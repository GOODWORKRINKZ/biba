# -*- coding: utf-8 -*-
"""Конвертация схемы EasyEDA (RP2040.json) в KiCad-проект с сохранением разводки.

В отличие от gen_schematic.py (нетлист → метки), здесь сохраняются оригинальные
позиции компонентов, провода (W), метки (F) и соединения (J) из EasyEDA.

Запуск: python scripts/easyeda_sch2kicad.py <каталог_variant>
Результат: <variant>/brushed-bts7960.kicad_sch + .kicad_pro + таблицы.
Символы: kicad/common/symbols/biba.kicad_sym (перезаписываются).
"""
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

SCALE = 0.254  # 1 единица EasyEDA (схема) = 10 mil = 0.254 мм
PIN_LEN = 2.54


def mm_x(v):
    return float(v) * SCALE


def mm_y(v):
    return -float(v) * SCALE  # Y инвертирован (EasyEDA Y вверх -> KiCad вниз)


def parse_lib(s: str) -> dict:
    parts = s.split("#@$")
    header = parts[0].split("~")
    cx, cy = float(header[1]), float(header[2])
    attrs = parse_attrs(header[3]) if len(header) > 3 else {}
    designator, value = "", ""
    pins = []
    for sub in parts[1:]:
        f = sub.split("~")
        if f[0] == "T" and len(f) > 12:
            ttype, text = f[1], f[12]
            if ttype == "P":
                designator = text
            elif ttype == "N":
                value = text
        elif f[0] == "P" and len(f) > 5:
            num, px, py = f[3], float(f[4]), float(f[5])
            pins.append((num, px, py))
    return {
        "designator": designator,
        "value": value,
        "package": attrs.get("package", ""),
        "x": cx,
        "y": cy,
        "pins": pins,
    }


def parse_attrs(s: str) -> dict:
    toks = s.split("`")
    d = {}
    for i in range(0, len(toks) - 1, 2):
        d[toks[i]] = toks[i + 1]
    return d


def parse_wire(s: str):
    path = s.split("~")[1].split()
    pts = [(float(path[i]), float(path[i + 1])) for i in range(0, len(path) - 1, 2)]
    return pts


def parse_flag(s: str):
    f = s.split("~")
    x, y = float(f[2]), float(f[3])
    text = s.split("^^")[2].split("~")[0]
    return text, x, y


def parse_junction(s: str):
    f = s.split("~")
    return float(f[1]), float(f[2])


def designator_prefix(d: str) -> str:
    m = re.match(r"([A-Za-z]+)", d)
    return m.group(1) if m else "U"


def main() -> int:
    variant = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    src = variant / "easyeda" / "RP2040" / "RP2040.json"
    sch = json.load(open(src, encoding="utf-8"))
    shapes = sch["schematics"][0]["dataStr"]["shape"]

    comps, wires, flags, junctions, ncs = [], [], [], [], []
    for s in shapes:
        g = s.split("~")[0]
        if g == "LIB":
            comps.append(parse_lib(s))
        elif g == "W":
            wires.append(parse_wire(s))
        elif g == "F":
            flags.append(parse_flag(s))
        elif g == "J":
            junctions.append(parse_junction(s))
        elif g == "O":
            f = s.split("~")
            ncs.append((float(f[1]), float(f[2])))

    comps = [c for c in comps if c["designator"] and c["pins"]]

    # Группировка компонентов по раскладке пинов (для дедупликации символов)
    groups = {}
    sym_of = {}
    for c in comps:
        prefix = designator_prefix(c["designator"])
        sig = tuple(sorted((n, round(px - c["x"], 2), round(py - c["y"], 2)) for n, px, py in c["pins"]))
        key = (prefix, sig)
        if key not in groups:
            groups[key] = {"prefix": prefix, "pins": [(n, px, py) for n, px, py in sig], "members": []}
        groups[key]["members"].append(c)
        sym_of[c["designator"]] = key

    # имя символа для каждой группы
    used_names = defaultdict(int)
    for key in groups:
        prefix = groups[key]["prefix"]
        name = prefix if used_names[prefix] == 0 else f"{prefix}_{used_names[prefix]}"
        used_names[prefix] += 1
        groups[key]["name"] = name

    # генерация символов
    sym_blocks = []
    for key, grp in groups.items():
        name = grp["name"]
        pins = grp["pins"]
        xs = [px * SCALE for _, px, _ in pins]
        ys = [py * SCALE for _, _, py in pins]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        body_l = minx - 1.27
        body_r = maxx + 1.27
        body_t = maxy + 1.27
        body_b = miny - 1.27
        pinsexp = []
        for num, px, py in pins:
            lx = px * SCALE
            ly = py * SCALE
            # угол: пины направлены к центру корпуса
            if abs(lx) >= abs(ly):
                ang = 0 if lx < 0 else 180
            else:
                ang = 90 if ly > 0 else 270
            pinsexp.append(
                f"      (pin passive line (at {lx:.4f} {ly:.4f} {ang}) (length {PIN_LEN})\n"
                f"        (name \"{num}\" (effects (font (size 1.27 1.27))))\n"
                f"        (number \"{num}\" (effects (font (size 1.27 1.27)))))\n"
            )
        sym_blocks.append(
            f"  (symbol \"{name}\"\n"
            f"    (pin_names (offset 0.254))\n"
            f"    (in_bom yes)\n"
            f"    (on_board yes)\n"
            f"    (property \"Reference\" \"{grp['prefix']}\" (at 0 {body_t + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n"
            f"    (property \"Value\" \"{grp['prefix']}\" (at 0 {body_b - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n"
            f"    (property \"Footprint\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
            f"    (property \"Datasheet\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
            f"    (symbol \"{name}_0_1\"\n"
            f"      (rectangle (start {body_l:.4f} {body_t:.4f}) (end {body_r:.4f} {body_b:.4f})\n"
            f"        (stroke (width 0.254) (type default))\n"
            f"        (fill (type background)))\n"
            f"    )\n"
            f"    (symbol \"{name}_1_1\"\n" + "".join(pinsexp) + "    )\n"
            f"  )\n"
        )

    # ---- .kicad_sch ----
    L = []
    L.append("(kicad_sch\n")
    L.append("  (version 20231120)\n")
    L.append("  (generator \"easyeda2kicad\")\n")
    L.append(f"  (uuid \"{uuid.uuid4()}\")\n")
    L.append("  (paper \"A3\")\n")
    # встроенные символы с префиксом lib_id
    L.append("  (lib_symbols\n")
    for key, grp in groups.items():
        name = grp["name"]
        L.append(_embedded_symbol(f"biba:{name}", grp))
    L.append("  )\n")

    # компоненты
    for c in comps:
        key = sym_of[c["designator"]]
        symname = groups[key]["name"]
        cx, cy = mm_x(c["x"]), mm_y(c["y"])
        L.append(
            f"  (symbol (lib_id \"biba:{symname}\") (at {cx:.4f} {cy:.4f} 0) (unit 1)\n"
            f"    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid \"{uuid.uuid4()}\")\n"
            f"    (property \"Reference\" \"{c['designator']}\" (at {cx + 2.54:.4f} {cy + 2.54:.4f} 0)\n"
            f"      (effects (font (size 1.27 1.27))))\n"
            f"    (property \"Value\" \"{c['value']}\" (at {cx + 2.54:.4f} {cy - 2.54:.4f} 0)\n"
            f"      (effects (font (size 1.27 1.27))))\n"
            f"    (property \"Footprint\" \"\" (at {cx:.4f} {cy:.4f} 0)\n"
            f"      (effects (font (size 1.27 1.27)) hide))\n"
            f"    (property \"Datasheet\" \"\" (at {cx:.4f} {cy:.4f} 0)\n"
            f"      (effects (font (size 1.27 1.27)) hide))\n"
        )
        for num, _px, _py in c["pins"]:
            L.append(f"    (pin \"{num}\" (uuid \"{uuid.uuid4()}\"))\n")
        L.append("  )\n")

    # провода
    skip = set(os.environ.get("SCH_SKIP", "").split(","))
    if "wires" not in skip:
        for pts in wires:
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                L.append(
                    f"  (wire (pts (xy {mm_x(a[0]):.4f} {mm_y(a[1]):.4f}) (xy {mm_x(b[0]):.4f} {mm_y(b[1]):.4f}))\n"
                    f"    (stroke (width 0) (type solid))\n    (uuid \"{uuid.uuid4()}\"))\n"
                )

    # соединения
    if "junctions" not in skip:
        for x, y in junctions:
            L.append(f"  (junction (at {mm_x(x):.4f} {mm_y(y):.4f}) (diameter 1.016) (color 0 0 0 0)\n    (uuid \"{uuid.uuid4()}\"))\n")

    # метки
    if "labels" not in skip:
        for text, x, y in flags:
            L.append(
                f"  (label \"{text}\" (at {mm_x(x):.4f} {mm_y(y):.4f} 0)\n"
                f"    (effects (font (size 1.27 1.27))) (uuid \"{uuid.uuid4()}\"))\n"
            )

    # no-connect (крестики EasyEDA)
    for x, y in ncs:
        L.append(f"  (no_connect (at {mm_x(x):.4f} {mm_y(y):.4f}) (uuid \"{uuid.uuid4()}\"))\n")

    L.append("  (sheet_instances\n    (path \"/\" (page \"1\"))\n  )\n")
    L.append(")\n")
    sch_txt = "".join(L)

    # ---- запись ----
    sym_dir = variant.parent.parent / "common" / "symbols"
    sym_dir.mkdir(parents=True, exist_ok=True)
    sym_lib = "(kicad_symbol_lib\n  (version 20231120)\n  (generator \"easyeda2kicad\")\n" + "".join(sym_blocks) + ")\n"
    (sym_dir / "biba.kicad_sym").write_text(sym_lib, encoding="utf-8")

    proj = "brushed-bts7960"
    (variant / f"{proj}.kicad_sch").write_text(sch_txt, encoding="utf-8")
    (variant / f"{proj}.kicad_pro").write_text(
        "(kicad_project\n  (version 20231120)\n  (generator \"easyeda2kicad\")\n"
        "  (paper \"A3\")\n  (schematic\n    (legacy_lib_dir \"\")\n    (legacy_lib_list \"\")\n  )\n)\n",
        encoding="utf-8",
    )
    rel = (sym_dir / "biba.kicad_sym").resolve().as_posix()
    (variant / "sym-lib-table").write_text(
        "(sym_lib_table\n  (version 7)\n"
        f"  (lib (name \"biba\")(type \"KiCad\")(uri \"{rel}\")(options \"\")(descr \"BiBa project symbols\"))\n"
        ")\n",
        encoding="utf-8",
    )
    (variant / "fp-lib-table").write_text("(fp_lib_table\n  (version 7)\n)\n", encoding="utf-8")

    print(f"Компонентов: {len(comps)}, проводов: {len(wires)}, меток: {len(flags)}, соединений: {len(junctions)}, no-connect: {len(ncs)}, символов: {len(groups)}")
    return 0


def _embedded_symbol(name: str, grp: dict) -> str:
    base = name.split(":")[-1]
    pins = grp["pins"]
    xs = [px * SCALE for _, px, _ in pins]
    ys = [py * SCALE for _, _, py in pins]
    body_l, body_r = min(xs) - 1.27, max(xs) + 1.27
    body_t, body_b = max(ys) + 1.27, min(ys) - 1.27
    pinsexp = []
    for num, px, py in pins:
        lx, ly = px * SCALE, py * SCALE
        if abs(lx) >= abs(ly):
            ang = 0 if lx < 0 else 180
        else:
            ang = 90 if ly > 0 else 270
        pinsexp.append(
            f"      (pin passive line (at {lx:.4f} {ly:.4f} {ang}) (length {PIN_LEN})\n"
            f"        (name \"{num}\" (effects (font (size 1.27 1.27))))\n"
            f"        (number \"{num}\" (effects (font (size 1.27 1.27)))))\n"
        )
    return (
        f"  (symbol \"{name}\"\n"
        f"    (pin_names (offset 0.254))\n"
        f"    (in_bom yes)\n"
        f"    (on_board yes)\n"
        f"    (property \"Reference\" \"{grp['prefix']}\" (at 0 {body_t + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n"
        f"    (property \"Value\" \"{grp['prefix']}\" (at 0 {body_b - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n"
        f"    (property \"Footprint\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
        f"    (property \"Datasheet\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
        f"    (symbol \"{base}_0_1\"\n"
        f"      (rectangle (start {body_l:.4f} {body_t:.4f}) (end {body_r:.4f} {body_b:.4f})\n"
        f"        (stroke (width 0.254) (type default))\n"
        f"        (fill (type background)))\n"
        f"    )\n"
        f"    (symbol \"{base}_1_1\"\n" + "".join(pinsexp) + "    )\n"
        f"  )\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
