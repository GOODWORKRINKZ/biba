# Phase 9: RPM Estimator Hardening — Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Добавить dead-reckoning fallback в цикл измерения RPM: когда Goertzel estimator
возвращает `valid=false`, экстраполировать скорость из последнего валидного
измерения через EMA-соотношение `meas_hz / target_hz`, ограниченное по числу
последовательных invalid-циклов. Python-симуляция на sweep-данных является
обязательным gate перед написанием C-кода.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**7 requirements are locked.** See `09-SPEC.md` for full requirements, boundaries,
and acceptance criteria.

Downstream agents MUST read `09-SPEC.md` before planning or implementing.
Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `rpm_dr.h` / `rpm_dr.c` — DR state struct + `rpm_dr_update()` function
- `mode_standalone.c` — replace one-liner `spec_hz = valid ? freq : 0` with DR call
- `rpm_spectral_estimator.h` — add `BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED = 5` to enum
- `biba_config.h` — add `BIBA_RPM_DR_MAX_STREAK` (default 5) and `BIBA_RPM_DR_RATIO_LO/HI/ALPHA`
- Unit tests for DR state machine (streak, ratio update, clamp, cold start)
- Python simulation script `scripts/is_dr_sim.py` on fullsine amp100 sweep raw data

**Out of scope (from SPEC.md):**
- Modifying `rpm_spectral_estimator.c` logic or thresholds
- Modifying `zc_detector.c`
- Changing blackbox binary format or download script
- Per-wheel separate ratio constants in firmware (EMA adapts in-flight)
- IMU-assisted DR (no IMU in standalone mode)

</spec_lock>

<decisions>
## Implementation Decisions

### API: `rpm_dr_update()` signature

- **D-A1:** Функция возвращает `float` (экстраполированный или 0.0 Hz) и заполняет
  out-param `biba_rpm_spectral_invalid_reason_t *out_reason` — паттерн аналогичен
  `rpm_pi_step()`. Caller (`mode_standalone.c`) присваивает `s_spec_reason_left = out_reason`.

  ```c
  float biba_rpm_dr_update(
      biba_rpm_dr_state_t         *state,
      const biba_rpm_spectral_result_t *spec,
      float                        target_hz,
      biba_rpm_spectral_invalid_reason_t *out_reason   /* out: EXTRAPOLATED or original */
  );
  ```

- **D-A2:** Когда spec.valid == true: обновляем ratio_ema, возвращаем spec.freq_hz,
  *out_reason = BIBA_RPM_SPECTRAL_INVALID_NONE (0).
  Когда spec.valid == false, streak ≤ MAX_STREAK, ratio_ema > 0, target ≥ 50Hz:
  возвращаем ratio_ema × target_hz, *out_reason = BIBA_RPM_SPECTRAL_INVALID_EXTRAPOLATED (5).
  Иначе (холодный старт / streak истёк): возвращаем 0.0f, *out_reason = spec.invalid_reason.

- **D-A3:** Функция работает с магнитудами (spec.freq_hz ≥ 0, target_hz ≥ 0). Знак
  применяется в mode_standalone.c через `s_meas_left_reverse` — без изменений.

### Lifecycle: сброс DR state

- **D-L1:** `biba_rpm_dr_reset(biba_rpm_dr_state_t *state)` обнуляет `ratio_ema = 0.0f`
  и `streak = 0`. Вызывается в том же месте, что и `biba_rpm_pi_reset()` — при дисарме.
  Каждая сессия начинается с холодного старта (cold start).

- **D-L2:** Warm start (сохранение ratio_ema через перезарминг) — **не применяется**
  в этой фазе. При перезарминге в тех же условиях EMA набирается быстро (α=0.2,
  первое валидное измерение даёт ~20% веса).

### Python Simulation (`scripts/is_dr_sim.py`)

- **D-S1:** Скрипт **импортирует** из существующих портов:
  - `from is_sweepraw_analyze import spectral_estimate, SpectralResult` — Python Goertzel
  - `from is_algo_bench import alg_subwindow_schmitt` — Python ZC A2
  Дублирования кода нет; изменение параметров в портах автоматически отражается в симуляции.

- **D-S2:** Выход скрипта — **stdout + PNG artifact**:
  - stdout: таблица `before/after dropout rate` по duty-bins, строка `PASS / FAIL`
    (PASS если dropout < 5% при |duty| > 15%), exit code 0 или 1
  - PNG: график dropout rate before/after по duty-bins, сохраняется рядом со скриптом
    или в `scripts/artifacts/` (путь подходит для field notes)

- **D-S3:** REQ-06 acceptance gate: **< 5% dropout при |duty| > 15%** (из requirements
  SPEC.md REQ-06). SPEC.md D7 указывает < 10% — используем более строгое из двух (5%).

### Unit Tests

- **D-T1:** Новая директория `firmware/test/test_rpm_dr/` — консистентно с
  `test_rpm_pi/`, `test_zc_detector/`, `test_rpm_spectral_estimator/`.
  Требует новой записи в `platformio.ini` [env:native_test] test_filter.

### Agent Discretion

- Конкретный формат `biba_rpm_dr_state_t` (поля `ratio_ema`, `streak`, тип streak —
  uint8_t) — на усмотрение реализации, без опроса пользователя.
- PNG имя файла и путь сохранения — на усмотрение.
- Порядок вызовов в `platformio.ini` для нового теста — следовать существующему паттерну.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked Requirements
- `.planning/phases/09-rpm-estimator-hardening/09-SPEC.md` — **обязательно прочитать первым**;
  7 заблокированных требований, acceptance criteria, calibration data table, config defaults

### Firmware API Patterns (read before designing rpm_dr API)
- `firmware/src/app/rpm_pi.h` — паттерн `float func(state*, cfg*, target, meas)` и `_reset()`
- `firmware/src/app/rpm_spectral_estimator.h` — enum `biba_rpm_spectral_invalid_reason_t` (добавить =5)
- `firmware/src/app/zc_detector.h` — `zc_ema_update()` паттерн (magnitude-only EMA)

### Integration Point
- `firmware/src/modes/mode_standalone.c` — строки ~340–410: функция `on_adc_pair_done()`,
  одна строка `spec_hz_left = (enabled && spec_left.valid) ? spec_left.freq_hz : 0.0f;`
  — **именно её** заменяет DR вызов

### Python Algorithm Ports (для is_dr_sim.py)
- `scripts/is_sweepraw_analyze.py` — Python-порт `spectral_estimate()` (Goertzel, зеркало firmware)
- `scripts/is_algo_bench.py` — Python-порт `alg_subwindow_schmitt()` (ZC A2, зеркало firmware)

### Sweep Raw Data (входные данные для симуляции)
- `scripts/artifacts/is-sweepraw/sweepraw_SIN_amp100_per8000_n157_20260524-180629_fullsine_left.csv`
- `scripts/artifacts/is-sweepraw/sweepraw_SIN_amp100_per8000_n157_20260524-180629_fullsine_right.csv`
- Формат: `win_idx, t_ms, duty_pct, sample_idx, adc_raw` — 1024 samples/window, 157 windows

### Existing Test Pattern
- `firmware/test/test_rpm_pi/test_main.c` — паттерн `make_default_cfg()` + Unity assertions
- `firmware/test/test_rpm_spectral_estimator/` — второй образец отдельного test directory

### Calibration Context
Из SPEC.md таблица sweep calibration (fullsine amp100):
- LEFT FWD: mean ratio=0.805, std=0.242, p5=0.374, p95=1.129
- RIGHT FWD: mean ratio=0.845, std=0.104, p5=0.659, p95=0.988
- RIGHT REV: mean ratio=0.759, std=0.129, p5=0.426, p95=0.893
- Config defaults: RATIO_LO=0.50, RATIO_HI=1.30, ALPHA=0.2, MAX_STREAK=5

</canonical_refs>

<deferred>
## Deferred Ideas

- **Warm start через перезарминг** — ratio_ema сохраняется через disarm/rearm в рамках
  одного power cycle. Не реализуется в Phase 9 (cold start достаточен).
- **Per-wheel offline calibration constants** — статические initial_ratio_left/right
  в biba_config.h вместо старта с 0. Полезно при частых dropout на одном колесе, но
  усложняет конфиг. Отложено.

</deferred>
