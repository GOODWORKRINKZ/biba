# -*- coding: utf-8 -*-
"""Генерация KiCad-проекта (схема) из нетлиста EasyEDA (netlist.json).

Создаёт в <variant>/kicad_out/:
  - biba.kicad_sym        — собственные символы (в kicad/common/symbols/)
  - brushed-bts7960.kicad_pro / .kicad_sch
  - sym-lib-table / fp-lib-table
Связи — глобальные метки на каждом пине.

Запуск: python scripts/gen_schematic.py <каталог_variant>
"""
import json
import sys
import uuid
from pathlib import Path

PIN_LEN = 3.81
PIN_X = -5.08
STEP = 2.54


def pin_y(i: int) -> float:
    return -(i - 1) * STEP


# --- Определения символов: имя -> {ref, value, pins: [(number, name, etype)]} ---
def _pins(names):
    return [(str(i + 1), n, "passive") for i, n in enumerate(names)]


SYMBOLS = {
    "R": {"ref": "R", "value": "R", "pins": _pins(["1", "2"])},
    "C": {"ref": "C", "value": "C", "pins": _pins(["1", "2"])},
    "CONN_1X3": {"ref": "J", "value": "Conn_01x03", "pins": _pins(["1", "2", "3"])},
    "CONN_1X4": {"ref": "J", "value": "Conn_01x04", "pins": _pins(["1", "2", "3", "4"])},
    "RP2040": {
        "ref": "IC",
        "value": "RP2040",
        "pins": _pins([
            "CRSF_TX", "CRSF_RX", "GND", "L_RPWM", "L_LPWM", "L_REN", "L_LEN", "GND",
            "R_RPWM", "R_LPWM", "R_REN", "R_LEN", "GND", "GP10", "GP11", "UART1_TX",
            "UART1_RX", "GND", "GP14", "GP15", "GP16", "GP17", "GND", "GP18", "GP19",
            "I2C0_SDA", "I2C0_SCL", "GND", "IMU_INT1", "NC", "R_IS", "L_IS", "GND",
            "VBAT", "IBAT", "NC", "NC", "GND", "+5V", "NC", "NC", "NC", "NC", "GND",
        ]),
    },
    "SN74AHC244": {
        "ref": "U",
        "value": "SN74AHC244DW",
        "pins": _pins([
            "1OE", "1A0", "2Y3", "1A1", "2Y2", "1A2", "2Y1", "1A3", "2Y0", "GND",
            "2A0", "1Y3", "2A1", "1Y2", "2A2", "1Y1", "2A3", "1Y0", "2OE", "VCC",
        ]),
    },
    "BTN7970": {
        "ref": "U",
        "value": "BTN7970",
        "pins": _pins(["GND", "IN", "INH", "OUT", "SR", "IS", "VS", "OUT"]),
    },
    "BMI160": {
        "ref": "U",
        "value": "BMI160",
        "pins": _pins(["GND", "NC", "NC", "INT1", "VDDIO", "GND", "GND", "VDD", "NC", "NC", "NC", "CS", "SCL", "SDA"]),
    },
    "SPX3819": {
        "ref": "U",
        "value": "SPX3819M5-L-3-3/TR",
        "pins": _pins(["IN", "GND", "EN", "NC", "OUT"]),
    },
    "SKMW30G": {
        "ref": "PM",
        "value": "SKMW30G-05",
        "pins": _pins(["VIN", "GND", "VO", "TRIM", "GND", "CTRL"]),
    },
}

# привязка designator -> тип символа
def sym_for(designator: str) -> str:
    if designator.startswith("R"):
        return "R"
    if designator.startswith("C"):
        return "C"
    if designator.startswith("H"):
        return "CONN_1X3"
    if designator.startswith("J1"):
        return "CONN_1X3"
    if designator.startswith("J"):
        return "CONN_1X4"
    if designator.startswith("IC"):
        return "RP2040"
    if designator == "U1":
        return "SN74AHC244"
    if designator.startswith("U2") or designator.startswith("U3") or designator.startswith("U4") or designator.startswith("U5"):
        return "BTN7970"
    if designator == "U6":
        return "BMI160"
    if designator == "U7":
        return "SPX3819"
    if designator.startswith("PM"):
        return "SKMW30G"
    return "R"


# колонка по группе
def col_for(designator: str) -> int:
    if designator in ("PM1", "U7", "C6", "C7", "C8", "C9"):
        return 0
    if designator.startswith("IC"):
        return 1
    if designator == "U1":
        return 2
    if designator in ("U2", "U3", "U4", "U5") or designator.startswith(("R9", "R1")):
        return 3
    if designator.startswith(("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "C1", "C2", "C3", "C4", "C5")):
        return 4
    if designator.startswith(("U6", "R2")):
        return 5
    if designator.startswith(("J", "H")):
        return 6
    return 6


def gen_symbol(name: str, spec: dict) -> str:
    base = name.split(":")[-1]
    pins = spec["pins"]
    n = len(pins)
    top = 1.27
    bottom = -(n - 1) * STEP - 1.27
    body = (
        f"    (symbol \"{base}_0_1\"\n"
        f"      (rectangle (start -1.27 {top}) (end 1.27 {bottom:.2f})\n"
        f"        (stroke (width 0.254) (type default))\n"
        f"        (fill (type background)))\n"
        f"    )\n"
    )
    pinsexp = []
    for num, pname, etype in pins:
        y = pin_y(int(num))
        pinsexp.append(
            f"      (pin {etype} line (at {PIN_X} {y:.2f} 0) (length {PIN_LEN})\n"
            f"        (name \"{pname}\" (effects (font (size 1.27 1.27))))\n"
            f"        (number \"{num}\" (effects (font (size 1.27 1.27)))))\n"
        )
    pins_block = f"    (symbol \"{base}_1_1\"\n" + "".join(pinsexp) + "    )\n"
    return (
        f"  (symbol \"{name}\"\n"
        f"    (pin_names (offset 0.254))\n"
        f"    (in_bom yes)\n"
        f"    (on_board yes)\n"
        f"    (property \"Reference\" \"{spec['ref']}\" (at 0 {top + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n"
        f"    (property \"Value\" \"{spec['value']}\" (at 0 {bottom - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))\n"
        f"    (property \"Footprint\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
        f"    (property \"Datasheet\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n"
        + body + pins_block +
        f"  )\n"
    )


def gen_sym_lib() -> str:
    blocks = [gen_symbol(n, s) for n, s in SYMBOLS.items()]
    return "(kicad_symbol_lib\n  (version 20231120)\n  (generator \"python\")\n" + "".join(blocks) + ")\n"


def gen_sch(components, paper="A2") -> str:
    lines = []
    lines.append("(kicad_sch\n")
    lines.append("  (version 20231120)\n")
    lines.append("  (generator \"python\")\n")
    lines.append(f"  (uuid \"{uuid.uuid4()}\")\n")
    lines.append(f"  (paper \"{paper}\")\n")

    # встроенные символы — схема самодостаточна, sym-lib-table не обязателен
    lines.append("  (lib_symbols\n")
    for name, spec in SYMBOLS.items():
        lines.append(gen_symbol(f"biba:{name}", spec))
    lines.append("  )\n")

    # группировка и укладка по колонкам (все координаты кратны 2.54 мм)
    cols_x = {0: 0.0, 1: 25.4, 2: 50.8, 3: 76.2, 4: 101.6, 5: 127.0, 6: 152.4}
    col_y = {c: 50.8 for c in cols_x}
    col_height = {c: 0.0 for c in cols_x}
    placed = {}

    order = sorted(components, key=lambda c: (col_for(c["designator"]), _refkey(c["designator"])))
    # сначала посчитать высоты, потом разместить
    for c in order:
        d = c["designator"]
        sym = sym_for(d)
        n = len(SYMBOLS[sym]["pins"])
        h = (n + 3) * STEP
        col = col_for(d)
        placed[d] = (cols_x[col], col_y[col])
        col_y[col] += h

    # символы
    for c in order:
        d = c["designator"]
        sym = sym_for(d)
        spec = SYMBOLS[sym]
        x, y = placed[d]
        ref = d
        value = c["value"]
        lines.append(
            f"  (symbol (lib_id \"biba:{sym}\") (at {x:.2f} {y:.2f} 0) (unit 1)\n"
            f"    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid \"{uuid.uuid4()}\")\n"
            f"    (property \"Reference\" \"{ref}\" (at {x + 2.54:.2f} {y + 1.27:.2f} 0)\n"
            f"      (effects (font (size 1.27 1.27))))\n"
            f"    (property \"Value\" \"{value}\" (at {x + 2.54:.2f} {y - 1.27:.2f} 0)\n"
            f"      (effects (font (size 1.27 1.27))))\n"
            f"    (property \"Footprint\" \"\" (at {x:.2f} {y:.2f} 0)\n"
            f"      (effects (font (size 1.27 1.27)) hide))\n"
            f"    (property \"Datasheet\" \"\" (at {x:.2f} {y:.2f} 0)\n"
            f"      (effects (font (size 1.27 1.27)) hide))\n"
        )
        for num, _pn, _et in spec["pins"]:
            lines.append(f"    (pin \"{num}\" (uuid \"{uuid.uuid4()}\"))\n")
        lines.append("  )\n")

        # метки на пинах (KiCad инвертирует локальный Y символа при размещении)
        pin_net = {p["pin"]: p["net"] for p in c["pins"]}
        for num, _pn, _et in spec["pins"]:
            net = pin_net.get(num)
            ly = y - pin_y(int(num))
            if net:
                lines.append(
                    f"  (label \"{net}\" (at {x + PIN_X:.2f} {ly:.2f} 0)\n"
                    f"    (effects (font (size 1.27 1.27))) (uuid \"{uuid.uuid4()}\"))\n"
                )
            else:
                lines.append(
                    f"  (no_connect (at {x + PIN_X:.2f} {ly:.2f}) (uuid \"{uuid.uuid4()}\"))\n"
                )

    lines.append("  (sheet_instances\n")
    lines.append("    (path \"/\" (page \"1\"))\n")
    lines.append("  )\n")
    lines.append(")\n")
    return "".join(lines)


def _refkey(d: str):
    import re
    m = re.match(r"([A-Za-z]+)(\d+)", d)
    return (m.group(1), int(m.group(2))) if m else (d, 0)


def main() -> int:
    variant = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    netlist = json.load(open(variant / "easyeda" / "RP2040" / "netlist.json", encoding="utf-8"))
    comps = netlist["components"]

    # каталоги
    proj_dir = variant
    proj_dir.mkdir(exist_ok=True)
    sym_dir = variant.parent.parent / "common" / "symbols"
    sym_dir.mkdir(parents=True, exist_ok=True)

    sym_path = sym_dir / "biba.kicad_sym"
    sym_path.write_text(gen_sym_lib(), encoding="utf-8")

    proj_name = "brushed-bts7960"
    (proj_dir / f"{proj_name}.kicad_sch").write_text(gen_sch(comps), encoding="utf-8")

    (proj_dir / f"{proj_name}.kicad_pro").write_text(
        "(kicad_project\n  (version 20231120)\n  (generator \"python\")\n"
        "  (paper \"A2\")\n  (schematic\n    (legacy_lib_dir \"\")\n    (legacy_lib_list \"\")\n  )\n)\n",
        encoding="utf-8",
    )

    rel = sym_path.resolve().as_posix()
    (proj_dir / "sym-lib-table").write_text(
        "(sym_lib_table\n  (version 7)\n"
        f"  (lib (name \"biba\")(type \"KiCad\")(uri \"{rel}\")(options \"\")(descr \"BiBa project symbols\"))\n"
        ")\n",
        encoding="utf-8",
    )
    (proj_dir / "fp-lib-table").write_text("(fp_lib_table\n  (version 7)\n)\n", encoding="utf-8")

    print("Символы:", sym_path)
    print("Проект:", proj_dir)
    print("Компонентов:", len(comps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
