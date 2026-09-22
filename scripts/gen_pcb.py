# -*- coding: utf-8 -*-
"""Генерация платы KiCad из исходника EasyEDA (PCB_RP2040.json).

Импорт делает штатный конвертер KiCad (`kicad-cli pcb import`, формат
EasyEDA / JLCEDA Std) — свой парсер не пишем. Дальше плата приводится к
виду, пригодному для работы в репозитории:

  - слоям возвращаются канонические имена KiCad (EasyEDA-псевдонимы
    TopLayer/BottomLayer/... убираются);
  - футпринты получают библиотечный префикс `biba:` и выгружаются в
    `kicad/common/footprints/biba.pretty/` — схема ссылается именно туда;
  - свободные пады и отверстия EasyEDA (переходные массивы под моторными
    выходами, крепёж, силовые клеммы) помечаются board-only, чтобы не
    попадать в BOM/pos-файлы и не мешать синхронизации со схемой.

Пишет в <variant>/: brushed-bts7960.kicad_pcb, fp-lib-table.

Запуск: python scripts/gen_pcb.py <каталог_variant>

Скрипту нужен Python из состава KiCad (модуль pcbnew) — если запущен
обычным интерпретатором, перезапускает себя сам.
"""
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

PROJ_NAME = "brushed-bts7960"
SRC_PCB = Path("easyeda") / "RP2040" / "PCB_RP2040.json"
FP_LIB = "biba"

# Внутренняя единица EasyEDA — 10 мил.
MIL10_MM = 0.254

# Свободные пады/отверстия EasyEDA — KiCad заводит под них псевдо-футпринты
# с обозначениями Pad_ggeNNNN / Hole_ggeNNNN.
FREE_ITEM_RE = re.compile(r"^(Pad|Hole)_gge\d+$")


# --- поиск KiCad ---------------------------------------------------------

def _kicad_root() -> Path:
    """Каталог установки KiCad (переменная KICAD_HOME либо стандартные пути)."""
    env = os.environ.get("KICAD_HOME")
    if env:
        return Path(env)
    candidates = [
        Path(r"C:\Program Files\KiCad"),
        Path(r"C:\Program Files (x86)\KiCad"),
        Path("/usr/lib/kicad"),
        Path("/Applications/KiCad/KiCad.app/Contents"),
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        # версии лежат подкаталогами (10.0, 9.0, ...) — берём старшую
        vers = sorted((p for p in base.iterdir() if re.match(r"^\d+\.\d+$", p.name)),
                      key=lambda p: [int(x) for x in p.name.split(".")], reverse=True)
        return vers[0] if vers else base
    raise SystemExit("KiCad не найден. Задайте KICAD_HOME на каталог установки.")


def _kicad_bin(name: str) -> str:
    """Путь к утилите строго из каталога установки KiCad."""
    exe = name + (".exe" if os.name == "nt" else "")
    path = _kicad_root() / "bin" / exe
    if not path.exists():
        raise SystemExit(f"Не найден {name}. Задайте KICAD_HOME на каталог установки KiCad.")
    return str(path)


def _tool(name: str) -> str:
    """Путь к утилите KiCad: сначала PATH, потом каталог установки.

    Для `python` не годится — на PATH почти наверняка системный
    интерпретатор без pcbnew; там нужен _kicad_bin.
    """
    return shutil.which(name) or _kicad_bin(name)


def _reexec_under_kicad_python() -> None:
    """Перезапустить себя интерпретатором KiCad, если нет pcbnew.

    os.exec* на Windows отвязывает консоль, поэтому именно subprocess.
    """
    if os.environ.get("BIBA_GEN_PCB_REEXEC"):
        raise SystemExit("В Python KiCad нет модуля pcbnew — проверьте установку.")
    env = dict(os.environ, BIBA_GEN_PCB_REEXEC="1", PYTHONIOENCODING="utf-8")
    cmd = [_kicad_bin("python"), os.path.abspath(__file__)] + sys.argv[1:]
    raise SystemExit(subprocess.run(cmd, env=env, check=False).returncode)


try:
    import pcbnew
except ImportError:
    _reexec_under_kicad_python()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from easyeda_netlist import footprint_name


# --- шаги обработки ------------------------------------------------------

def run_import(src: Path, dst: Path) -> None:
    """Импорт EasyEDA Std -> .kicad_pcb штатным конвертером KiCad."""
    cmd = [_tool("kicad-cli"), "pcb", "import", "--format", "auto",
           "-o", str(dst), str(src)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0 or not dst.exists():
        sys.stderr.write(res.stdout + res.stderr)
        raise SystemExit(f"kicad-cli pcb import завершился с кодом {res.returncode}")


def reset_layer_names(board) -> int:
    """Убрать EasyEDA-псевдонимы слоёв, вернув имена KiCad по умолчанию."""
    changed = 0
    for lid in board.GetEnabledLayers().Seq():
        std = pcbnew.LayerName(lid)
        if board.GetLayerName(lid) != std:
            board.SetLayerName(lid, std)
            changed += 1
    return changed


def is_free_item(fp) -> bool:
    return bool(FREE_ITEM_RE.match(fp.GetReference()))


def mark_free_items(board) -> int:
    """Свободные пады/отверстия — только плата: мимо BOM и pos-файлов."""
    flags = (pcbnew.FP_BOARD_ONLY
             | pcbnew.FP_EXCLUDE_FROM_BOM
             | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    count = 0
    for fp in board.GetFootprints():
        if is_free_item(fp):
            fp.SetAttributes(fp.GetAttributes() | flags)
            count += 1
    return count


def relink_footprints(board) -> dict:
    """Префикс библиотеки biba + чистые имена. -> {designator: имя}."""
    mapping = {}
    for fp in board.GetFootprints():
        if is_free_item(fp):
            continue
        name = footprint_name(fp.GetFPID().GetUniStringLibItemName())
        fp.SetFPID(pcbnew.LIB_ID(FP_LIB, name))
        # обозначение, продублированное текстом на шелкографии, делаем
        # подстановкой — иначе футпринт в библиотеке унесёт чужой designator
        for item in fp.GraphicalItems():
            text = item.Cast()
            if isinstance(text, pcbnew.PCB_TEXT) and text.GetText() == fp.GetReference():
                text.SetText("${REFERENCE}")
        mapping[fp.GetReference()] = name
    return mapping


def _lib_copy(fp, name):
    """Экземпляр с платы -> футпринт для библиотеки.

    Без сдвига в начало координат KiCad считает футпринт на плате
    отличающимся от библиотечного (lib_footprint_mismatch).
    """
    copy = pcbnew.FOOTPRINT(fp)
    copy.SetPosition(pcbnew.VECTOR2I(0, 0))
    copy.SetReference("REF**")
    copy.SetValue(name)
    return copy


def export_footprint_lib(board, lib_dir: Path) -> int:
    """Выгрузить по одному экземпляру каждого футпринта в biba.pretty.

    Одноимённые футпринты в исходнике EasyEDA расходятся на доли микрона и
    сдвинутыми подписями, поэтому эталоном берём тот экземпляр, с которым
    совпадает больше всего остальных — так меньше лишних предупреждений
    lib_footprint_mismatch. Порядок обхода фиксирован, иначе выбор эталона
    (а с ним и содержимое библиотеки) меняется от запуска к запуску.
    """
    if lib_dir.exists():
        shutil.rmtree(lib_dir)
    lib_dir.mkdir(parents=True)

    groups = {}
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if not is_free_item(fp):
            groups.setdefault(fp.GetFPID().GetUniStringLibItemName(), []).append(fp)

    io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    for name, instances in groups.items():
        best, best_score = instances[0], -1
        for candidate in instances:
            probe = _lib_copy(candidate, name)
            score = sum(not other.FootprintNeedsUpdate(probe) for other in instances)
            if score > best_score:
                best, best_score = candidate, score
        io.FootprintSave(str(lib_dir), _lib_copy(best, name))
        freeze_uuids(lib_dir / f"{name}.kicad_mod", name)
    return len(groups)


def freeze_uuids(path: Path, seed: str) -> None:
    """Заменить случайные UUID на детерминированные.

    KiCad выдаёт новые UUID при каждой записи — без этого повторная
    генерация библиотеки даёт пустой по смыслу, но огромный diff.
    """
    counter = itertools.count()
    text = re.sub(
        r'\(uuid "[0-9a-fA-F-]{36}"\)',
        lambda _: f'(uuid "{uuid.uuid5(uuid.NAMESPACE_URL, f"biba/{seed}/{next(counter)}")}")',
        path.read_text(encoding="utf-8"),
    )
    path.write_text(text, encoding="utf-8")


def fill_zones(board) -> bool:
    """Перезалить полигоны.

    Импортёр переносит контуры COPPERAREA как есть, без вырезов под
    чужие цепи, поэтому без перезаливки DRC видит сотни пересечений.
    """
    return pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def apply_design_rules(variant: Path, src: Path) -> list:
    """Перенести DRCRULE из EasyEDA в классы цепей проекта KiCad.

    Импортёр правила не переносит, и плата остаётся с дефолтами KiCad
    (зазор 0.2 мм), под которые она не разводилась: в EasyEDA зазор
    0.152 мм. Без этого DRC ругается на исходную, корректную трассировку.
    """
    rules = json.loads(src.read_text(encoding="utf-8")).get("DRCRULE") or {}
    pro_path = variant / f"{PROJ_NAME}.kicad_pro"
    pro = json.loads(pro_path.read_text(encoding="utf-8")) if pro_path.exists() else {}

    settings = pro.setdefault("net_settings", {})
    base = (settings.get("classes") or [{}])[0]
    classes, patterns, applied = [], [], []

    for name, rule in rules.items():
        if not isinstance(rule, dict) or "trackWidth" not in rule:
            continue  # isRealtime и прочие флаги редактора
        cls = dict(base)
        cls["name"] = "Default" if name == "Default" else name
        cls["track_width"] = round(rule["trackWidth"] * MIL10_MM, 4)
        cls["clearance"] = round(rule["clearance"] * MIL10_MM, 4)
        cls["via_diameter"] = round(rule["viaHoleDiameter"] * MIL10_MM, 4)
        cls["via_drill"] = round(rule["viaHoleD"] * MIL10_MM, 4)
        classes.append(cls)
        for net in rule.get("nets") or []:
            patterns.append({"netclass": cls["name"], "pattern": net})
        applied.append(f"{cls['name']}: дорожка {cls['track_width']} мм, "
                       f"зазор {cls['clearance']} мм, via {cls['via_diameter']}/{cls['via_drill']} мм")

    if classes:
        classes.sort(key=lambda c: c["name"] != "Default")
        settings["classes"] = classes
        settings["netclass_patterns"] = patterns
        settings.setdefault("meta", {"version": 5})
        pro_path.write_text(json.dumps(pro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return applied


def write_fp_lib_table(variant: Path, lib_dir: Path) -> None:
    uri = lib_dir.resolve().as_posix()
    (variant / "fp-lib-table").write_text(
        "(fp_lib_table\n  (version 7)\n"
        f"  (lib (name \"{FP_LIB}\")(type \"KiCad\")(uri \"{uri}\")(options \"\")"
        "(descr \"BiBa project footprints\"))\n)\n",
        encoding="utf-8",
    )


def run_drc(pcb: Path) -> dict:
    """DRC штатной утилитой; возвращает разобранный JSON-отчёт."""
    report = pcb.with_suffix(".drc.json")
    cmd = [_tool("kicad-cli"), "pcb", "drc", "--format", "json",
           "--severity-error", "--severity-warning", "-o", str(report), str(pcb)]
    subprocess.run(cmd, capture_output=True, text=True, check=False)
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    report.unlink(missing_ok=True)
    return data


def print_drc(data: dict) -> None:
    from collections import Counter
    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    print("\n=== DRC ===")
    print("Нарушений:", len(violations), " Неразведённых пар:", len(unconnected))
    counts = Counter((v["severity"], v["type"]) for v in violations)
    for (severity, kind), n in counts.most_common():
        print(f"  {n:4d}  {severity:7s} {kind}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    variant = Path(args[0] if args else ".").resolve()
    src = variant / SRC_PCB
    if not src.exists():
        raise SystemExit(f"Нет исходника EasyEDA: {src}")

    # импорт разовый: плата дальше ведётся в KiCad, перезапуск сотрёт правки
    pcb_path = variant / f"{PROJ_NAME}.kicad_pcb"
    if pcb_path.exists() and "--force" not in sys.argv:
        raise SystemExit(
            f"{pcb_path.name} уже существует. Импорт из EasyEDA — разовый:\n"
            f"  плата ведётся в KiCad, повторный запуск сотрёт правки и разводку.\n"
            f"  Если это действительно нужно: gen_pcb.py <variant> --force"
        )
    run_import(src, pcb_path)

    board = pcbnew.LoadBoard(str(pcb_path))
    layers = reset_layer_names(board)
    free = mark_free_items(board)
    mapping = relink_footprints(board)

    lib_dir = variant.parent.parent / "common" / "footprints" / f"{FP_LIB}.pretty"
    uniq = export_footprint_lib(board, lib_dir)
    filled = fill_zones(board)
    board.Save(str(pcb_path))

    write_fp_lib_table(variant, lib_dir)
    rules = apply_design_rules(variant, src)

    print("Плата:", pcb_path)
    print("Компонентов:", len(mapping))
    print("Свободных падов/отверстий (board-only):", free)
    print("Футпринтов в библиотеке:", uniq, "->", lib_dir)
    print("Слоёв переименовано:", layers)
    print("Полигоны залиты:", "да" if filled else "нет")
    for line in rules:
        print("Класс цепей", line)

    print_drc(run_drc(pcb_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
