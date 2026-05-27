# Phase 12: Signal Chain Feature Gating - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-27
**Phase:** 12-Signal Chain Feature Gating
**Areas discussed:** Toggle Mechanism, Toggle Granularity, Feature Scope, Config Structure

---

## Toggle Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Compile-time defines в target_config.h | `BIBA_FEATURE_*=1`. Просто, 0 RAM, но нужна перекомпиляция. | ✓ |
| Runtime-флаги во flash (LittleFS) | Меняются через serial. Гибко в поле, но +RAM и persistence. | |
| Гибрид: дефолт в конфиге + runtime override | compile-time default, serial-команда переопределяет до reboot. | |

**User's choice:** Compile-time defines в target_config.h
**Notes:** Самый простой и предсказуемый механизм. Полевое переключение не требуется на данном этапе.

---

## Toggle Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Один мастер-свитч + индивидуальные | `BIBA_FEATURE_RPM_CLOSED_LOOP` (мастер) + `BIBA_FEATURE_RPM_PI`, `BIBA_FEATURE_RPM_ZC` и т.д. | ✓ |
| Только индивидуальные, без мастера | Каждый сам за себя. `BIBA_OPEN_LOOP` удаляется. | |
| Групповые тумблеры по стадиям | `BIBA_FEATURE_MEASUREMENT`, `BIBA_FEATURE_CONTROL`, `BIBA_FEATURE_SAFETY`. | |

**User's choice:** Мастер-свитч + индивидуальные
**Notes:** Сохраняет удобство быстрого переключения open/closed loop одним define, но даёт тонкий контроль.

---

## Feature Scope

| Option | Description | Selected |
|--------|-------------|----------|
| RPM-цепочка (ZC+spectral+DR+PI+anti-stall) | Мастер + 5 индивидуальных. Основной scope. | ✓ |
| Safety-фичи (latch recovery, current/power limiter) | `BIBA_FEATURE_LATCH_RECOVERY`, `BIBA_FEATURE_CURRENT_LIMITER`. | ✓ |
| Comfort-фичи (steering deadband, ramp, melody) | `BIBA_FEATURE_STEERING_DEADBAND`, `BIBA_FEATURE_RPM_RAMP`, `BIBA_FEATURE_MELODY`. | ✓ |
| Drive-фичи (heading-hold PID, speed mode, mixer) | `BIBA_FEATURE_HEADING_HOLD`, `BIBA_FEATURE_SPEED_MODE`, `BIBA_FEATURE_MIXER_PROJECTION`. | ✓ |
| Reverse pip (уже есть BIBA_REVERSE_PIP_ENABLED) | Оставить как есть — уже отключаемый. | ✓ |

**User's choice:** ALL categories selected
**Notes:** Полный аудит всей цепочки. 17 тумблеров total.

---

## Config Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Секции-комментарии + FEATURE-префикс | `/* --- Feature: RPM PI --- */` + `#define BIBA_FEATURE_RPM_PI 1` + параметры. | ✓ |
| Feature-config struct в коде | `const biba_feature_config_t FEAT = {...}`. Больше типизации, сложнее. | |
| Отдельный features.h на каждый target | `targets/RPICO_RP2040/features.h`. Изоляция, но ещё один файл. | |

**User's choice:** Секции-комментарии + FEATURE-префикс
**Notes:** Минимальные изменения относительно текущей структуры, читаемо, легко найти все параметры фичи.

---

## Agent's Discretion

Не применимо — все решения приняты пользователем.

## Deferred Ideas

- Runtime-переключение тумблеров через serial (полевой дебаггинг)
- Motor trim repair for PI mode (target_hz offset вместо duty trim)
- IMU integration for heading-hold (перетюнить PID с реальным гироскопом)
