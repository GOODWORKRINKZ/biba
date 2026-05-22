# Phase 6: IS-Signal RPM Proof-of-Concept — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 06-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 06-is-rpm-poc
**Areas discussed:** USB CDC Command Protocol, Motor Selection Strategy, MY1016Z Characteristics, Algorithm Comparison Criteria, Output Format

---

## USB CDC Command Protocol

| Option | Description | Selected |
|--------|-------------|----------|
| `CAPTURE <FWD\|REV> <duty> <n> <sps>` | Единый параметр direction — просто и ясно | ✓ |
| `CAPTURE_FWD / CAPTURE_REV` | Разные команды — более явно, больше кода | |
| `CAPTURE_SWEEP <motor> <duty>` | Авто-sweep FWD+REV — меньше вызовов, меньше контроля | |

**User's choice:** `CAPTURE <FWD|REV> <duty> <n> <sps>`
**Notes:** Тест должен гонять мотор в обе стороны — это мастхев. Direction как параметр команды — самый чистый вариант. `CAPTURE_BOTH` (оба мотора) убран из scope.

---

## Motor Selection Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| `<motor>` как параметр команды | Firmware выбирает LEFT или RIGHT | |
| Константа в Python | Motor = hardcoded в Python-скрипте, PoC всегда на одном моторе | ✓ |

**User's choice:** Константа в Python-скрипте
**Notes:** Тест ведётся на одном моторе за раз. Python знает какой. Firmware не нужна информация о выборе мотора. Аргумент `--motor {left|right}` в CLI.

---

## MY1016Z Характеристики

| Option | Description | Selected |
|--------|-------------|----------|
| 2750 RPM при 24V | Предполагали BLDC | |
| Редукторный коллекторный, 75 RPM на выходе | Пользователь уточнил | ✓ |

**User's choice:** MY1016Z — редукторный коллекторный мотор, 24V, 75 RPM на выходном валу
**Notes:** Критически важное уточнение. IS-рябь от переключения щёток на коллекторных пластинах (commutator ripple), не от пар полюсов. Формула: `f = N_seg × RPM_core / 60`. Передаточное число редуктора — уточнить по даташиту (примерно 33:1 → RPM_core ≈ 2500 → f_ripple ≈ 250–1000 Hz при duty 25–100%).

---

## Гарантийное число редуктора

| Option | Description | Selected |
|--------|-------------|----------|
| Есть даташит — проверю точно | Пользователь проверит по даташиту | ✓ |
| ~30:1 примерно | Грубая оценка | |
| Нет даташита | — | |

**User's choice:** Есть даташит — уточнить до запуска захватов
**Notes:** Нужно для абсолютной калибровки f_ripple → RPM. Занесено как обязательный шаг в canonical refs.

---

## Algorithm Comparison Criteria

| Option | Description | Selected |
|--------|-------------|----------|
| R² > 0.9 между duty и пик-частотой | Достаточно для PoC | ✓ |
| Глубже: SNR, computational cost, real-time viability | Выходит за рамки PoC | |

**User's choice:** R² > 0.9 — достаточно для PoC
**Notes:** Если три алгоритма показывают R² > 0.9 — цель достигнута. Какой лучше для embedded real-time — следующая фаза.

---

## Выход Python-скрипта

| Option | Description | Selected |
|--------|-------------|----------|
| CSV + графики (PNG) | CSV сырые данные + спектры и scatter-plot | ✓ |
| Jupyter notebook | Интерактивно, но требует Jupyter | |
| Только консольный вывод | Без файлов | |

**User's choice:** CSV + PNG
**Notes:** Артефакты в `artifacts/is-capture/`. Консольный вывод с duty/direction/f_peak/R² при каждом захвате.

---

## Agent's Discretion

- Структура Python-скрипта (один файл или два) — по усмотрению, если есть `--port` и `--motor`
- Unit-тесты алгоритмов — агент пишет на синтетическом сигнале, покрывая ±5% критерий
- Порядок волн firmware → python — как в 06-PLAN.md

## Deferred Ideas

- `CAPTURE_BOTH` (оба мотора interleaved) — упрощено до одного мотора для PoC
- Real-time RPM на embedded RP2040 (C) — Phase 7+
- Абсолютная калибровка f_ripple → RPM в физических единицах — после уточнения N_seg и ratio
- SNR и computational cost анализ алгоритмов — Phase 7 при необходимости
