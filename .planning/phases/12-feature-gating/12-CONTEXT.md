# Phase 12: Signal Chain Feature Gating - Context

**Gathered:** 2026-05-27
**Status:** Ready for planning

## Phase Boundary

Аудит всей цепочки CRSF → моторный PWM-сигнал, выделение каждой фичи в отдельный compile-time тумблер (`BIBA_FEATURE_*` в `target_config.h`), реорганизация конфигов по фичам с секциями-комментариями. `BIBA_OPEN_LOOP` заменяется на мастер-свитч `BIBA_FEATURE_RPM_CLOSED_LOOP` + 16 индивидуальных тумблеров под ним. Цель: любая фича, влияющая на итоговый duty-сигнал к драйверам, должна отключаться одним `#define` без побочных эффектов.

## Implementation Decisions

### D-01: Механизм тумблеров — compile-time defines
- Все тумблеры — `#define BIBA_FEATURE_<NAME> 1` (или `0`) в `target_config.h`
- Никакого runtime-переключения, никакой persistence во flash
- При смене тумблера — перекомпиляция и перепрошивка
- Каждый тумблер по умолчанию `1` (enabled) в `biba_config.h`, target может переопределить

### D-02: Мастер-свитч + индивидуальные
- `BIBA_FEATURE_RPM_CLOSED_LOOP` — мастер всей RPM-цепочки. Если `0`, ВСЕ RPM-фичи (ZC, spectral, DR, PI, anti-stall, dual-window, load gate) выключены независимо от их индивидуальных тумблеров
- Каждая RPM-фича имеет свой `BIBA_FEATURE_RPM_<SUBSYSTEM>` тумблер, который работает только когда мастер = 1
- Старый `BIBA_OPEN_LOOP` удаляется; его роль выполняет `BIBA_FEATURE_RPM_CLOSED_LOOP=0`
- Для обратной совместимости: `#ifdef BIBA_OPEN_LOOP` → `#define BIBA_FEATURE_RPM_CLOSED_LOOP 0` (deprecation warning через `#warning`)

### D-03: Полный охват — 17 тумблеров
Все фичи цепочки получают индивидуальный тумблер:

**RPM-цепочка (мастер `BIBA_FEATURE_RPM_CLOSED_LOOP`):**
- `BIBA_FEATURE_RPM_ZC` — Zero-crossing detector (`zc_detector.c`)
- `BIBA_FEATURE_RPM_SPECTRAL` — Goertzel spectral estimator (`rpm_spectral_estimator.c`)
- `BIBA_FEATURE_RPM_DUAL_WINDOW` — Dual-window hint-guided search
- `BIBA_FEATURE_RPM_LOAD_GATE` — IS-pin DC load gate (Phase 11)
- `BIBA_FEATURE_RPM_DR` — Dead reckoning fallback (`rpm_dr.c`)
- `BIBA_FEATURE_RPM_PI` — PI controller (`rpm_pi.c`)
- `BIBA_FEATURE_RPM_ANTI_STALL` — Anti-stall duty ramp (Phase 11)

**Safety:**
- `BIBA_FEATURE_LATCH_RECOVERY` — BTS7960 thermal latch auto-reset
- `BIBA_FEATURE_CURRENT_LIMITER` — Per-motor current/power clamp (`control_loop.c`)

**Comfort:**
- `BIBA_FEATURE_STEERING_DEADBAND` — Steering deadband (no-rescale, 0.20)
- `BIBA_FEATURE_RPM_RAMP` — Setpoint accel/decel ramp (`ramp.c`)
- `BIBA_FEATURE_MELODY` — Motor coil melodies (arm/disarm/failsafe/startup)
- `BIBA_FEATURE_REVERSE_PIP` — Reverse backup beep (бывший `BIBA_REVERSE_PIP_ENABLED`)

**Drive:**
- `BIBA_FEATURE_HEADING_HOLD` — Heading-hold PID correction
- `BIBA_FEATURE_SPEED_MODE` — 3-position switch speed scaling (1/3, 2/3, 1.0)
- `BIBA_FEATURE_MIXER_PROJECTION` — L∞ ball projection (vs plain differential mix)

### D-04: Структура конфигов — секции-комментарии + FEATURE-префикс
- В `biba_config.h`: каждая фича получает свою секцию с заголовком-комментарием
- Все `#define` фичи сгруппированы внутри секции (тумблер + все параметры фичи)
- В `target_config.h`: только переопределения, с тем же форматом секций
- Шаблон секции:
```c
/* --- Feature: RPM PI Controller ----------------------------------------- */
#ifndef BIBA_FEATURE_RPM_PI
#  define BIBA_FEATURE_RPM_PI             1
#endif
#ifndef BIBA_RPM_PI_KP
#  define BIBA_RPM_PI_KP                  0.5f
#endif
/* ... остальные параметры фичи ... */
```

### D-05: Критические негативные фичи (safety) — НЕ отключаются
Следующие элементы цепочки **не имеют тумблера** и не могут быть отключены:
- **Failsafe** (`failsafe.c`) — critical safety, обязателен всегда
- **SSR** (`biba_hal_ssr_set`) — hardware safety interlock
- **Arming** (CH5 gate) — software safety interlock
- **CRSF ingest** — без него нет управления
- **BTS7960 drive** (`biba_bts7960_drive`) — конечный выход, не отключается
- **Blackbox** — не влияет на сигнал, только запись; уже имеет свой CH7 trigger
- **Debug serial** (DBGON/OLON) — bench-test инструмент, не production-фича

### D-06: Зависимости между тумблерами
- `BIBA_FEATURE_RPM_PI=1` требует `BIBA_FEATURE_RPM_DR=1` (PI использует DR-выход как measurement)
- `BIBA_FEATURE_RPM_DUAL_WINDOW=1` требует `BIBA_FEATURE_RPM_SPECTRAL=1` (hint — это второй поиск spectral)
- `BIBA_FEATURE_RPM_LOAD_GATE=1` требует `BIBA_FEATURE_RPM_SPECTRAL=1` (gate применяется к spectral-результату)
- `BIBA_FEATURE_RPM_ANTI_STALL=1` требует `BIBA_FEATURE_RPM_SPECTRAL=1` (использует HIGH_LOAD из spectral)
- Нарушение зависимостей — `#error` на этапе компиляции
- Если `BIBA_FEATURE_RPM_CLOSED_LOOP=0`, проверка зависимостей не выполняется (всё выключено)

### D-07: Дефолтные значения для RP2040 target
- Все тумблеры = `1` (enabled) — сохраняет текущее поведение
- `BIBA_FEATURE_HEADING_HOLD` = `1` (код есть, но ki=0 — фактически выключен; тумблер просто гейтит вызов `biba_pid_step`)
- `BIBA_FEATURE_REVERSE_PIP` = `0` (как сейчас `BIBA_REVERSE_PIP_ENABLED=0`)
- `BIBA_FEATURE_MELODY` = `1` (arm/disarm/failsafe звуки важны)

### Agent's Discretion
Не применимо — все решения приняты пользователем.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Firmware signal chain
- `firmware/src/modes/mode_standalone.c` — Полная цепочка CRSF→мотор: ingest_crsf() → tick() → biba_bts7960_drive(). Все 19 этапов.
- `firmware/include/biba_config.h` — Текущий плоский список #define. Будет реорганизован.
- `firmware/targets/RPICO_RP2040/target_config.h` — Целевые переопределения для RP2040. Сюда добавляются тумблеры.

### Модули цепочки
- `firmware/src/app/control_loop.c/h` — `biba_apply_motor_limits()`, `biba_pid_step()`, `biba_mix_differential()`, `biba_apply_deadband()`
- `firmware/src/app/failsafe.c/h` — `biba_failsafe_tick()`
- `firmware/src/app/ramp.c/h` — `biba_ramp_update_with_rates()`
- `firmware/src/app/zc_detector.c/h` — `zc_freq_analyze()`
- `firmware/src/app/rpm_spectral_estimator.c/h` — `biba_rpm_spectral_estimate()`, `biba_rpm_spectral_apply_load_gate()`
- `firmware/src/app/rpm_pi.c/h` — `biba_rpm_pi_step()`, `BIBA_RPM_PI_*` defaults
- `firmware/src/app/rpm_dr.c/h` — `biba_rpm_dr_update()`
- `firmware/src/app/melody.c/h` — `biba_melody_player_tick()`
- `firmware/src/app/blackbox.c/h` — Не влияет на сигнал, вне скоупа

### Драйверы
- `firmware/src/drivers/bts7960.c/h` — `biba_bts7960_drive()`, `biba_bts7960_thermal_reset()`
- `firmware/src/drivers/crsf.c/h` — CRSF ingest
- `firmware/src/drivers/current_sense.c/h` — Current sensing for limiter
- `firmware/src/drivers/voltage_sense.c/h` — VBAT sensing

## Existing Code Insights

### Reusable Assets
- **`#ifndef` guard pattern**: `biba_config.h` уже использует `#ifndef BIBA_*` / `#define BIBA_*` / `#endif` — тумблеры используют тот же механизм
- **`BIBA_OPEN_LOOP` guard**: существующие `#ifndef BIBA_OPEN_LOOP` / `#endif` блоки в `mode_standalone.c` — будут заменены на каскад `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_*`
- **`target_config.h` override**: RP2040 target уже переопределяет дефолты — тумблеры следуют той же модели

### Established Patterns
- Все `#define` в `biba_config.h` следуют шаблону: `#ifndef NAME` / `#  define NAME value` / `#endif`
- Target-specific overrides в `targets/<TARGET>/target_config.h` без `#ifndef` (прямой `#define`)
- Функциональные модули имеют свой `.h` с конфигурационными дефолтами (напр. `rpm_pi.h` → `BIBA_RPM_PI_KP`)

### Integration Points
- **`mode_standalone.c:on_adc_pair_done()`** — DMA callback, здесь живут ZC, spectral, DR, PI, anti-stall, latch recovery. Основной участок для `#if`-гейтинга.
- **`mode_standalone.c:biba_mode_standalone_tick()`** — Главный tick, здесь: speed mode, deadband, heading-hold, mixer, limiter, ramp, melody, reverse pip.
- **`biba_config.h`** — Центральный конфиг. После реорганизации: ~17 секций с тумблерами + их параметрами.

## Specific Ideas

- Тумблер `BIBA_FEATURE_MIXER_PROJECTION=0` должен возвращать plain differential mix (`left=throttle+steer, right=throttle-steer` с `biba_clamp_unit`) — без L∞ ball projection, но с сохранением speed_scale
- Тумблер `BIBA_FEATURE_SPEED_MODE=0` должен фиксировать `speed_scale = 1.0` (full speed), игнорируя CH6
- Тумблер `BIBA_FEATURE_STEERING_DEADBAND=0` должен пропускать steering как есть, без deadband
- Тумблер `BIBA_FEATURE_HEADING_HOLD=0` должен пропускать вызов `biba_pid_step` даже если CH10 в положении STABILIZED
- Тумблер `BIBA_FEATURE_MELODY=0` должен пропускать `biba_melody_player_start/stop/tick` — моторы всегда управляются через `biba_bts7960_drive`, без audio-блокировки PWM
- Тумблер `BIBA_FEATURE_RPM_RAMP=0` должен подавать mixer-выход напрямую в target_hz, без `biba_ramp_update_with_rates`

## Deferred Ideas

- **Runtime-переключение тумблеров через serial** — полезно для полевого дебаггинга, но requires flash persistence + RAM. Возможная будущая фаза.
- **Motor trim repair for PI mode** — trim сейчас bypassed (несовместим с PI). Нужно переосмыслить как target_hz offset. Отдельная фича.
- **IMU integration for heading-hold** — ki=0 пока нет реального гироскопа. Когда появится — нужно будет перетюнить PID и включить ki.

---

*Phase: 12-Signal Chain Feature Gating*
*Context gathered: 2026-05-27*
