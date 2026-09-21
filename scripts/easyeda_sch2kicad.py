# -*- coding: utf-8 -*-
"""Конвертация схемы EasyEDA (RP2040.json) в KiCad 1:1 — с графикой символов.

Что переносится:
  * компоненты: позиция, поворот, графика символа (R/PL/PG/E/A/PT/T), пины
    с реальной длиной/направлением и именами;
  * провода (W) — полилинии режутся на отрезки и дополнительно в точках пинов
    (KiCad не соединяет пин, лежащий в середине провода);
  * GND / +5V флаги → power-символы, netPort → глобальные метки;
  * соединения (J), no-connect (O).

Системы координат:
  EasyEDA: 1 ед. = 10 mil, Y вниз, поворот — против часовой на экране.
  KiCad-лист: мм, Y вниз, поворот символа — тоже против часовой.
  KiCad-библиотека: Y вверх. Поэтому графика символа = R(-rot)·(dx, -dy).

Запуск: python scripts/easyeda_sch2kicad.py <каталог_variant>
Результат: <variant>/brushed-bts7960.kicad_sch, kicad/common/symbols/biba.kicad_sym
"""
import json
import math
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from easyeda_netlist import footprint_name

SCALE = 0.254  # 1 единица EasyEDA = 10 mil
# рамка EasyEDA: x 0..1632, y -1149..0 → лист A3 KiCad (420×297 мм)
OFF_X, OFF_Y = 10, 1150
GRID = 5  # 5 ед. = 1.27 мм
LIB = "biba"
PROJ = "brushed-bts7960"

ELEC = "passive"


_uuid_n = 0


def U():
    """Детерминированные UUID: повторная генерация даёт минимальный diff."""
    global _uuid_n
    _uuid_n += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"biba/{PROJ}/{_uuid_n}"))


def f(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def sx(x):
    return (float(x) + OFF_X) * SCALE


def sy(y):
    return (float(y) + OFF_Y) * SCALE


def snap(v, g=GRID):
    return round(v / g) * g


def snap_pt(x, y, tol=1.5):
    """Привязка к сетке точек, которые в EasyEDA «съехали» на 1–2 ед."""
    return tuple(snap(v) if abs(v - snap(v)) <= tol else v for v in (x, y))


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def font_mm(size_str, default=1.27):
    m = re.match(r"([\d.]+)pt", size_str or "")
    if not m:
        return default
    return round(float(m.group(1)) / 7.0 * 1.27, 3)


# ---------------------------------------------------------------- геометрия
class Frame:
    """Преобразование абсолютных координат EasyEDA в локальные координаты
    символа KiCad (Y вверх) с отменой поворота компонента."""

    def __init__(self, ox, oy, rot):
        self.ox, self.oy, self.rot = ox, oy, rot % 360
        a = math.radians(-self.rot)
        self.c, self.s = round(math.cos(a)), round(math.sin(a))

    def pt(self, x, y):
        mx, my = float(x) - self.ox, -(float(y) - self.oy)
        lx = mx * self.c - my * self.s
        ly = mx * self.s + my * self.c
        return round(lx * SCALE, 4), round(ly * SCALE, 4)

    def vec(self, dx, dy):
        mx, my = float(dx), -float(dy)
        return mx * self.c - my * self.s, mx * self.s + my * self.c

    def angle(self, a):
        return (float(a or 0) - self.rot) % 360


def parse_attrs(s):
    toks = s.split("`")
    return {toks[i]: toks[i + 1] for i in range(0, len(toks) - 1, 2)}


def path_polylines(d):
    """SVG path (M/L/H/V/Z, абсолютные и относительные) → список полилиний."""
    toks = re.findall(r"[MLHVZmlhvz]|-?[\d.]+(?:e-?\d+)?", d)
    lines, cur = [], []
    x = y = 0.0
    start = (0.0, 0.0)
    i, cmd = 0, None
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append(start)
                    lines.append(cur)
                cur = []
                x, y = start
            continue
        if cmd in "Mm":
            nx, ny = float(toks[i]), float(toks[i + 1])
            i += 2
            if cmd == "m":
                nx, ny = x + nx, y + ny
            if len(cur) > 1:
                lines.append(cur)
            x, y = nx, ny
            start = (x, y)
            cur = [(x, y)]
            cmd = "L" if cmd == "M" else "l"
        elif cmd in "Ll":
            nx, ny = float(toks[i]), float(toks[i + 1])
            i += 2
            if cmd == "l":
                nx, ny = x + nx, y + ny
            x, y = nx, ny
            cur.append((x, y))
        elif cmd in "Hh":
            v = float(toks[i])
            i += 1
            x = x + v if cmd == "h" else v
            cur.append((x, y))
        elif cmd in "Vv":
            v = float(toks[i])
            i += 1
            y = y + v if cmd == "v" else v
            cur.append((x, y))
        else:
            i += 1
    if len(cur) > 1:
        lines.append(cur)
    return lines


def svg_arc(d):
    """'M x1 y1 A rx ry rot large sweep x2 y2' → (start, mid, end) в абсолютных коорд."""
    n = [float(v) for v in re.findall(r"-?[\d.]+", d)]
    x1, y1, rx, _ry, _rot, large, sweep, x2, y2 = n[:9]
    r = rx
    dx, dy = (x2 - x1) / 2, (y2 - y1) / 2
    q = math.hypot(dx, dy)
    r = max(r, q)
    h = math.sqrt(max(r * r - q * q, 0))
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    ux, uy = -dy / q, dx / q
    sign = 1 if large != sweep else -1
    cx, cy = mx + sign * h * ux, my + sign * h * uy
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    da = a2 - a1
    if sweep:  # по часовой в экранных коорд. = рост угла
        while da <= 0:
            da += 2 * math.pi
    else:
        while da >= 0:
            da -= 2 * math.pi
    am = a1 + da / 2
    return (x1, y1), (cx + r * math.cos(am), cy + r * math.sin(am)), (x2, y2)


def is_fill(v):
    return bool(v) and v not in ("none", "transparent")


# ---------------------------------------------------------------- парсинг
def parse_pin(s, fr):
    seg = s.split("^^")
    h = seg[0].split("~")
    num, px, py = h[3], float(h[4]), float(h[5])
    elec = h[2]
    lines = path_polylines(seg[2].split("~")[0])
    pts = [p for ln in lines for p in ln]
    far = max(pts, key=lambda p: math.hypot(p[0] - px, p[1] - py)) if pts else (px, py)
    length = math.hypot(far[0] - px, far[1] - py) * SCALE
    vx, vy = fr.vec(far[0] - px, far[1] - py)
    ang = int(round(math.degrees(math.atan2(vy, vx)))) % 360 if length else 0
    nm = seg[3].split("~")
    nu = seg[4].split("~")
    name = nm[4] if len(nm) > 4 else num
    lx, ly = fr.pt(px, py)
    return {
        "num": num,
        "name": name,
        "x": lx,
        "y": ly,
        "abs": (px, py),
        "ang": ang,
        "len": round(length, 4),
        "name_show": nm[0] == "1",
        "num_show": nu[0] == "1",
        "elec": elec,
    }


def parse_lib(s):
    parts = s.split("#@$")
    h = parts[0].split("~")
    cx, cy = float(h[1]), float(h[2])
    attrs = parse_attrs(h[3])
    rot = float(h[4] or 0)
    ax, ay = snap(cx), snap(cy)
    fr = Frame(ax, ay, rot)
    comp = {
        "attrs": attrs,
        "rot": int(rot) % 360,
        "ax": ax,
        "ay": ay,
        "designator": "",
        "value": "",
        "ref_t": None,
        "val_t": None,
        "pins": [],
        "gfx": [],
    }
    for sub in parts[1:]:
        t = sub.split("~")
        k = t[0]
        if k == "T":
            text = t[12] if len(t) > 12 else ""
            info = {
                "x": float(t[2]),
                "y": float(t[3]),
                "rot": float(t[4] or 0),
                "size": t[7],
                "text": text,
                "show": t[13] != "0" if len(t) > 13 else True,
                "anchor": t[14] if len(t) > 14 else "start",
            }
            if t[1] == "P":
                comp["designator"], comp["ref_t"] = text, info
            elif t[1] == "N":
                comp["value"], comp["val_t"] = text, info
            elif t[1] == "L" and info["show"] and text:
                lx, ly = fr.pt(info["x"], info["y"])
                comp["gfx"].append(("text", text, lx, ly, fr.angle(info["rot"]), font_mm(info["size"]), info["anchor"]))
        elif k == "P":
            comp["pins"].append(parse_pin(sub, fr))
        elif k == "R":
            x, y, w, hh = float(t[1]), float(t[2]), float(t[5]), float(t[6])
            a, b = fr.pt(x, y), fr.pt(x + w, y + hh)
            comp["gfx"].append(("rect", a, b, is_fill(t[10])))
        elif k in ("PL", "PG"):
            n = [float(v) for v in t[1].split()]
            pts = [fr.pt(n[i], n[i + 1]) for i in range(0, len(n) - 1, 2)]
            fill = k == "PG" and is_fill(t[5])
            if k == "PG":
                pts.append(pts[0])
            comp["gfx"].append(("poly", tuple(pts), fill))
        elif k == "PT":
            for ln in path_polylines(t[1]):
                comp["gfx"].append(("poly", tuple(fr.pt(*p) for p in ln), is_fill(t[5])))
        elif k == "E":
            ex, ey, rx = float(t[1]), float(t[2]), float(t[3])
            c = fr.pt(ex, ey)
            comp["gfx"].append(("circle", c, round(rx * SCALE, 4), is_fill(t[8])))
        elif k == "A":
            a, m, b = svg_arc(t[1])
            comp["gfx"].append(("arc", fr.pt(*a), fr.pt(*m), fr.pt(*b)))
    return comp


def parse_flag(s):
    seg = s.split("^^")
    h = seg[0].split("~")
    kind = h[1].replace("part_netLabel_", "")
    x, y = float(h[2]), float(h[3])
    rot = int(float(h[4] or 0)) % 360
    tt = seg[2].split("~")
    return {
        "kind": kind,
        "x": x,
        "y": y,
        "rot": rot,
        "text": tt[0],
        "tx": float(tt[2]),
        "ty": float(tt[3]),
        "trot": float(tt[4] or 0),
        "anchor": tt[5] or "start",
    }


# ---------------------------------------------------------------- символы
def pin_sexpr(p, ind):
    name = esc(p["name"]) if p["name"] else "~"
    return (
        f"{ind}(pin {ELEC} line (at {f(p['x'])} {f(p['y'])} {p['ang']}) (length {f(p['len'])})\n"
        f"{ind}  (name \"{name}\" (effects (font (size 1.016 1.016))))\n"
        f"{ind}  (number \"{esc(p['num'])}\" (effects (font (size 1.016 1.016))))\n"
        f"{ind})\n"
    )


def gfx_sexpr(g, ind):
    k = g[0]
    stroke = "(stroke (width 0.1524) (type default))"
    if k == "rect":
        _, a, b, fill = g
        return (
            f"{ind}(rectangle (start {f(a[0])} {f(a[1])}) (end {f(b[0])} {f(b[1])})\n"
            f"{ind}  {stroke} (fill (type {'outline' if fill else 'none'})))\n"
        )
    if k == "poly":
        _, pts, fill = g
        xy = " ".join(f"(xy {f(x)} {f(y)})" for x, y in pts)
        return f"{ind}(polyline (pts {xy})\n{ind}  {stroke} (fill (type {'outline' if fill else 'none'})))\n"
    if k == "circle":
        _, c, r, fill = g
        return (
            f"{ind}(circle (center {f(c[0])} {f(c[1])}) (radius {f(r)})\n"
            f"{ind}  {stroke} (fill (type {'outline' if fill else 'none'})))\n"
        )
    if k == "arc":
        _, a, m, b = g
        return (
            f"{ind}(arc (start {f(a[0])} {f(a[1])}) (mid {f(m[0])} {f(m[1])}) (end {f(b[0])} {f(b[1])})\n"
            f"{ind}  {stroke} (fill (type none)))\n"
        )
    if k == "text":
        _, text, x, y, ang, size, anchor = g
        ang = int(round(ang)) % 360
        flip = ang in (180, 270)  # KiCad рисует текст читаемым и отражает выравнивание
        ang %= 180
        if flip:
            anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
        just = {"start": "left", "end": "right"}.get(anchor, "")
        vj = "bottom"
        j = f" (justify {just} {vj})" if just else f" (justify {vj})"
        return f"{ind}(text \"{esc(text)}\" (at {f(x)} {f(y)} {ang * 10})\n{ind}  (effects (font (size {size} {size})){j}))\n"
    raise ValueError(k)


def symbol_sexpr(name, sym, prefix_name, ind="  "):
    base = name.split(":")[-1]
    pins = sym["pins"]
    hide_names = not any(p["name_show"] for p in pins)
    hide_nums = not any(p["num_show"] for p in pins)
    ys = [p["y"] for p in pins] or [0]
    out = [f"{ind}(symbol \"{esc(name)}\"\n"]
    if sym.get("power"):
        out.append(f"{ind}  (power)\n")
    out.append(f"{ind}  (pin_numbers{' hide' if hide_nums else ''})\n")
    out.append(f"{ind}  (pin_names (offset 0.508){' hide' if hide_names else ''})\n")
    out.append(f"{ind}  (exclude_from_sim no) (in_bom {'no' if sym.get('power') else 'yes'}) (on_board {'no' if sym.get('power') else 'yes'})\n")
    hid = " hide" if sym.get("power") else ""
    out.append(f"{ind}  (property \"Reference\" \"{prefix_name}\" (at 0 {f(max(ys) + 2.54)} 0) (effects (font (size 1.27 1.27)){hid}))\n")
    out.append(f"{ind}  (property \"Value\" \"{esc(sym['value'])}\" (at 0 {f(min(ys) - 2.54)} 0) (effects (font (size 1.27 1.27))))\n")
    out.append(f"{ind}  (property \"Footprint\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n")
    out.append(f"{ind}  (property \"Datasheet\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n")
    if sym.get("power"):
        out.append(f"{ind}  (property \"ki_keywords\" \"global power\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n")
    out.append(f"{ind}  (symbol \"{esc(base)}_0_1\"\n")
    for g in sym["gfx"]:
        out.append(gfx_sexpr(g, ind + "    "))
    out.append(f"{ind}  )\n")
    out.append(f"{ind}  (symbol \"{esc(base)}_1_1\"\n")
    for p in pins:
        if sym.get("power"):
            out.append(
                f"{ind}    (pin power_in line (at 0 0 {p['ang']}) (length 0) hide\n"
                f"{ind}      (name \"{esc(sym['value'])}\" (effects (font (size 1.27 1.27))))\n"
                f"{ind}      (number \"1\" (effects (font (size 1.27 1.27))))\n"
                f"{ind}    )\n"
            )
        else:
            out.append(pin_sexpr(p, ind + "    "))
    out.append(f"{ind}  )\n{ind})\n")
    return "".join(out)


POWER_SYMS = {
    # GND: при rot=0 смотрит вниз (как в EasyEDA)
    "GND": {
        "power": True,
        "value": "GND",
        "pins": [{"num": "1", "name": "GND", "x": 0, "y": 0, "ang": 270, "len": 0, "name_show": False, "num_show": False}],
        "gfx": [
            ("poly", ((0, 0), (0, -1.27)), False),
            ("poly", ((-1.524, -1.27), (1.524, -1.27)), False),
            ("poly", ((-1.016, -1.778), (1.016, -1.778)), False),
            ("poly", ((-0.508, -2.286), (0.508, -2.286)), False),
        ],
    },
    # +5V: при rot=0 смотрит вверх
    "+5V": {
        "power": True,
        "value": "+5V",
        "pins": [{"num": "1", "name": "+5V", "x": 0, "y": 0, "ang": 90, "len": 0, "name_show": False, "num_show": False}],
        "gfx": [
            ("poly", ((0, 0), (0, 2.54)), False),
            ("poly", ((-1.27, 2.54), (1.27, 2.54)), False),
        ],
    },
}
POWER_NAME = {"gnD": "GND", "+5V": "+5V"}


def sym_name(comp, used):
    pre = re.match(r"[A-Za-z]+", comp["designator"]).group(0)
    if pre in ("R", "C", "L", "D") and len(comp["pins"]) <= 2:
        base = pre
        if pre == "C" and any(g[0] == "arc" for g in comp["gfx"]):
            base = "C_Pol"
    else:
        base = re.sub(r"[^A-Za-z0-9_.+-]", "_", comp["value"]) or pre
    return base, pre


def text_center(t, size_units=7.0):
    """Центр текста EasyEDA (x,y — базовая линия, anchor start/middle/end)."""
    w = len(t["text"]) * size_units * 0.62
    rot = int(t["rot"]) % 360
    along = {"start": w / 2, "end": -w / 2}.get(t["anchor"], 0)
    up = size_units * 0.35
    if rot in (90, 270):
        # вертикальный текст (читается снизу вверх)
        return t["x"] - up, t["y"] - along, 90
    return t["x"] + along, t["y"] - up, 0


def field_angle(visual, sym_rot):
    """KiCad хранит угол поля относительно символа."""
    return 90 if (visual == 90) != (sym_rot in (90, 270)) else 0


# ---------------------------------------------------------------- провода
def split_segments(wires, nodes):
    segs = []
    for pts in wires:
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            inner = []
            for n in nodes:
                if n in (a, b):
                    continue
                if on_segment(n, a, b):
                    inner.append(n)
            inner.sort(key=lambda n: (n[0] - a[0]) ** 2 + (n[1] - a[1]) ** 2)
            chain = [a] + inner + [b]
            segs.extend(zip(chain, chain[1:]))
    # дедупликация
    seen, out = set(), []
    for a, b in segs:
        key = tuple(sorted((a, b)))
        if key not in seen:
            seen.add(key)
            out.append((a, b))
    return out


def on_segment(p, a, b, eps=0.01):
    (px, py), (ax, ay), (bx, by) = p, a, b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > eps * max(1, math.hypot(bx - ax, by - ay)):
        return False
    return min(ax, bx) - eps <= px <= max(ax, bx) + eps and min(ay, by) - eps <= py <= max(ay, by) + eps


# ---------------------------------------------------------------- main
def main() -> int:
    variant = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    src = variant / "easyeda" / "RP2040" / "RP2040.json"
    doc = json.load(open(src, encoding="utf-8"))
    shapes = doc["schematics"][0]["dataStr"]["shape"]

    comps, wires, flags, junctions, ncs = [], [], [], [], []
    for s in shapes:
        g = s.split("~")[0]
        if g == "LIB":
            c = parse_lib(s)
            if c["designator"] and c["pins"]:
                comps.append(c)
        elif g == "W":
            n = [float(v) for v in s.split("~")[1].split()]
            wires.append([snap_pt(n[i], n[i + 1]) for i in range(0, len(n) - 1, 2)])
        elif g == "F":
            flags.append(parse_flag(s))
        elif g == "J":
            t = s.split("~")
            junctions.append(snap_pt(float(t[1]), float(t[2])))
        elif g == "O":
            t = s.split("~")
            ncs.append((float(t[1]), float(t[2])))
    comps.sort(key=lambda c: (re.match(r"[A-Za-z]+", c["designator"]).group(0), int(re.sub(r"\D", "", c["designator"]) or 0)))

    # ---- дедупликация символов по канонической геометрии
    symbols = {}  # name -> sym
    sig2name = {}
    used = defaultdict(int)
    for c in comps:
        pins = sorted(
            ({k: p[k] for k in ("num", "name", "x", "y", "ang", "len", "name_show", "num_show")} for p in c["pins"]),
            key=lambda p: (p["num"]),
        )
        gfx = [g for g in c["gfx"]]
        base, pre = sym_name(c, used)
        sig = json.dumps([base, pins, gfx], sort_keys=True)
        if sig not in sig2name:
            name = base if used[base] == 0 else f"{base}_{used[base]}"
            used[base] += 1
            sig2name[sig] = name
            symbols[name] = {"pins": pins, "gfx": gfx, "value": base, "prefix": pre}
        c["sym"] = sig2name[sig]
    for n, s in POWER_SYMS.items():
        symbols[n] = dict(s, prefix="#PWR")

    # ---- узлы для разрезания проводов
    nodes = set()
    for c in comps:
        for p in c["pins"]:
            nodes.add(p["abs"])
    for pts in wires:
        nodes.update(pts)
    nodes.update(junctions)
    nodes.update((fl["x"], fl["y"]) for fl in flags)
    segs = split_segments(wires, nodes)

    root = U()
    L = []
    L.append("(kicad_sch\n  (version 20231120)\n  (generator \"easyeda2kicad\")\n  (generator_version \"2.0\")\n")
    L.append(f"  (uuid \"{root}\")\n  (paper \"A3\")\n")
    L.append(
        "  (title_block\n    (title \"BiBa — RP2040, 4× BTN7970 (brushed)\")\n"
        "    (date \"2026-05-08\")\n    (rev \"1.0\")\n"
        "    (comment 1 \"Конвертировано из EasyEDA (scripts/easyeda_sch2kicad.py)\")\n  )\n"
    )
    L.append("  (lib_symbols\n")
    for name, s in symbols.items():
        L.append(symbol_sexpr(f"{LIB}:{name}", s, s["prefix"], "    "))
    L.append("  )\n")

    # ---- компоненты
    for c in comps:
        rot = c["rot"]
        X, Y = sx(c["ax"]), sy(c["ay"])
        L.append(f"  (symbol (lib_id \"{LIB}:{c['sym']}\") (at {f(X)} {f(Y)} {rot}) (unit 1)\n")
        L.append(f"    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n    (uuid \"{U()}\")\n")
        for prop, text, t in (("Reference", c["designator"], c["ref_t"]), ("Value", c["value"], c["val_t"])):
            tx, ty, vis = text_center(t)
            hide = "" if t["show"] else " hide"
            L.append(
                f"    (property \"{prop}\" \"{esc(text)}\" (at {f(sx(tx))} {f(sy(ty))} {field_angle(vis, rot)})\n"
                f"      (effects (font (size 1.27 1.27)){hide}))\n"
            )
        a = c["attrs"]
        package = a.get("package", "")
        extra = {
            # имя то же, что даёт плате gen_pcb.py, иначе футпринт не найдётся
            "Footprint": f"{LIB}:{footprint_name(package)}" if package else "",
            "Datasheet": "",
            "Package": package,
            "LCSC": a.get("Supplier Part", ""),
            "MPN": a.get("Manufacturer Part", ""),
        }
        for k, v in extra.items():
            L.append(f"    (property \"{k}\" \"{esc(v)}\" (at {f(X)} {f(Y)} 0)\n      (effects (font (size 1.27 1.27)) hide))\n")
        for p in c["pins"]:
            L.append(f"    (pin \"{esc(p['num'])}\" (uuid \"{U()}\"))\n")
        L.append(f"    (instances (project \"{PROJ}\" (path \"/{root}\" (reference \"{c['designator']}\") (unit 1))))\n  )\n")

    # ---- флаги
    pwr_n = 0
    for fl in flags:
        X, Y = sx(fl["x"]), sy(fl["y"])
        if fl["kind"] in POWER_NAME:
            pwr_n += 1
            name = POWER_NAME[fl["kind"]]
            ref = f"#PWR{pwr_n:03d}"
            tx, ty, vis = text_center({"x": fl["tx"], "y": fl["ty"], "rot": fl["trot"], "text": fl["text"], "anchor": fl["anchor"]}, 9)
            L.append(
                f"  (symbol (lib_id \"{LIB}:{name}\") (at {f(X)} {f(Y)} {fl['rot']}) (unit 1)\n"
                f"    (exclude_from_sim no) (in_bom no) (on_board no) (dnp no)\n    (uuid \"{U()}\")\n"
                f"    (property \"Reference\" \"{ref}\" (at {f(X)} {f(Y)} 0) (effects (font (size 1.27 1.27)) hide))\n"
                f"    (property \"Value\" \"{esc(fl['text'])}\" (at {f(sx(tx))} {f(sy(ty))} {field_angle(vis, fl['rot'])})\n"
                f"      (effects (font (size 1.27 1.27))))\n"
                f"    (property \"Footprint\" \"\" (at {f(X)} {f(Y)} 0) (effects (font (size 1.27 1.27)) hide))\n"
                f"    (property \"Datasheet\" \"\" (at {f(X)} {f(Y)} 0) (effects (font (size 1.27 1.27)) hide))\n"
                f"    (pin \"1\" (uuid \"{U()}\"))\n"
                f"    (instances (project \"{PROJ}\" (path \"/{root}\" (reference \"{ref}\") (unit 1))))\n  )\n"
            )
        else:
            # netPort: у EasyEDA при rot=0 тело метки уходит влево от точки
            ang = (fl["rot"] + 180) % 360
            just = "left" if ang in (0, 90) else "right"
            L.append(
                f"  (global_label \"{esc(fl['text'])}\" (shape input) (at {f(X)} {f(Y)} {ang})\n"
                f"    (fields_autoplaced yes)\n"
                f"    (effects (font (size 1.27 1.27)) (justify {just}))\n    (uuid \"{U()}\")\n"
                f"    (property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\" (at {f(X)} {f(Y)} 0)\n"
                f"      (effects (font (size 1.27 1.27)) hide))\n  )\n"
            )

    # ---- провода, соединения, NC
    for a, b in segs:
        L.append(
            f"  (wire (pts (xy {f(sx(a[0]))} {f(sy(a[1]))}) (xy {f(sx(b[0]))} {f(sy(b[1]))}))\n"
            f"    (stroke (width 0) (type default))\n    (uuid \"{U()}\"))\n"
        )
    for x, y in junctions:
        L.append(f"  (junction (at {f(sx(x))} {f(sy(y))}) (diameter 0) (color 0 0 0 0)\n    (uuid \"{U()}\"))\n")
    for x, y in ncs:
        L.append(f"  (no_connect (at {f(sx(x))} {f(sy(y))}) (uuid \"{U()}\"))\n")

    L.append("  (sheet_instances\n    (path \"/\" (page \"1\"))\n  )\n)\n")

    (variant / f"{PROJ}.kicad_sch").write_text("".join(L), encoding="utf-8")

    pro = variant / f"{PROJ}.kicad_pro"
    try:
        json.loads(pro.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # .kicad_pro — это JSON; KiCad дополнит недостающие настройки сам
        pro.write_text(
            json.dumps({"meta": {"filename": pro.name, "version": 3}, "sheets": [[root, "Root"]]}, indent=2) + "\n",
            encoding="utf-8",
        )

    sym_dir = variant.parent.parent / "common" / "symbols"
    sym_dir.mkdir(parents=True, exist_ok=True)
    lib = ["(kicad_symbol_lib\n  (version 20231120)\n  (generator \"easyeda2kicad\")\n"]
    for name, s in symbols.items():
        lib.append(symbol_sexpr(name, s, s["prefix"]))
    lib.append(")\n")
    (sym_dir / f"{LIB}.kicad_sym").write_text("".join(lib), encoding="utf-8")

    print(
        f"Компонентов: {len(comps)}, символов: {len(symbols)}, проводов: {len(segs)} отрезков, "
        f"флагов: {len(flags)}, соединений: {len(junctions)}, NC: {len(ncs)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
