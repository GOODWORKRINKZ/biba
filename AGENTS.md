# AGENTS.md — инструкция для ИИ-агентов (Claude Code, GitHub Copilot и др.)

Краткая карта репозитория BiBa и правила работы с аппаратной частью (KiCad).

## Проект в двух словах

BiBa — двухколёсный полевой робот. Есть несколько вариантов привода
(коллекторные / бесколлекторные моторы) и несколько платформ управления
(Raspberry Pi, RP2040). Прошивка — C (PlatformIO), высокоуровневый
контроллер — Python.

## Точки входа

- `firmware/` — прошивка RP2040 (PlatformIO), таргеты и HAL.
- `biba-controller/` — Python-контроллер (работает на Pi/роботе).
- `docs/` — архитектура, проводка, варианты железа, ADR.
- `kicad/` — KiCad-проекты (схемы и платы), см. `kicad/README.md`.
- `.planning/` — фазы разработки, исследования, решения.
- `tests/` — pytest.

## Канонические источники по железу (читай ПЕРЕД правкой схем)

1. `firmware/targets/<target>/target.md` — распиновка и назначение пинов.
2. `firmware/targets/<target>/target.h` — **истина по пинам** (define'ы GPIO).
3. `docs/variants.md` — матрица вариантов (платформа / мотор / драйвер / статус).
4. `docs/wiring.md` — проводка Raspberry Pi-варианта.

Правило: схема в `kicad/` обязана соответствовать `target.h`. Меняешь пин —
меняешь и `target.h`, и схему, и `target.md`.

## KiCad: как пользоваться

- Установлен **KiCad 10.0.3**: `C:\Program Files\KiCad\10.0`
  (`kicad-cli.exe`, `python.exe` 3.11.5).
- MCP-сервер: **KiCAD-MCP-Server** (mixelpixx) лежит в
  `C:\Users\krikz\KiCAD-MCP-Server`, подключён к VS Code через
  `.vscode/mcp.json` (сервер `KiCAD-MCP-Server`). VS Code подхватывает его
  автоматически; после правки конфига — перезагрузить окно
  (`Developer: Reload Window`).
- Все KiCad-файлы живут в `kicad/`. Каждый вариант схемы — отдельный
  KiCad-проект в `kicad/variants/<name>/`.

### Headless (без GUI), через `kicad-cli`

```powershell
kicad-cli sch export netlist --format kicadxml -o out.xml board.kicad_sch
kicad-cli sch export python-bom -o bom.xml board.kicad_sch
kicad-cli sch erc -o erc.rpt board.kicad_sch
kicad-cli pcb drc -o drc.rpt board.kicad_pcb
kicad-cli pcb render -o render.png board.kicad_pcb
kicad-cli pcb export gerbers -o gerber/ board.kicad_pcb
```

### Через MCP (живой KiCad или headless)

Сервер умеет: создать проект, редактировать схему (компоненты, связи, метки),
генерировать символы и футпринты, расставлять компоненты, трассировать,
ERC/DRC, экспорт (BOM/герберы), снапшоты схемы и платы.

Держи KiCad запущенным с открытым проектом — сервер по умолчанию подключается
к работающему экземпляру (IPC-бэкенд `kipy`); иначе работает headless через
`pcbnew` (SWIG-бэкенд).

## Соглашения

- Документация — на русском.
- План каждого варианта — `kicad/variants/<name>/README.md` (держи актуальным).
- Общие библиотеки (символы/футпринты/3D) — только в `kicad/common/`,
  не дублируй по вариантам.
