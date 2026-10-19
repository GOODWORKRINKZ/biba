#!/usr/bin/env python3
"""Обновить плату KiCad из схемы без GUI (аналог «Update PCB from Schematic»).

Что делает:
  1. `kicad-cli sch export netlist --format kicadxml` по корневому листу варианта.
  2. Для каждого символа схемы ищет футпринт на плате по позиционному
     обозначению (reference):
       - нет на плате        → подгружает из библиотеки и ставит по
                               `placement.json` либо на «парковку» справа от платы;
       - другой футпринт     → заменяет, сохраняя позицию/поворот/сторону;
       - есть                → обновляет значение, lib-id и путь к символу (UUID).
  3. Переназначает цепи всем пинам по нетлисту (новые цепи создаются),
     неподключённые пины получают цепи `unconnected-(...)`, как в GUI.
  4. Применяет `board_only_nets` из `placement.json` (цепи у площадок,
     которых нет в схеме, например клеммы батареи).
  5. Удаляет неиспользуемые цепи, перезаливает полигоны, сохраняет плату.
  6. Печатает отчёт: добавлено / заменено / изменённые цепи у площадок
     (это места, где дорожки надо перетрассировать) / лишние футпринты.

Запуск: python scripts/pcb_update_from_sch.py kicad/variants/<name> [--dry-run]
                                                     [--force-place] [--remove-extra]

`placement.json` (рядом с платой, необязателен):
  {
    "place":           {"Q1": [x_mm, y_mm, rot_deg, "F.Cu"], ...},
    "board_only_nets": {"Pad_gge6837": {"*": "BAT+"}, ...}
  }
`place` применяется только к новым футпринтам (с `--force-place` — ко всем
перечисленным). `--remove-extra` удаляет с платы футпринты, которых нет в
схеме (кроме board-only: крепёж, площадки). Нужен Python из состава KiCad (модуль pcbnew); при запуске
системным Python скрипт перезапустит себя интерпретатором KiCad
(каталог ищется по KICAD_HOME либо стандартным путям).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------
# Bootstrap: pcbnew есть только в Python KiCad
# --------------------------------------------------------------------------


def _kicad_home() -> Path:
    env = os.environ.get("KICAD_HOME")
    cands = [Path(env)] if env else []
    cands += [Path(r"C:\Program Files\KiCad\10.0"), Path(r"C:\Program Files\KiCad\9.0"),
              Path("/usr"), Path("/Applications/KiCad/KiCad.app/Contents")]
    for c in cands:
        if (c / "bin").exists():
            return c
    raise SystemExit("KiCad не найден. Задайте KICAD_HOME.")


def _kicad_bin(name: str) -> str:
    home = _kicad_home()
    for p in (home / "bin" / f"{name}.exe", home / "bin" / name, home / "MacOS" / name):
        if p.exists():
            return str(p)
    raise SystemExit(f"Не найден {name} в {home}")


try:
    import pcbnew  # type: ignore
except ImportError:
    if os.environ.get("_PCB_UPDATE_REEXEC"):
        raise SystemExit("В Python KiCad нет модуля pcbnew — проверьте установку.")
    os.environ["_PCB_UPDATE_REEXEC"] = "1"
    sys.exit(subprocess.call([_kicad_bin("python"), os.path.abspath(__file__)] + sys.argv[1:]))

REPO = Path(__file__).resolve().parents[1]
MM = 1_000_000


def mm(v: float) -> int:
    return int(round(v * MM))


# --------------------------------------------------------------------------
# Нетлист
# --------------------------------------------------------------------------


def export_netlist(sch: Path) -> ET.Element:
    out = Path(tempfile.mkdtemp()) / "net.xml"
    subprocess.run([_kicad_bin("kicad-cli"), "sch", "export", "netlist", "--format", "kicadxml",
                    "-o", str(out), str(sch)], check=True, capture_output=True)
    return ET.parse(out).getroot()


def read_components(root: ET.Element) -> dict[str, dict]:
    comps = {}
    for c in root.iter("comp"):
        ref = c.get("ref")
        if ref.startswith("#"):
            continue
        sp = c.find("sheetpath")
        sheet = sp.get("tstamps", "/") if sp is not None else "/"
        ts = (c.findtext("tstamps") or "").split()
        comps[ref] = {
            "value": c.findtext("value") or "",
            "footprint": c.findtext("footprint") or "",
            "path": sheet.rstrip("/") + "/" + (ts[0] if ts else ""),
        }
    return comps


def read_nets(root: ET.Element) -> dict[tuple[str, str], str]:
    """(ref, pin) -> имя цепи."""
    pins = {}
    for n in root.iter("net"):
        for node in n.findall("node"):
            pins[(node.get("ref"), node.get("pin"))] = n.get("name")
    return pins


# --------------------------------------------------------------------------
# Футпринты
# --------------------------------------------------------------------------


def fp_lib_dirs(variant: Path) -> dict[str, Path]:
    libs: dict[str, Path] = {}
    std = _kicad_home() / "share" / "kicad" / "footprints"
    if std.exists():
        for d in std.glob("*.pretty"):
            libs[d.stem] = d
    table = variant / "fp-lib-table"
    if table.exists():
        import re
        for m in re.finditer(r'\(name "([^"]+)"\).*?\(uri "([^"]+)"\)', table.read_text(encoding="utf-8")):
            uri = m.group(2).replace("${KIPRJMOD}", str(variant))
            libs[m.group(1)] = Path(uri)
    libs.setdefault("biba", REPO / "kicad" / "common" / "footprints" / "biba.pretty")
    return libs


def load_footprint(libs: dict[str, Path], fpid: str):
    if ":" in fpid:
        lib, name = fpid.split(":", 1)
    else:
        lib, name = "biba", fpid
    d = libs.get(lib)
    if d is None or not d.exists():
        raise SystemExit(f"Библиотека футпринтов {lib!r} не найдена (для {fpid})")
    fp = pcbnew.FootprintLoad(str(d), name)
    if fp is None:
        raise SystemExit(f"Футпринт {fpid} не найден в {d}")
    return fp


def fp_name(fpid: str) -> str:
    return fpid.split(":", 1)[1] if ":" in fpid else fpid


def place(fp, x: float, y: float, rot: float, layer: str):
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    if layer == "B.Cu" and fp.GetLayerName() != "B.Cu":
        try:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        except AttributeError:
            fp.Flip(fp.GetPosition(), False)
    fp.SetOrientationDegrees(rot)


# --------------------------------------------------------------------------
# Основная процедура
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    dry = "--dry-run" in argv
    force_place = "--force-place" in argv
    remove_extra = "--remove-extra" in argv
    if len(args) != 1:
        print(__doc__)
        return 2
    variant = Path(args[0]).resolve()
    name = variant.name
    sch = variant / f"{name}.kicad_sch"
    pcb = variant / f"{name}.kicad_pcb"
    if not sch.exists() or not pcb.exists():
        raise SystemExit(f"Нет {sch.name} или {pcb.name} в {variant}")

    cfg = {}
    pj = variant / "placement.json"
    if pj.exists():
        cfg = json.loads(pj.read_text(encoding="utf-8"))
    placement: dict = cfg.get("place", {})
    board_only_nets: dict = cfg.get("board_only_nets", {})

    root = export_netlist(sch)
    comps = read_components(root)
    pin_nets = read_nets(root)
    libs = fp_lib_dirs(variant)

    board = pcbnew.LoadBoard(str(pcb))
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}

    added, replaced, value_changed, unplaced = [], [], [], []

    # парковка новых футпринтов: справа от платы
    edge = board.GetBoardEdgesBoundingBox()
    park_x0 = edge.GetRight() / MM + 6.0
    park_y0 = edge.GetY() / MM + 3.0
    park_i = 0

    for ref, info in comps.items():
        fp = by_ref.get(ref)
        want = info["footprint"]
        if fp is not None and want and fp_name(fp.GetFPIDAsString()) != fp_name(want):
            new = load_footprint(libs, want)
            new.SetPosition(fp.GetPosition())
            new.SetOrientation(fp.GetOrientation())
            if fp.GetLayerName() == "B.Cu":
                place(new, fp.GetPosition().x / MM, fp.GetPosition().y / MM,
                      fp.GetOrientationDegrees(), "B.Cu")
            replaced.append((ref, fp.GetFPIDAsString(), want))
            board.Remove(fp)
            fp = new
            board.Add(fp)
            by_ref[ref] = fp
            if force_place and ref in placement:
                place(fp, *placement[ref])
        elif fp is None:
            if not want:
                print(f"!! {ref}: в схеме нет футпринта, пропущен")
                continue
            fp = load_footprint(libs, want)
            board.Add(fp)
            by_ref[ref] = fp
            if ref in placement:
                place(fp, *placement[ref])
            else:
                place(fp, park_x0 + (park_i % 8) * 7.0, park_y0 + (park_i // 8) * 7.0, 0, "F.Cu")
                park_i += 1
                unplaced.append(ref)
            added.append((ref, want))
        elif force_place and ref in placement:
            place(fp, *placement[ref])

        fp.SetReference(ref)
        if fp.GetValue() != info["value"]:
            value_changed.append((ref, fp.GetValue(), info["value"]))
            fp.SetValue(info["value"])
        if want and fp.GetFPIDAsString() != want:
            fp.SetFPID(pcbnew.LIB_ID(*want.split(":", 1)) if ":" in want else pcbnew.LIB_ID("", want))
        fp.SetPath(pcbnew.KIID_PATH(info["path"]))

    # --- цепи --------------------------------------------------------------
    def net_item(name: str):
        if not name:
            return None
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        return ni

    net_changed = []
    for ref, fp in by_ref.items():
        if ref not in comps:
            continue
        for pad in fp.Pads():
            new_name = pin_nets.get((ref, pad.GetNumber()), "")
            old_name = pad.GetNetname()
            if old_name != new_name:
                if old_name and not old_name.startswith("unconnected-") and ref not in [a[0] for a in added]:
                    net_changed.append((f"{ref}.{pad.GetNumber()}", old_name, new_name))
                ni = net_item(new_name)
                if ni is None:
                    pad.SetNetCode(0)
                else:
                    pad.SetNet(ni)

    for ref, pads in board_only_nets.items():
        fp = by_ref.get(ref)
        if fp is None:
            print(f"!! board_only_nets: {ref} нет на плате")
            continue
        for pad in fp.Pads():
            nn = pads.get(pad.GetNumber(), pads.get("*"))
            if nn and pad.GetNetname() != nn:
                net_changed.append((f"{ref}.{pad.GetNumber()}", pad.GetNetname(), nn))
                pad.SetNet(net_item(nn))

    # чистые переименования цепей (например, IC1_35 -> Net-(IC1-GP29) после
    # импорта из EasyEDA) отделяем от настоящих пересадок площадок
    remaining = {pad.GetNetname() for fp in by_ref.values() for pad in fp.Pads()}
    news_by_old: dict[str, set[str]] = {}
    for _, a, b in net_changed:
        news_by_old.setdefault(a, set()).add(b)
    renamed = {a: next(iter(n)) for a, n in news_by_old.items()
               if len(n) == 1 and a not in remaining}
    net_changed = [c for c in net_changed if c[1] not in renamed]

    # дорожки/полигоны получают цепи от площадок, к которым они подключены
    board.BuildConnectivity()
    board.GetConnectivity().PropagateNets()

    extra = [r for r, fp in by_ref.items()
             if r not in comps and not (fp.GetAttributes() & pcbnew.FP_BOARD_ONLY)]
    removed_extra = []
    if remove_extra and not dry:
        for r in extra:
            board.Remove(by_ref[r])
            removed_extra.append(r)
        extra = []

    # --- отчёт -------------------------------------------------------------
    print(f"Схема: {len(comps)} компонентов; плата: {len(by_ref)} футпринтов")
    print(f"Добавлено ({len(added)}):")
    for ref, f in added:
        print(f"  + {ref:6} {f}" + ("   [парковка]" if ref in unplaced else ""))
    print(f"Заменён футпринт ({len(replaced)}):")
    for ref, a, b in replaced:
        print(f"  ~ {ref:6} {a} -> {b}")
    print(f"Изменено значение ({len(value_changed)}):")
    for ref, a, b in value_changed:
        print(f"  = {ref:6} {a!r} -> {b!r}")
    print(f"Переименованные цепи ({len(renamed)}): " + ", ".join(f"{a}->{b}" for a, b in sorted(renamed.items())))
    print(f"Площадки сменили цепь — дорожки к ним надо перетрассировать ({len(net_changed)}):")
    for p, a, b in net_changed:
        print(f"  * {p:14} {a!r} -> {b!r}")
    if extra:
        print(f"На плате, но не в схеме (не тронуты; --remove-extra удалит): {', '.join(extra)}")
    if removed_extra:
        print(f"Удалены с платы (нет в схеме): {', '.join(removed_extra)}")

    if dry:
        print("--dry-run: плата не сохранена")
        return 0

    try:
        board.RemoveUnusedNets(None)
    except Exception as e:  # noqa: BLE001
        print(f"(RemoveUnusedNets не удалось: {e})")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(pcb), board)
    print(f"Сохранено: {pcb}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
