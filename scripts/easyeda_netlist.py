# -*- coding: utf-8 -*-
"""Разбор исходника EasyEDA (JSON) в нетлист и список компонентов.

Читает PCB_RP2040.json (нетлист по падам) и RP2040.json (BOM/номиналы),
пишет easyeda/netlist.txt и easyeda/components.tsv.

Запуск: python scripts/easyeda_netlist.py <каталог_easyeda>
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def parse_attrs(s: str) -> dict:
    """'key`value`key`value' -> {key: value}."""
    toks = s.split("`")
    d = {}
    for i in range(0, len(toks) - 1, 2):
        d[toks[i]] = toks[i + 1]
    return d


def parse_lib(s: str) -> dict:
    """Разобрать строку LIB~... в словарь компонента."""
    parts = s.split("#@$")
    header = parts[0].split("~")
    x, y = header[1], header[2]
    attrs = parse_attrs(header[3]) if len(header) > 3 else {}
    rotation = header[4] if len(header) > 4 else ""
    uuid = header[8] if len(header) > 8 else ""
    designator, value = "", ""
    pads = []  # (number, net)
    for sub in parts[1:]:
        f = sub.split("~")
        etype = f[0]
        if etype == "TEXT" and len(f) > 10:
            ttype, content = f[1], f[10]
            if ttype == "P":
                designator = content
            elif ttype == "N":
                value = content
        elif etype == "PAD" and len(f) > 8:
            net, number = f[7], f[8]
            pads.append((number, net))
    return {
        "designator": designator,
        "value": value,
        "package": attrs.get("package", ""),
        "lcsc": attrs.get("Supplier Part") or "",
        "mfr_part": attrs.get("Manufacturer Part") or "",
        "link": attrs.get("link", ""),
        "x": x,
        "y": y,
        "rotation": rotation,
        "uuid": uuid,
        "pads": pads,
    }


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    pcb = json.load(open(src / "PCB_RP2040.json", encoding="utf-8"))
    sch = json.load(open(src / "RP2040.json", encoding="utf-8"))

    shape = pcb.get("shape", [])
    libs = [s for s in shape if s.startswith("LIB~")]

    comps = []
    for s in libs:
        c = parse_lib(s)
        if c["designator"]:
            comps.append(c)

    # top-level PADs (на случай, если пады не только внутри LIB)
    top_pads = [s for s in shape if s.startswith("PAD~")]

    # Собираем нетлист из встроенных падов LIB
    nets = defaultdict(set)  # net -> set of "D.pin"
    total_embedded_pads = 0
    for c in comps:
        for number, net in c["pads"]:
            if net:
                nets[net].add(f"{c['designator']}.{number}")
                total_embedded_pads += 1

    # Дополняем из top-level PAD, если встроенных не хватило
    if not comps or total_embedded_pads < len(top_pads):
        for s in top_pads:
            f = s.split("~")
            if len(f) > 8:
                net, number = f[7], f[8]
                if net:
                    # без designator — сохраним отдельно, номер позиции по gge
                    nets[net].add(f"?(pad {number} {f[1]},{f[2]})")

    # BOM из схемы
    bom = sch.get("BOM") or []

    out = src
    # netlist
    with open(out / "netlist.txt", "w", encoding="utf-8") as fh:
        fh.write(f"# BiBa RP2040 — нетлист (EasyEDA). Компонентов: {len(comps)}, "
                 f"сетей: {len(nets)}, встроенных падов: {total_embedded_pads}, "
                 f"top-level PAD: {len(top_pads)}\n\n")
        for net in sorted(nets):
            pins = sorted(nets[net])
            fh.write(f"{net}: {', '.join(pins)}\n")

    # components tsv
    with open(out / "components.tsv", "w", encoding="utf-8") as fh:
        fh.write("designator\tvalue\tpackage\tlcsc\tmfr_part\tpins\trotation\tx\ty\tlink\n")
        for c in sorted(comps, key=lambda d: _designator_key(d["designator"])):
            fh.write(
                f"{c['designator']}\t{c['value']}\t{c['package']}\t{c['lcsc']}\t"
                f"{c['mfr_part']}\t{len(c['pads'])}\t{c['rotation']}\t{c['x']}\t{c['y']}\t{c['link']}\n"
            )

    # консоль
    print(f"Компонентов: {len(comps)}")
    print(f"Сетей: {len(nets)}")
    print(f"Встроенных падов в LIB: {total_embedded_pads}")
    print(f"Top-level PAD: {len(top_pads)}")
    print(f"BOM строк: {len(bom)}")
    print("\n=== Компоненты ===")
    for c in sorted(comps, key=lambda d: _designator_key(d["designator"])):
        padstr = ", ".join(f"{n}={net}" for n, net in c["pads"])
        print(f"{c['designator']:6s} {c['value']:14s} {c['package']:26s} "
              f"{c['lcsc']:10s} {c['mfr_part']:16s} [{padstr}]")
    print("\nЗаписано:", out / "netlist.txt", ",", out / "components.tsv")
    return 0


def _designator_key(d: str):
    m = re.match(r"([A-Za-z]+)(\d+)", d)
    if m:
        return (m.group(1), int(m.group(2)))
    return (d, 0)


if __name__ == "__main__":
    raise SystemExit(main())
