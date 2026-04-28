# Documentation refactor and compose relocation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Превратить документацию проекта в hub, отражающий три аппаратные композиции (Pi-only / STM32-only / Pi+STM32), и физически перенести текущий `docker-compose.yml` из корня в `docker/legacy-pi/`, обновив все скрипты, systemd-unit, тесты и CI-ссылки так, чтобы `bbupdate` и автозапуск продолжали работать без регрессий.

**Architecture:**
1. Каталог `docker/` создаётся в корне; туда переезжает текущий compose в `docker/legacy-pi/`, и заводятся пустые placeholder'ы `docker/base/` и `docker/ros2/` с README-заглушками.
2. Все обращения к `docker-compose.yml` (биба-алиасы, `update.sh`, `diagnostics.sh`, systemd unit в `setup_node.sh`, тесты) централизуются вокруг новой переменной `BIBA_COMPOSE_FILE`, по умолчанию указывающей на `$BIBA_DIR/docker/legacy-pi/docker-compose.yml`.
3. README переписывается как архитектурный hub с матрицей композиций; добавляются `docs/system_architecture.md` (детальный обзор) и `docs/ros2_stack.md` (заглушка-структура); `deployment.md` расщепляется на разделы per-композиция; `stm32_architecture.md` получает cross-link.
4. Опорный дизайн — [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](2026-04-28-sbc-architecture-redesign-design.md).

**Tech Stack:** Markdown, Bash, Docker Compose v2, systemd, pytest.

---

## Pre-flight

Перед стартом убедиться, что baseline зелёный:

```bash
cd /home/ros2/Downloads/biba
python3 -m pytest tests/test_config.py tests/test_biba_aliases.py tests/test_setup_node.py -q
```
Expected: `40 passed` (или больше, если тесты добавятся — но не меньше).

Все правки делаются на текущей ветке `copilot/add-stm32f103-hardware-support`, начиная с HEAD `c6d6651`.

---

### Task 1: Создать каталог `docker/` со скелетом

**Files:**
- Create: `docker/README.md`
- Create: `docker/legacy-pi/README.md`
- Create: `docker/ros2/README.md`
- Create: `docker/base/README.md`

**Step 1: Создать `docker/README.md`**

Содержимое:
```markdown
# docker/

Этот каталог содержит compose-стеки и базовые образы для всех аппаратных композиций BiBa. См. [docs/system_architecture.md](../docs/system_architecture.md).

| Подкаталог | Композиция | Описание |
| --- | --- | --- |
| [`legacy-pi/`](legacy-pi/) | A. Pi-only | Текущий рабочий compose с `biba-controller` Python-runtime |
| [`ros2/`](ros2/) | C. Pi + STM32 | ROS2-стек (в разработке) |
| [`base/`](base/) | общий | Базовые Docker-образы (в разработке) |

Композиция B (STM32-only) не содержит SBC и compose-стека не имеет — её прошивка живёт в [`firmware/`](../firmware/).
```

**Step 2: Создать `docker/legacy-pi/README.md`**

Содержимое:
```markdown
# Legacy Pi-only композиция (A)

Compose-стек для текущей рабочей конфигурации робота: Raspberry Pi Zero 2W с прямым доступом к BTS7960, CRSF, BMS, voice runtime и web UI.

Запуск стандартный — через alias-ы `bb*` (см. [scripts/biba_aliases.sh](../../scripts/biba_aliases.sh)):

```bash
bbpull
bbstart
```

Полный quick-start — в [docs/deployment.md](../../docs/deployment.md#композиция-a-pi-only).
```

**Step 3: Создать `docker/ros2/README.md`**

Содержимое (placeholder):
```markdown
# ROS2-стек композиции C (Pi + STM32)

> **Статус:** в разработке. Дизайн зафиксирован в
> [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).

Когда стек будет реализован, здесь будут лежать `docker-compose.yaml`, конфиги Zenoh router'а и launch-обёртки для контейнеров `biba-stm32-bridge`, `robot-state-publisher`, `ros2-control` и `twist-mux`.

Реальные исходники узлов будут жить в `ros2_ws/src/`.
```

**Step 4: Создать `docker/base/README.md`**

Содержимое (placeholder):
```markdown
# Базовые Docker-образы

> **Статус:** в разработке. Дизайн зафиксирован в
> [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).

Здесь будут жить `Dockerfile.ros2-zenoh`, `Dockerfile.ros2-control` и прочие общие base-образы. Образы публикуются в GHCR и используются как `FROM` в сервисных Dockerfile-ах из [`../ros2/`](../ros2/).
```

**Step 5: Проверить, что новые файлы добавились без шума**

Run:
```bash
cd /home/ros2/Downloads/biba
ls docker/ docker/legacy-pi/ docker/ros2/ docker/base/
```
Expected: каждый каталог содержит ровно `README.md`.

**Step 6: Commit**

```bash
git add docker/
git commit -m "chore(docker): add empty docker/ skeleton with placeholders for legacy-pi, ros2, base"
```

---

### Task 2: Перенести `docker-compose.yml` в `docker/legacy-pi/`

**Files:**
- Move: `docker-compose.yml` → `docker/legacy-pi/docker-compose.yml`

**Step 1: Перенести файл через `git mv`**

Run:
```bash
cd /home/ros2/Downloads/biba
git mv docker-compose.yml docker/legacy-pi/docker-compose.yml
```
Expected: файл переехал, history сохранена.

**Step 2: Убедиться, что в корне действительно нет compose**

Run: `ls docker-compose.yml 2>&1 || echo "missing — ok"`
Expected: `missing — ok`.

**Step 3: Зафиксировать, что compose-тесты теперь падают (baseline для следующей задачи)**

Run:
```bash
python3 -m pytest tests/test_config.py -k docker_compose -q 2>&1 | tail -5
```
Expected: тесты `test_docker_compose_*` падают с `FileNotFoundError: [Errno 2] No such file or directory: 'docker-compose.yml'`. Это ожидаемо и будет починено в Task 3.

**Step 4: Commit (failing state, isolation move)**

```bash
git add -A
git commit -m "refactor(docker): move docker-compose.yml to docker/legacy-pi/"
```
Note: tests are intentionally red on this commit; они будут перенаправлены в Task 3.

---

### Task 3: Переключить `tests/test_config.py` на новый путь compose

**Files:**
- Modify: `tests/test_config.py` (15 вхождений строки `"docker-compose.yml"`)

**Step 1: Ввести модульную константу для пути compose**

В верхней части файла (после `from pathlib import Path`-импортов), если такой константы ещё нет, добавить:

```python
LEGACY_PI_COMPOSE_PATH = "docker/legacy-pi/docker-compose.yml"
```

**Step 2: Заменить все 15 вхождений**

Заменить каждое:
```python
with open("docker-compose.yml", encoding="utf-8") as compose_file:
```
на:
```python
with open(LEGACY_PI_COMPOSE_PATH, encoding="utf-8") as compose_file:
```

Search-and-replace поможет выполнить это за один проход. Никакая другая логика тестов не меняется.

**Step 3: Запустить compose-тесты**

Run:
```bash
python3 -m pytest tests/test_config.py -k docker_compose -q
```
Expected: PASS на всех `test_docker_compose_*` тестах.

**Step 4: Запустить полный test_config.py**

Run:
```bash
python3 -m pytest tests/test_config.py -q
```
Expected: PASS на всех тестах файла.

**Step 5: Commit**

```bash
git add tests/test_config.py
git commit -m "test(config): point docker-compose tests at docker/legacy-pi/"
```

---

### Task 4: Обновить `scripts/biba_aliases.sh` под новый путь

**Files:**
- Modify: `scripts/biba_aliases.sh`
- Modify: `tests/test_biba_aliases.py`

**Step 1: Написать новый failing test**

В `tests/test_biba_aliases.py` добавить тест:

```python
def test_biba_aliases_use_docker_legacy_pi_compose_path() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    # default путь к compose должен указывать в docker/legacy-pi/
    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in aliases
    # старый путь больше не используется напрямую
    assert '"$BIBA_DIR/docker-compose.yml"' not in aliases
    # compose всё ещё запускается через docker compose -f
    assert '-f "$BIBA_COMPOSE_FILE"' in aliases
```

**Step 2: Убедиться, что новый тест падает**

Run:
```bash
python3 -m pytest tests/test_biba_aliases.py -q
```
Expected: новый тест FAIL, остальные PASS.

**Step 3: Внести правки в `scripts/biba_aliases.sh`**

- Добавить переменную `BIBA_COMPOSE_FILE` рядом с `BIBA_DIR`/`BIBA_ENV_FILE`:

```bash
BIBA_DIR="${BIBA_DIR:-$HOME/biba}"
BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"
BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"
```

- В функции `_biba_compose` заменить `-f "$BIBA_DIR/docker-compose.yml"` на `-f "$BIBA_COMPOSE_FILE"`.

**Step 4: Запустить тесты алиасов**

Run:
```bash
python3 -m pytest tests/test_biba_aliases.py -q
```
Expected: PASS на всех тестах файла.

**Step 5: Commit**

```bash
git add scripts/biba_aliases.sh tests/test_biba_aliases.py
git commit -m "chore(aliases): point _biba_compose at docker/legacy-pi/ via BIBA_COMPOSE_FILE"
```

---

### Task 5: Обновить `scripts/update.sh` и `scripts/diagnostics.sh`

**Files:**
- Modify: `scripts/update.sh`
- Modify: `scripts/diagnostics.sh`
- Modify: `tests/test_biba_aliases.py`

**Step 1: Расширить тесты обоих скриптов**

В `tests/test_biba_aliases.py` добавить:

```python
def test_update_script_uses_docker_legacy_pi_compose_path() -> None:
    script = Path("scripts/update.sh").read_text(encoding="utf-8")

    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in script
    assert '"$BIBA_DIR/docker-compose.yml"' not in script
    assert '-f "$BIBA_COMPOSE_FILE"' in script


def test_diagnostics_script_uses_docker_legacy_pi_compose_path() -> None:
    script = Path("scripts/diagnostics.sh").read_text(encoding="utf-8")

    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in script
    assert '"$BIBA_DIR/docker-compose.yml"' not in script
    assert '-f "$BIBA_COMPOSE_FILE"' in script
```

**Step 2: Убедиться, что они падают**

Run:
```bash
python3 -m pytest tests/test_biba_aliases.py -q
```
Expected: два новых теста FAIL.

**Step 3: Внести правки в оба скрипта**

В `scripts/update.sh` и `scripts/diagnostics.sh` добавить рядом с `BIBA_ENV_FILE` строку:

```bash
BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"
```

И в их `_biba_compose` функциях заменить `-f "$BIBA_DIR/docker-compose.yml"` на `-f "$BIBA_COMPOSE_FILE"`.

**Step 4: Запустить тесты**

Run:
```bash
python3 -m pytest tests/test_biba_aliases.py -q
```
Expected: PASS на всех тестах файла.

**Step 5: Commit**

```bash
git add scripts/update.sh scripts/diagnostics.sh tests/test_biba_aliases.py
git commit -m "chore(scripts): route update.sh and diagnostics.sh through BIBA_COMPOSE_FILE"
```

---

### Task 6: Обновить systemd unit в `scripts/setup/setup_node.sh`

**Files:**
- Modify: `scripts/setup/setup_node.sh`
- Modify: `tests/test_setup_node.py`

**Step 1: Написать failing test**

В `tests/test_setup_node.py` добавить:

```python
def test_setup_node_service_uses_docker_legacy_pi_compose_path() -> None:
    script = Path("scripts/setup/setup_node.sh").read_text(encoding="utf-8")

    # WorkingDirectory указывает в docker/legacy-pi/, чтобы docker compose нашёл compose-файл
    assert "WorkingDirectory=$REPO_DIR/docker/legacy-pi" in script
```

**Step 2: Убедиться, что тест падает**

Run:
```bash
python3 -m pytest tests/test_setup_node.py -q
```
Expected: новый тест FAIL.

**Step 3: Поправить `setup_service()` в `scripts/setup/setup_node.sh`**

Заменить:
```
WorkingDirectory=$REPO_DIR
```
на:
```
WorkingDirectory=$REPO_DIR/docker/legacy-pi
```

Это самый чистый способ, потому что `docker compose up -d` без `-f` подхватит `docker-compose.yml` из cwd, и существующая семантика `ExecStartPre`/`ExecStart`/`ExecStop` остаётся прежней.

**Step 4: Запустить тесты**

Run:
```bash
python3 -m pytest tests/test_setup_node.py -q
```
Expected: PASS на всех тестах файла.

**Step 5: Commit**

```bash
git add scripts/setup/setup_node.sh tests/test_setup_node.py
git commit -m "chore(systemd): point biba-controller.service WorkingDirectory at docker/legacy-pi/"
```

---

### Task 7: Прогнать полный тест-suite

**Files:** нет (валидация)

**Step 1: Полный pytest**

Run:
```bash
cd /home/ros2/Downloads/biba
python3 -m pytest -q 2>&1 | tail -15
```
Expected: ВСЕ существующие тесты проходят. Если что-то сломалось — НЕ продолжать; найти проблему и поправить, прежде чем переходить к документации.

**Step 2: Проверить, что compose валиден**

Run:
```bash
docker compose -f docker/legacy-pi/docker-compose.yml config >/dev/null && echo "ok"
```
Expected: `ok`. Если docker недоступен — пропустить эту проверку и зафиксировать в commit message.

**Step 3: Никаких изменений — никакого commit'а**

Этот шаг чисто валидационный.

---

### Task 8: Переписать README как архитектурный hub

**Files:**
- Modify: `README.md`

**Step 1: Структура нового README**

Содержание сохраняется по сути, но реорганизуется в hub. Новая верхнеуровневая структура:

1. **BiBa** — лого, бейджи, одна-две строки описания.
2. **Архитектура** — таблица композиций A/B/C (та же, что в design-doc) + правило маршрутизации CRSF. Cross-link на [docs/system_architecture.md](docs/system_architecture.md) и [docs/stm32_architecture.md](docs/stm32_architecture.md).
3. **Состав железа** — текущие пункты, без правок.
4. **Распиновка** — текущая таблица, без правок (актуальна для композиции A; примечание про композиции B/C ссылается на `docs/wiring.md`).
5. **Структура репозитория** — обновить, убрать упоминания корневого `docker-compose.yml`, добавить `docker/`, `ros2_ws/` (с пометкой "в разработке"), оставить остальное.
6. **Quick-start по композициям** — три коротких подраздела:
   - Композиция A (Pi-only): сегодняшний bringup-скрипт + ссылка на [docs/deployment.md](docs/deployment.md#композиция-a-pi-only).
   - Композиция B (STM32-only): ссылка на [firmware/README.md](firmware/README.md).
   - Композиция C (Pi + STM32): помечено «в разработке», ссылка на [design-doc](docs/plans/2026-04-28-sbc-architecture-redesign-design.md).
7. **Подготовка Raspberry Pi** — без изменений, но в подразделе «Композиция A».
8. **Запуск** — заменить `docker compose up -d` (которое читает корневой compose) на `docker compose -f docker/legacy-pi/docker-compose.yml up -d` или показать через `bb*` aliases.
9. **Конфигурация и переменные окружения** — оставить нынешние таблицы env'ов, но в начале раздела явно сказать, что они применимы к композиции A (`docker/legacy-pi/docker-compose.yml`).
10. **Settings UI** — без изменений.
11. **Звуки и моторный синтез** — без изменений.
12. **Motor Trim** — без изменений.

**Step 2: Применить правки**

Это большая правка. Делается одним проходом редактирования. Принципы:
- НЕ удалять существующий контент про env / settings UI / trim — он по-прежнему правда для композиции A.
- ВСЕ упоминания «`docker-compose.yml`» (без префикса) заменить на «`docker/legacy-pi/docker-compose.yml`» либо на «через alias `bb*`».
- Все упоминания «`docker compose pull`/`up -d`» заменить на корректные команды из нового пути (или просто `bbpull`/`bbstart`).

**Step 3: Проверить ссылки**

Run:
```bash
grep -nE 'docs/|firmware/|docker/' README.md | head -40
```
Visual check: все ссылки указывают на существующие файлы.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): rewrite as architecture hub with three-composition matrix"
```

---

### Task 9: Создать `docs/system_architecture.md`

**Files:**
- Create: `docs/system_architecture.md`

**Step 1: Написать документ**

Документ — это «канонический обзор для разработчика». Содержание:

1. **Обзор** (1 абзац): зачем существует BiBa, кратко про композиции.
2. **Три композиции** (таблица из design-doc + по 1 абзацу про каждую).
3. **Правило маршрутизации CRSF** (короткий раздел).
4. **Композиция A: Pi-only** — диаграмма потока данных (CRSF → mixer → BTS7960), модули `biba-controller/`, что НЕ поддерживается (новые направления).
5. **Композиция B: STM32-only** — ссылка на [stm32_architecture.md](stm32_architecture.md), список того, что доступно.
6. **Композиция C: Pi + STM32** — диаграмма (CRSF → STM32 → SPI → SBC ROS2-stack → BTS7960), список ROS2-узлов в minimal-профиле и full-профиле, hook-points для манипулятора/UWB/internet-bridge/camera/autonomy.
7. **Hardware-классы SBC** — Zero 2W (lite, только A или minimal-C), Pi 4/5 (full-C).
8. **Failsafe-уровни** — независимый STM32 failsafe vs SBC twist-arbitration.
9. **Точки расширения** — список будущих ROS2-пакетов и где они появятся (`ros2_ws/src/`).
10. **Cross-links** на [stm32_architecture.md](stm32_architecture.md), [ros2_stack.md](ros2_stack.md), [deployment.md](deployment.md).

**Источник правды:** этот документ должен быть прозой-копией design-doc'а [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](plans/2026-04-28-sbc-architecture-redesign-design.md), но без раздела «список задач» и «out of scope». Можно делать прямые цитаты таблиц.

**Step 2: Сохранить и пробежать спеллчек глазами**

**Step 3: Commit**

```bash
git add docs/system_architecture.md
git commit -m "docs(architecture): add system_architecture.md as canonical multi-composition overview"
```

---

### Task 10: Создать `docs/ros2_stack.md` (placeholder-структура)

**Files:**
- Create: `docs/ros2_stack.md`

**Step 1: Содержимое**

```markdown
# ROS2-стек (композиция C)

> **Статус:** в разработке. Этот документ описывает целевую структуру ROS2-стека, который будет жить в `ros2_ws/src/` и `docker/ros2/`. Реализация ведётся по дизайну в [plans/2026-04-28-sbc-architecture-redesign-design.md](plans/2026-04-28-sbc-architecture-redesign-design.md).

## Назначение

ROS2-стек добавляет высокоуровневый слой к робото-комбинации Pi + STM32. STM32 владеет hard-realtime частью (CRSF, PWM, current-limit, motor-audio); SBC через SPI-bridge подключается к ROS2-экосистеме.

## ROS2-пакеты (целевой список)

| Пакет                     | Назначение                                                       | Статус   |
| ------------------------- | ---------------------------------------------------------------- | -------- |
| `biba_description`        | URDF/xacro для дифф-привода BiBa                                 | planned  |
| `biba_msgs`               | `CrsfStatus`, `Stm32Telemetry`, `MotorAudio`                     | planned  |
| `biba_stm32_bridge`       | Python ROS2-узел: SPI ↔ топики (реюз `biba-controller/stm32_link/`)| planned |
| `biba_hardware_stm32`     | `ros2_control` SystemInterface поверх SPI                        | planned  |
| `biba_bringup`            | launch + конфиги controller_manager, twist_mux                   | planned  |
| `biba_manipulator`        | hook-point: ros2_control для servo-контроллера                   | future   |
| `biba_uwb_follow`         | hook-point: BU4 → tag pose → cmd_vel                             | future   |
| `biba_remote_bridge`      | hook-point: Zenoh / WebRTC / VPN bridge                          | future   |
| `biba_camera`             | hook-point: FPV stream + ML inference                            | future   |
| `biba_autonomy`           | hook-point: SLAM / Nav2 / mission scripting                      | future   |

## Контейнеры (целевой состав)

См. таблицы профилей **minimal** и **full** в [system_architecture.md](system_architecture.md#композиция-c-pi--stm32).

## Транспорт

ROS2 поверх `rmw_zenoh_cpp` + Zenoh router. Это даёт естественный мост наружу (cloud-Zenoh / WebRTC) для будущего internet-bridge.

## Топики SPI-bridge (предварительно)

См. таблицы публикаций и подписок `biba_stm32_bridge` в [design-doc](plans/2026-04-28-sbc-architecture-redesign-design.md#контракт-biba_stm32_bridge--stm32).

## Как добавить новый пакет

> Будет дописано после реализации первой версии стека.
```

**Step 2: Commit**

```bash
git add docs/ros2_stack.md
git commit -m "docs(ros2): add ros2_stack.md placeholder with target package map"
```

---

### Task 11: Дополнить `docs/stm32_architecture.md` cross-link'ами

**Files:**
- Modify: `docs/stm32_architecture.md`

**Step 1: Добавить вводный блок про композиции**

В самом начале файла (после заголовка "STM32F103 firmware architecture") добавить короткий раздел:

```markdown
> **Контекст:** этот документ описывает прошивку STM32, которая используется в композициях B (STM32-only) и C (Pi + STM32) проекта BiBa. Общий обзор всех композиций — в [system_architecture.md](system_architecture.md). Высокоуровневый ROS2-стек композиции C — в [ros2_stack.md](ros2_stack.md).
```

**Step 2: Уточнить терминологию режимов**

В разделе «Два режима работы» в подзаголовках пометить:
- `Standalone` — соответствует **композиции B** проекта.
- `Companion` — соответствует **композиции C** проекта.

Это две минимальные правки текста, без изменения смысла.

**Step 3: Commit**

```bash
git add docs/stm32_architecture.md
git commit -m "docs(stm32): cross-link to system_architecture and label modes by composition"
```

---

### Task 12: Расщепить `docs/deployment.md` per-композиция

**Files:**
- Modify: `docs/deployment.md`

**Step 1: Новая структура**

Перестроить документ:

1. **Обзор** (новый, 1 абзац) — про три композиции, ссылка на [system_architecture.md](system_architecture.md).
2. **Композиция A: Pi-only** — основной массив сегодняшнего deployment.md (предварительные требования, bringup-скрипт, авторизация GHCR, запуск, alias-ы, обновление, диагностика, конфигурация). Все упоминания `docker-compose.yml` обновить до `docker/legacy-pi/docker-compose.yml`. Команды `docker compose pull/up -d` заменить на путь через `-f` или на `bb*` aliases.
3. **Композиция B: STM32-only** — короткий раздел (1-2 параграфа): «Без SBC. См. [firmware/README.md](../firmware/README.md) и [docs/wiring.md](wiring.md)».
4. **Композиция C: Pi + STM32 (ROS2)** — короткий раздел-заглушка: «В разработке. Целевая архитектура — в [system_architecture.md](system_architecture.md), реализация — по [design-doc](plans/2026-04-28-sbc-architecture-redesign-design.md)».
5. **Troubleshooting** — оставить, пометить «применимо к композиции A» либо разнести по композициям, если что-то STM32-специфичное всплывёт (на сейчас — оставить как есть).

**Step 2: Применить правки**

Никакой существующий контент не удаляем — только реорганизуем под новые подзаголовки и обновляем пути compose. Все taблицы env-переменных остаются под композицией A.

**Step 3: Проверить ссылки**

Run:
```bash
grep -nE '\]\(.*\)' docs/deployment.md | head -40
```
Visual check.

**Step 4: Commit**

```bash
git add docs/deployment.md
git commit -m "docs(deployment): split per composition; update compose paths to docker/legacy-pi/"
```

---

### Task 13: Финальная валидация

**Files:** нет

**Step 1: Полный pytest**

Run:
```bash
cd /home/ros2/Downloads/biba
python3 -m pytest -q 2>&1 | tail -10
```
Expected: ВСЕ тесты PASS, не меньше, чем в Pre-flight. Новые тесты добавлены — счётчик должен вырасти ровно на количество новых.

**Step 2: Найти orphan-ссылки на старый путь compose**

Run:
```bash
cd /home/ros2/Downloads/biba
grep -RIn --exclude-dir=.git --exclude-dir=docs/plans 'docker-compose.yml' . | grep -v 'docker/legacy-pi/docker-compose.yml' | grep -v 'tests/test_config.py'
```
Expected: пусто или только осмысленные совпадения (например, в design-doc'ах из `docs/plans/` старые планы могут ссылаться на корневой compose — это исторические артефакты, их не трогаем). Если найдены живые места — починить и закоммитить.

`docs/plans/` исключён из проверки целенаправленно: исторические планы — иммутабельны.

**Step 3: Smoke-проверка compose**

Run:
```bash
docker compose -f docker/legacy-pi/docker-compose.yml config >/dev/null && echo "compose ok"
```
Expected: `compose ok`. Если docker недоступен — пропустить.

**Step 4: Smoke-проверка bash-скриптов на синтаксис**

Run:
```bash
bash -n scripts/biba_aliases.sh && \
bash -n scripts/update.sh && \
bash -n scripts/diagnostics.sh && \
bash -n scripts/setup/setup_node.sh && \
echo "scripts ok"
```
Expected: `scripts ok`.

**Step 5: Финальный commit (если что-то нашлось в шагах 2-4)**

Если все шаги зелёные — финального commit'а нет. Если что-то починили — отдельный commit с message:
```
chore: clean up orphan references to root docker-compose.yml
```

---

## Готово

После Task 13:

- Корневой `docker-compose.yml` удалён.
- `docker/legacy-pi/docker-compose.yml` — рабочий compose композиции A.
- Все скрипты и systemd unit указывают на новый путь через `BIBA_COMPOSE_FILE` или `WorkingDirectory`.
- README — архитектурный hub с матрицей трёх композиций.
- `docs/system_architecture.md` — каноничный обзор.
- `docs/ros2_stack.md`, `docker/ros2/`, `docker/base/` — placeholder'ы под следующие задачи дизайна.
- `docs/stm32_architecture.md` помечен по композициям и cross-link'ован.
- `docs/deployment.md` разделён по композициям.

Дальше (отдельные планы): Task 2 из дизайна — base-images; Task 3 — `biba_description`; Task 4 — `biba_msgs`; и т.д.
