# -*- coding: utf-8 -*-
"""Расчёт силовых цепей платы KiCad по геометрии.

Считает для каждой силовой цепи: сопротивление дорожек, допустимый ток по
IPC-2221, а также волновое сопротивление микрополоска для справки.

Это расчёт, а не измерение: ток в полигонах не учитывается (для этого нужен
полевой решатель, у KiCad его нет), сопротивление тепловых спиц — тоже.
Разбор результатов — в kicad/variants/*/analysis/M1-driver-failure.md §7.

Запуск: python scripts/pcb_power_check.py <файл.kicad_pcb>

Нужен Python из состава KiCad (модуль pcbnew) — если запущен обычным
интерпретатором, перезапускает себя сам.
"""
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RHO_CU = 1.72e-8      # Ом*м, отожжённая медь при 20 C
MILS2_PER_MM2 = 1550.0
EPS_R = 4.5           # FR-4
POWER_NETS = ('VIN', 'GND', 'M1+', 'M1-', 'M2+', 'M2-', '+5V')
DELTA_T = (10, 20, 45)


def _kicad_root() -> Path:
    env = os.environ.get("KICAD_HOME")
    if env:
        return Path(env)
    for base in (Path(r"C:\Program Files\KiCad"), Path(r"C:\Program Files (x86)\KiCad"),
                 Path("/usr/lib/kicad"), Path("/Applications/KiCad/KiCad.app/Contents")):
        if base.is_dir():
            vers = sorted((p for p in base.iterdir() if re.match(r"^\d+\.\d+$", p.name)),
                          key=lambda p: [int(x) for x in p.name.split(".")], reverse=True)
            return vers[0] if vers else base
    raise SystemExit("KiCad не найден. Задайте KICAD_HOME на каталог установки.")


def _kicad_python() -> str:
    exe = "python" + (".exe" if os.name == "nt" else "")
    path = _kicad_root() / "bin" / exe
    if not path.exists():
        raise SystemExit("Не найден python KiCad. Задайте KICAD_HOME.")
    return str(path)


try:
    import pcbnew
except ImportError:
    if os.environ.get("BIBA_PCB_POWER_REEXEC"):
        raise SystemExit("В Python KiCad нет модуля pcbnew — проверьте установку.")
    env = dict(os.environ, BIBA_PCB_POWER_REEXEC="1", PYTHONIOENCODING="utf-8")
    cmd = [_kicad_python(), os.path.abspath(__file__)] + sys.argv[1:]
    raise SystemExit(subprocess.run(cmd, env=env, check=False).returncode)


def _stackup_layer(pcb_path: str, name: str, kind: str):
    """Толщина слоя стекапа из текста .kicad_pcb, мм.

    pcbnew отдаёт GetStackupDescriptor() необёрнутым SwigPyObject —
    прочитать стекап через Python API нельзя, поэтому разбираем файл.
    """
    text = Path(pcb_path).read_text(encoding="utf-8")
    m = re.search(r'\(stackup\b.*?\n\t\t\)\n', text, re.DOTALL)
    if not m:
        return None
    block = m.group(0)
    pat = (r'\(layer\s+"%s"\s*\n\s*\(type\s+"%s"\)\s*\n\s*\(thickness\s+([\d.]+)\)'
           % (re.escape(name), kind))
    hit = re.search(pat, block, re.IGNORECASE)
    return float(hit.group(1)) if hit else None


def copper_thickness(pcb_path: str) -> float:
    """Толщина меди внешнего слоя в мм; без стекапа — 1 oz с предупреждением."""
    t = _stackup_layer(pcb_path, "F.Cu", "copper")
    if t:
        return t
    sys.stderr.write("ВНИМАНИЕ: стекап не задан, медь принята 35 мкм (1 oz)\n")
    return 0.035


def ipc_current(w_mm: float, t_mm: float, dt: float) -> float:
    """IPC-2221, внешний слой: I = 0.048 * dT^0.44 * A^0.725 (A в мил^2)."""
    area = w_mm * t_mm * MILS2_PER_MM2
    return 0.048 * (dt ** 0.44) * (area ** 0.725)


def width_for(current: float, t_mm: float, dt: float) -> float:
    area = (current / (0.048 * dt ** 0.44)) ** (1 / 0.725)
    return area / MILS2_PER_MM2 / t_mm


def resistance(w_mm: float, l_mm: float, t_mm: float) -> float:
    """Сопротивление дорожки, Ом."""
    return RHO_CU * (l_mm / 1000.0) / ((w_mm / 1000.0) * (t_mm / 1000.0))


def z0_microstrip(w_mm: float, h_mm: float, t_mm: float) -> float:
    return 87 / math.sqrt(EPS_R + 1.41) * math.log(5.98 * h_mm / (0.8 * w_mm + t_mm))


def dielectric_height(pcb_path: str) -> float:
    """Толщина диэлектрика между слоями, мм."""
    return _stackup_layer(pcb_path, "dielectric 1", "core") or 1.51


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        raise SystemExit("Укажите файл платы: pcb_power_check.py <файл.kicad_pcb>")

    pcb_path = sys.argv[1]
    board = pcbnew.LoadBoard(pcb_path)
    t_cu = copper_thickness(pcb_path)
    h = dielectric_height(pcb_path)
    print("Медь %.0f мкм (%.1f oz), диэлектрик %.2f мм, отожжённая медь при 20 C."
          % (t_cu * 1000, t_cu / 0.035, h))
    print("Полигоны в расчёт НЕ входят — ток в заливке отсюда не считается.\n")

    seg = defaultdict(lambda: defaultdict(float))
    vias = defaultdict(int)
    for t in board.GetTracks():
        net = t.GetNetname()
        if net not in POWER_NETS:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            vias[net] += 1
            continue
        s, e = t.GetStart(), t.GetEnd()
        seg[net][round(t.GetWidth() / 1e6, 3)] += ((s.x - e.x) ** 2 + (s.y - e.y) ** 2) ** 0.5 / 1e6

    hdr = "%-5s %7s %9s %9s" % ("цепь", "ширина", "длина", "R")
    hdr += "".join("%8s" % ("I@%dC" % d) for d in DELTA_T)
    print(hdr)
    print("%-5s %7s %9s %9s%s" % ("", "мм", "мм", "мОм", "".join("%8s" % "А" for _ in DELTA_T)))
    for net in POWER_NETS:
        if net not in seg:
            continue
        for w in sorted(seg[net], reverse=True):
            length = seg[net][w]
            row = "%-5s %7.2f %9.1f %9.2f" % (net, w, length,
                                              resistance(w, length, t_cu) * 1000)
            row += "".join("%8.1f" % ipc_current(w, t_cu, d) for d in DELTA_T)
            print(row)
        print("%-5s %7s %9.1f %9s  переходных: %d"
              % ("", "", sum(seg[net].values()), "", vias[net]))

    print("\nТребуемая ширина по IPC-2221 (внешний слой):")
    for current, dt in ((21, 20), (21, 45), (50, 45)):
        print("  %3d А при dT=%2d C -> %5.1f мм" % (current, dt, width_for(current, t_cu, dt)))

    print("\nВолновое сопротивление микрополоска над сплошным GND (справочно —"
          "\nдля ШИМ 20 кГц и UART не критерий):")
    for w in (0.25, 0.5, 1.0, 1.5, 4.0):
        print("  ширина %4.2f мм -> Z0 = %5.1f Ом" % (w, z0_microstrip(w, h, t_cu)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
