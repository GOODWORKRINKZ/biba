# Phase 12: Signal Chain Feature Gating — Research

**Researched:** 2026-05-27
**Domain:** C preprocessor feature gating, firmware architecture audit, compile-time configuration
**Confidence:** HIGH

## Summary

Phase 12 transforms the current monolithic `biba_config.h` + single `BIBA_OPEN_LOOP` toggle into a structured system of 17 per-feature compile-time switches (`BIBA_FEATURE_*`), organized in the existing `#ifndef`/`#define`/`#endif` pattern with `target_config.h` override support. Every stage in the CRSF→motor-PWM signal chain that currently has code in `mode_standalone.c` receives its own toggle; any feature can be removed with a single `#define BIBA_FEATURE_<NAME> 0` in `target_config.h`.

**Primary recommendation:** Gate at call sites in `mode_standalone.c`, not in module `.c` files. All 17 toggles are controlled from a single reorganized `biba_config.h` with feature-scoped sections. Dependency `#error` checks go at the **bottom** of `biba_config.h`, after all toggles are defined and any target overrides are pulled in.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CRSF ingest | Firmware / HAL | — | Always present; no toggle |
| Arming / SSR | Firmware / HAL | — | Hardware safety interlocks; no toggle |
| Failsafe | Firmware / App | — | Critical safety; no toggle |
| Mixer (L∞ or differential) | Firmware / App | — | Core drive math; toggle only the projection algorithm |
| RPM measurement (ZC+spectral+DR) | Firmware / App (ISR) | — | DMA ISR context; gated by master RPM toggle |
| RPM control (PI+anti-stall) | Firmware / App (ISR) | — | DMA ISR writes, tick reads; gated by RPM master |
| Speed mode scaling | Firmware / App (tick) | — | Post-mixer scaling; independent toggle |
| Steering deadband | Firmware / App (tick) | — | Input conditioning; independent toggle |
| Heading-hold PID | Firmware / App (tick) | — | Drive correction; independent toggle |
| Current/power limiter | Firmware / App (tick) | — | Safety; independent toggle |
| Latch recovery | Firmware / App (ISR+tick) | — | Safety; independent toggle |
| RPM ramp | Firmware / App (tick) | — | Command shaping; independent toggle |
| Melody | Firmware / App (tick) | — | Audio; independent toggle |
| Reverse pip | Firmware / App (tick) | — | Audio+safety; independent toggle |
| BTS7960 drive output | Firmware / HAL | — | Always present; no toggle |
| Blackbox | Firmware / App | — | Already has CH7 trigger; no toggle |
| Debug serial | Firmware / App (tick) | — | Bench-test tool; no toggle |

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01**: All toggles are `#define BIBA_FEATURE_<NAME> 1` (or `0`) in `target_config.h`. No runtime switching, no flash persistence. Default = `1` (enabled) in `biba_config.h`.
- **D-02**: `BIBA_FEATURE_RPM_CLOSED_LOOP` is the master RPM switch. If `0`, ALL RPM sub-features are off regardless of individual toggles. Old `BIBA_OPEN_LOOP` removed; backward compat via `#ifdef BIBA_OPEN_LOOP` → `#define BIBA_FEATURE_RPM_CLOSED_LOOP 0` + `#warning`.
- **D-03**: 17 toggles total covering RPM chain (7), Safety (2), Comfort (4), Drive (3).
- **D-04**: `biba_config.h` reorganized into feature-scoped sections with comment headers. Each section contains the toggle + all parameters for that feature.
- **D-05**: Critical safety features (failsafe, SSR, arming, CRSF ingest, BTS7960 drive, blackbox, debug serial) have NO toggles.
- **D-06**: Dependency `#error` checks: PI→DR, DUAL_WINDOW→SPECTRAL, LOAD_GATE→SPECTRAL, ANTI_STALL→SPECTRAL. No checks when RPM_CLOSED_LOOP=0.
- **D-07**: RP2040 defaults: all toggles=1, HEADING_HOLD=1, REVERSE_PIP=0, MELODY=1.

### the Agent's Discretion
Not applicable — all decisions made by user.

### Deferred Ideas (OUT OF SCOPE)
- Runtime toggle switching via serial
- Motor trim repair for PI mode
- IMU integration for heading-hold (ki re-tune)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FEAT-01 | Each of 17 chain features has BIBA_FEATURE_<NAME> toggle in biba_config.h, disable-able by one define | Sections 4, 6 — Complete toggle-to-code mapping with line numbers |
| FEAT-02 | BIBA_FEATURE_RPM_CLOSED_LOOP=0 equivalent to old BIBA_OPEN_LOOP | Sections 3, 12 — Migration path and backward compat documented |
| FEAT-03 | biba_config.h reorganized with feature sections | Section 5 — Section ordering and parameter grouping plan |
| FEAT-04 | Dependency violations caught by #error at compile time | Section 8 — Dependency validation strategy with exact #error checks |
</phase_requirements>

## 1. Codebase Map — All 17 Toggles

### 1.1 RPM Chain (Master: `BIBA_FEATURE_RPM_CLOSED_LOOP`)

| # | Toggle | File | Lines | Function | Current Guard | Parameters |
|---|--------|------|-------|----------|---------------|------------|
| 1 | `BIBA_FEATURE_RPM_ZC` | `mode_standalone.c` | 389-393 | `on_adc_pair_done()` | `#ifndef BIBA_OPEN_LOOP` (outer block) | ZC_SUBWIN_K, ZC_SUBWIN_MIN_PKPK, ZC_SUBWIN_MIN_STD, ZC_MIN_VALID_HZ, ZC_EMA_ALPHA (in `zc_detector.h`) |
| 2 | `BIBA_FEATURE_RPM_SPECTRAL` | `mode_standalone.c` | 395-400 | `on_adc_pair_done()` | `#ifndef BIBA_OPEN_LOOP` (outer block) | BIBA_RPM_SPECTRAL_MIN_TARGET_HZ, BIBA_RPM_SPECTRAL_MAX_TARGET_HZ, BIBA_RPM_SPECTRAL_REL_BAND, BIBA_RPM_SPECTRAL_ABS_BAND_HZ, BIBA_RPM_SPECTRAL_MIN_PEAK_AMP_LSB, BIBA_RPM_SPECTRAL_MIN_QUALITY (in `rpm_spectral_estimator.h`) |
| 3 | `BIBA_FEATURE_RPM_DUAL_WINDOW` | `mode_standalone.c` | 430-437 | `on_adc_pair_done()` (hint_hz update) | `#ifndef BIBA_OPEN_LOOP` (outer block) | hint_hz variables (s_hint_hz_left/right) — defined at lines 126-127 |
| 4 | `BIBA_FEATURE_RPM_LOAD_GATE` | `mode_standalone.c` | 402 | `on_adc_pair_done()` | `#ifndef BIBA_OPEN_LOOP` (outer block) | BIBA_RPM_LOAD_RATIO_THRESH, BIBA_RPM_LOAD_QUALITY_MAX, BIBA_RPM_LOAD_ABS_THRESH_ADC (in `biba_config.h` lines 293-302) |
| 5 | `BIBA_FEATURE_RPM_DR` | `mode_standalone.c` | 443-451 | `on_adc_pair_done()` | `#ifndef BIBA_OPEN_LOOP` (outer block) | BIBA_RPM_DR_MAX_STREAK, BIBA_RPM_DR_RATIO_LO, BIBA_RPM_DR_RATIO_HI, BIBA_RPM_DR_ALPHA (in `biba_config.h` lines 279-291) |
| 6 | `BIBA_FEATURE_RPM_PI` | `mode_standalone.c` | 475-480 | `on_adc_pair_done()` | `#ifndef BIBA_OPEN_LOOP` (outer block) | BIBA_RPM_PI_KP, KI, KI_LOW, KI_LOW_THRESH, FF_SLOPE, FF_DEAD, STICTION, P_CLAMP, DT_S (in `rpm_pi.h` lines 51-59) |
| 7 | `BIBA_FEATURE_RPM_ANTI_STALL` | `mode_standalone.c` | 404-427 | `on_adc_pair_done()` | `#ifndef BIBA_OPEN_LOOP` (outer block) | ANTISTALL_RAMP_STEP, ANTISTALL_MAX_DUTY, ANTISTALL_CONFIRM (lines 213-215), plus s_antistall_* state variables (lines 216-220) |

### 1.2 Safety

| # | Toggle | File | Lines | Function | Current Guard | Parameters |
|---|--------|------|-------|----------|---------------|------------|
| 8 | `BIBA_FEATURE_LATCH_RECOVERY` | `mode_standalone.c` | 500-550 (ISR), 768-784 (tick) | `on_adc_pair_done()` + `tick()` | NONE — always runs | LATCH_IS_RAW_MIN (line 200), LATCH_BLOCKS_CONFIRM (line 202), LATCH_COOLDOWN_WINDOWS (line 203), s_latch_* state (lines 204-208) |
| 9 | `BIBA_FEATURE_CURRENT_LIMITER` | `mode_standalone.c` | 557-571 (function), 915-921 (call site) | `apply_drive_current_limits()` + `tick()` | NONE — always runs | BIBA_LEFT/RIGHT_MAX_CURRENT_A, BIBA_LEFT/RIGHT_MAX_POWER_W, BIBA_FALLBACK_SUPPLY_V (in `biba_config.h` lines 58-71) |

### 1.3 Comfort

| # | Toggle | File | Lines | Function | Current Guard | Parameters |
|---|--------|------|-------|----------|---------------|------------|
| 10 | `BIBA_FEATURE_STEERING_DEADBAND` | `mode_standalone.c` | 815-820 | `tick()` | NONE — always runs | BIBA_STEERING_DEADBAND (in `biba_config.h` line 196) |
| 11 | `BIBA_FEATURE_RPM_RAMP` | `mode_standalone.c` | 927-943 | `tick()` | `#ifndef BIBA_OPEN_LOOP` | BIBA_RPM_SETPOINT_ACCEL_RATE, DECEL_RATE, REVERSE_DECEL_RATE, ZERO_HOLD_MS (in `biba_config.h` lines 244-255) |
| 12 | `BIBA_FEATURE_MELODY` | `mode_standalone.c` | 617 (init), 705 (failsafe), 727 (arm), 744 (disarm), 863 (trim exit), 1055 (stop on control), 1095 (stop on !pip), 1141 (beacon), 1201-1208 (tick/drive) | `init()` + `tick()` | NONE — always runs | s_player (line 176), melody catalog (in `melody.c`), melody.h API |
| 13 | `BIBA_FEATURE_REVERSE_PIP` | `mode_standalone.c` | ~1080-1104 | `tick()` | `#if BIBA_REVERSE_PIP_ENABLED` (existing pattern, line ~1080) | BIBA_REVERSE_PIP_ENABLED, BIBA_REVERSE_PIP_INTERVAL_MS (in `biba_config.h` lines 210-214), s_reversing, s_reverse_pip_active, s_reverse_pip_next_ms (lines 179-181) |

### 1.4 Drive

| # | Toggle | File | Lines | Function | Current Guard | Parameters |
|---|--------|------|-------|----------|---------------|------------|
| 14 | `BIBA_FEATURE_HEADING_HOLD` | `mode_standalone.c` | 824-830 | `tick()` | NONE — always runs (but ki=0) | s_heading_pid (line 82), s_heading_cfg (lines 85-88), BIBA_CH_DRIVE_MODE, BIBA_DRIVE_MODE_LOW_THRESHOLD (in `biba_config.h`) |
| 15 | `BIBA_FEATURE_SPEED_MODE` | `mode_standalone.c` | 790-797 | `tick()` | NONE — always runs | BIBA_SPEED_MODE_LOW/HIGH_THRESHOLD, BIBA_SPEED_MODE_SLOW/MEDIUM/FAST_SCALE (in `biba_config.h` lines 161-174), BIBA_CH_SPEED_MODE |
| 16 | `BIBA_FEATURE_MIXER_PROJECTION` | `mode_standalone.c` | 898-914 | `tick()` | NONE — always runs | L∞ ball inline math (lines 902-914); fallback uses `biba_mix_differential()` (in `control_loop.h` line 91, **not currently called anywhere**) |

**NOTE:** `biba_mix_differential()` is defined in `control_loop.h` (line 91) and implemented in `control_loop.c` (line 120-127) but is **never called** in the current codebase. The mixer code is inlined at lines 898-914 of `mode_standalone.c`. When `BIBA_FEATURE_MIXER_PROJECTION=0`, the inlined L∞ ball code must be replaced with a call to `biba_mix_differential(throttle, steering)` with `speed_scale` applied post-mix.

## 2. Current `#ifdef` Audit

### 2.1 In `mode_standalone.c`

| Guard | Lines | What It Guards | Replacement |
|-------|-------|----------------|-------------|
| `#ifndef BIBA_OPEN_LOOP` | 388-490 | ZC, spectral, DR, PI, anti-stall (entire ISR RPM chain) | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && (BIBA_FEATURE_RPM_ZC \|\| BIBA_FEATURE_RPM_SPECTRAL \|\| ...)` — individual sub-toggles inside |
| `#ifndef BIBA_OPEN_LOOP` | 927-1004 | RPM ramp + PI duty assignment in tick() | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_RAMP` for ramp; separate `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_PI` for PI duty |
| `#ifdef BIBA_OPEN_LOOP` | 1176 | Blackbox rpm_hz field = 0 | `#if !BIBA_FEATURE_RPM_CLOSED_LOOP` (negated) |
| `#if BIBA_REVERSE_PIP_ENABLED` | ~1080-1104 | Reverse backup pip | Migrate to `#if BIBA_FEATURE_REVERSE_PIP` |
| *(none)* | Various | Latch recovery, current limiter, deadband, heading hold, speed mode, mixer, melody | ADD new `#if BIBA_FEATURE_<NAME>` guards |

### 2.2 In `biba_config.h`

| Guard Pattern | Purpose | Migration |
|---------------|---------|-----------|
| `#define BIBA_OPEN_LOOP` (line 310, **unconditional**) | Global open-loop mode | Removed. Replaced by `#ifndef BIBA_FEATURE_RPM_CLOSED_LOOP` / `#  define BIBA_FEATURE_RPM_CLOSED_LOOP 1` / `#endif` |
| `#ifndef BIBA_REVERSE_PIP_ENABLED` / `#  define BIBA_REVERSE_PIP_ENABLED 0` (lines 210-211) | Reverse pip toggle | Renamed to `#ifndef BIBA_FEATURE_REVERSE_PIP` / `#  define BIBA_FEATURE_REVERSE_PIP 0` |
| All other `#ifndef BIBA_*` | Config parameters | Reorganized into feature-scoped sections; each section starts with its `BIBA_FEATURE_<NAME>` toggle |

## 3. Integration Point Map — Exact Gate Locations

All gates are in **`firmware/src/modes/mode_standalone.c`** (1277 lines total).

### 3.1 `on_adc_pair_done()` (DMA ISR callback, GPIO pin ISR context)

| Toggle | Line Range | Gate Logic | Behavior When OFF |
|--------|-----------|------------|-------------------|
| RPM_ZC | 389-393 | `#if BIBA_FEATURE_RPM_ZC` | `zc_left = zc_right = {0}`; `raw_hz_left/right = 0.0f` |
| RPM_SPECTRAL | 395-400 | `#if BIBA_FEATURE_RPM_SPECTRAL` | `spec_left = spec_right = {0}` |
| RPM_LOAD_GATE | 402 | `#if BIBA_FEATURE_RPM_LOAD_GATE` | Skip `biba_rpm_spectral_apply_load_gate()` |
| RPM_ANTI_STALL | 404-427 | `#if BIBA_FEATURE_RPM_ANTI_STALL` | `s_antistall_duty_left/right = 0.0f` |
| RPM_DUAL_WINDOW | 430-437 | `#if BIBA_FEATURE_RPM_DUAL_WINDOW` | Don't update `s_hint_hz_left/right` |
| RPM_DR | 443-451 | `#if BIBA_FEATURE_RPM_DR` | `spec_hz_left/right = spec_left/right.freq_hz` (when valid); 0.0f otherwise |
| RPM_PI | 475-480 | `#if BIBA_FEATURE_RPM_PI` | `s_rpm_duty_left/right = 0.0f` |
| LATCH_RECOVERY | 500-550 | `#if BIBA_FEATURE_LATCH_RECOVERY` | Skip latch detection logic; `s_latch_reset_pending = false` |

**Critical ordering within ISR:** The ZC → SPECTRAL → LOAD_GATE → DUAL_WINDOW → DR → PI → ANTI_STALL override pipeline is sequential within the `#ifndef BIBA_OPEN_LOOP` block. Each gate must produce default values that the next stage can consume safely. DR needs spec results; PI needs DR results; anti-stall override needs PI results.

**Default value cascade when RPM_CLOSED_LOOP=0:**
- All `s_rpm_duty_left/right = 0.0f` (then tick assigns `left_out/right_out` from mixer directly)
- All telemetry variables (`s_spec_hz_*`, `s_pi_meas_hz_*`, etc.) = 0.0f
- `s_meas_left/right_enabled` remains set by tick (used by latch recovery)

### 3.2 `biba_mode_standalone_init()` (lines 577-622)

| Toggle | Line | Gate Logic | Behavior When OFF |
|--------|------|------------|-------------------|
| MELODY | 617 | `#if BIBA_FEATURE_MELODY` | Skip `biba_melody_player_start(&s_player, &biba_melody_startup)` — motors always through `biba_bts7960_drive` from boot |
| RPM_PI (config init) | 588-597 | `#if BIBA_FEATURE_RPM_PI` | Skip PI config init and `biba_rpm_pi_reset()` |
| RPM_DR (init) | 599-600 | `#if BIBA_FEATURE_RPM_DR` | Skip `biba_rpm_dr_reset()` |
| RPM_RAMP (init) | 602-603 | `#if BIBA_FEATURE_RPM_RAMP` | Skip `biba_ramp_init()` |
| RPM_CLOSED_LOOP (master) | 588-606 | Outer `#if BIBA_FEATURE_RPM_CLOSED_LOOP` | Skip ALL RPM init |

### 3.3 `biba_mode_standalone_tick()` (lines 628-1277)

| Toggle | Line | Gate Logic | Behavior When OFF |
|--------|------|------------|-------------------|
| MELODY | 705 | `#if BIBA_FEATURE_MELODY` | Skip failsafe melody start |
| MELODY | 727 | `#if BIBA_FEATURE_MELODY` | Skip arm melody start |
| MELODY | 744 | `#if BIBA_FEATURE_MELODY` | Skip disarm melody start |
| MELODY | 863 | `#if BIBA_FEATURE_MELODY` | Skip trim exit melody |
| SPEED_MODE | 790-797 | `#if BIBA_FEATURE_SPEED_MODE` | `speed_scale = 1.0f` |
| STEERING_DEADBAND | 815-820 | `#if BIBA_FEATURE_STEERING_DEADBAND` | `steering = raw_steering` (pass through) |
| HEADING_HOLD | 824-830 | `#if BIBA_FEATURE_HEADING_HOLD` | Skip `biba_pid_step()`; steering unchanged |
| MIXER_PROJECTION | 898-914 | `#if BIBA_FEATURE_MIXER_PROJECTION` | Use `biba_mix_differential(throttle, steering)`, then `mix.left *= speed_scale; mix.right *= speed_scale; biba_clamp_unit()` each |
| CURRENT_LIMITER | 915-921 | `#if BIBA_FEATURE_CURRENT_LIMITER` | `left_out = mix.left; right_out = mix.right` (no limiting) |
| RPM_RAMP | 927-943 | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_RAMP` | `left_out/right_out` from mixer go directly to target_hz conversion (skip ramp) |
| RPM directional logic | 948-999 | `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_PI` | PI duty assignment and direction-flip logic; `left_out/right_out` already hold mixer output |
| LATCH_RECOVERY | 768-784 | `#if BIBA_FEATURE_LATCH_RECOVERY` | Skip latch reset in tick context |
| REVERSE_PIP | ~1080-1104 | `#if BIBA_FEATURE_REVERSE_PIP` | `s_reverse_pip_active = false; s_reverse_pip_next_ms = 0u` |
| MELODY | 1055 | `#if BIBA_FEATURE_MELODY` | Skip melody stop on control active |
| MELODY | 1073 | `#if BIBA_FEATURE_MELODY` | Skip melody stop on pip end |
| MELODY | 1095 | `#if BIBA_FEATURE_MELODY` | Skip melody stop on !reverse |
| MELODY | 1141 | `#if BIBA_FEATURE_MELODY` | Skip beacon/SOS melody |
| MELODY | 1201-1208 | `#if BIBA_FEATURE_MELODY` | Both `biba_melody_player_tick_biased()` and `biba_melody_player_tick()` skipped |
| MELODY | 1212 | Gate on melody active | `if (!s_player.active)` → drives motors; when MELODY=0, `s_player.active` is always false → motors always driven |

### 3.4 Blackbox Record (line 1176)

| Toggle | Line | Gate Logic | Behavior When OFF |
|--------|------|------------|-------------------|
| RPM_CLOSED_LOOP (master) | 1176-1178 | `#if !BIBA_FEATURE_RPM_CLOSED_LOOP` | `rec.rpm_left_hz10 = rec.rpm_right_hz10 = 0` |

## 4. Variables Gated by Each Toggle

Some state variables are ONLY needed when the corresponding feature is enabled. The planner should consider `#if`-gating the variable declarations themselves to save RAM.

| Toggle | State Variables (RAM) | Approx. RAM Saved if OFF |
|--------|----------------------|--------------------------|
| RPM_PI | `s_rpm_pi_left`, `s_rpm_pi_right`, `s_rpm_cfg` | ~76 bytes (2 × 36-byte state + 36-byte config) |
| RPM_DR | `s_dr_left`, `s_dr_right` | ~16 bytes (2 × 8-byte state) |
| RPM_RAMP | `s_rpm_setpoint_ramp_left`, `s_rpm_setpoint_ramp_right` | ~16 bytes (2 × 8-byte ramp) |
| RPM_DUAL_WINDOW | `s_hint_hz_left`, `s_hint_hz_right` | 8 bytes (2 × float) |
| RPM_ANTI_STALL | `s_antistall_cnt_*`, `s_antistall_duty_*` | ~16 bytes |
| LATCH_RECOVERY | `s_latch_cnt_*`, `s_latch_reset_pending`, `s_latch_cooldown`, `s_latch_resets` | ~9 bytes |
| HEADING_HOLD | `s_heading_pid`, `s_heading_cfg` | ~44 bytes |
| MELODY | `s_player` | ~24 bytes (melody_player_t) |
| REVERSE_PIP | `s_reversing`, `s_reverse_pip_active`, `s_reverse_pip_next_ms` | ~10 bytes |
| STEERING_DEADBAND | *(none — pure computation)* | 0 |
| SPEED_MODE | *(none — pure computation)* | 0 |
| MIXER_PROJECTION | *(none — pure computation)* | 0 |
| CURRENT_LIMITER | *(none — pure computation)* | 0 |
| RPM_ZC | *(none — local stack vars)* | 0 |
| RPM_SPECTRAL | *(none — local stack vars)* | 0 |
| RPM_LOAD_GATE | *(none — local stack vars)* | 0 |

**Total potential RAM savings:** ~219 bytes (significant on RP2040 with 264KB SRAM — not critical but good practice).

## 5. Config Reorganization Plan — `biba_config.h`

### 5.1 Proposed Section Order

```
1. Preamble + include guard (keep existing)
2. Target config include (#include "target_config.h") (keep existing)
3. BIBA_NATIVE_TEST fallback section (keep existing)
   ─── CRITICAL SAFETY (NO TOGGLES) ───
4. Control loop timing (BIBA_CONTROL_LOOP_HZ, BIBA_TELEMETRY_PUBLISH_HZ)
5. Motor / PWM base (BIBA_PWM_FREQUENCY_HZ, BIBA_PWM_DEADTIME_NS, BIBA_BTS7960_RESET_PULSE_US)
6. CRSF link (BIBA_CRSF_BAUD, BIBA_CRSF_TIMEOUT_MS)
7. RC channel assignments (BIBA_CH_THROTTLE, STEERING, ARM, SPEED_MODE, DRIVE_MODE, BEACON, TRIM, BLACKBOX)
8. Arm threshold (BIBA_ARM_THRESHOLD)
9. Failsafe motor deadband (BIBA_MOTOR_DEADBAND)
10. Motor direction (BIBA_LEFT_MOTOR_DIR, BIBA_RIGHT_MOTOR_DIR)
11. System / SPI (BIBA_SYS_CLOCK_HZ, BIBA_SPI_LINK_TIMEOUT_MS)
   ─── FEATURE TOGGLES ───
12. Feature: RPM Closed-Loop Master (BIBA_FEATURE_RPM_CLOSED_LOOP)
    [BACKWARD COMPAT: #ifdef BIBA_OPEN_LOOP → #define BIBA_FEATURE_RPM_CLOSED_LOOP 0 + #warning]
13. Feature: RPM ZC Detector (BIBA_FEATURE_RPM_ZC)
    + params: ZC_SUBWIN_K, ZC_SUBWIN_MIN_PKPK, ZC_SUBWIN_MIN_STD, ZC_MIN_VALID_HZ, ZC_EMA_ALPHA
    [MOVED from zc_detector.h — these are user-tunable]
14. Feature: RPM Spectral Estimator (BIBA_FEATURE_RPM_SPECTRAL)
    + params: BIBA_RPM_SPECTRAL_MIN_TARGET_HZ, MAX_TARGET_HZ, REL_BAND, ABS_BAND_HZ,
             MIN_PEAK_AMP_LSB, MIN_QUALITY
15. Feature: RPM Dual-Window Search (BIBA_FEATURE_RPM_DUAL_WINDOW)
    + params: (currently none beyond hint_hz — if dual-window gets its own band params, add here)
16. Feature: RPM IS-Pin Load Gate (BIBA_FEATURE_RPM_LOAD_GATE)
    + params: BIBA_RPM_LOAD_RATIO_THRESH, BIBA_RPM_LOAD_QUALITY_MAX, BIBA_RPM_LOAD_ABS_THRESH_ADC
17. Feature: RPM Dead Reckoning (BIBA_FEATURE_RPM_DR)
    + params: BIBA_RPM_DR_MAX_STREAK, BIBA_RPM_DR_RATIO_LO, BIBA_RPM_DR_RATIO_HI, BIBA_RPM_DR_ALPHA
18. Feature: RPM PI Controller (BIBA_FEATURE_RPM_PI)
    + params: BIBA_RPM_PI_KP, KI, KI_LOW, KI_LOW_THRESH, FF_SLOPE, FF_DEAD, STICTION, P_CLAMP, DT_S
19. Feature: RPM Anti-Stall (BIBA_FEATURE_RPM_ANTI_STALL)
    + params: ANTISTALL_RAMP_STEP, ANTISTALL_MAX_DUTY, ANTISTALL_CONFIRM
20. Feature: RPM Calibration (BIBA_RPM_GEAR_RATIO, COMMUTATOR_BARS, PULSES_PER_WHEEL_REV, RPM_MAX_HZ)
    [Not toggleable individually — calibration is data, not a feature]
21. Feature: Latch Recovery (BIBA_FEATURE_LATCH_RECOVERY)
    + params: LATCH_IS_RAW_MIN, LATCH_BLOCKS_CONFIRM, LATCH_COOLDOWN_WINDOWS
22. Feature: Current Limiter (BIBA_FEATURE_CURRENT_LIMITER)
    + params: BIBA_LEFT_MAX_CURRENT_A, BIBA_RIGHT_MAX_CURRENT_A,
             BIBA_LEFT_MAX_POWER_W, BIBA_RIGHT_MAX_POWER_W, BIBA_FALLBACK_SUPPLY_V
23. Feature: Steering Deadband (BIBA_FEATURE_STEERING_DEADBAND)
    + params: BIBA_STEERING_DEADBAND
24. Feature: RPM Setpoint Ramp (BIBA_FEATURE_RPM_RAMP)
    + params: BIBA_RPM_SETPOINT_ACCEL_RATE, DECEL_RATE, REVERSE_DECEL_RATE, ZERO_HOLD_MS
25. Feature: Motor Coil Melody (BIBA_FEATURE_MELODY)
    + params: (melody data in melody.c — no config params beyond toggle)
26. Feature: Reverse Backup Pip (BIBA_FEATURE_REVERSE_PIP)
    + params: BIBA_REVERSE_PIP_INTERVAL_MS
    [Migration: rename BIBA_REVERSE_PIP_ENABLED → BIBA_FEATURE_REVERSE_PIP]
27. Feature: Heading Hold (BIBA_FEATURE_HEADING_HOLD)
    + params: s_heading_cfg (PID gains — could move here from mode_standalone.c)
28. Feature: Speed Mode (BIBA_FEATURE_SPEED_MODE)
    + params: BIBA_SPEED_MODE_LOW_THRESHOLD, HIGH_THRESHOLD, SLOW_SCALE, MEDIUM_SCALE, FAST_SCALE
29. Feature: Mixer Projection (BIBA_FEATURE_MIXER_PROJECTION)
    + params: (none currently — L∞ ball has no configurable parameters)
   ─── NON-FEATURE CONFIG ───
30. Current sense calibration (BIBA_IS_ZERO_OFFSET_V, BIBA_IS_AMPS_PER_VOLT)
31. Battery (BIBA_VBAT_DIVIDER_RATIO, BIBA_IBAT_AMPS_PER_VOLT, BIBA_IBAT_ZERO_OFFSET_V,
              BIBA_RAIL_12V_DIVIDER_RATIO, BIBA_ADC_VREF_V, BIBA_ADC_MAX_COUNTS)
32. Motor trim (BIBA_MOTOR_TRIM_MAX_EFFECT, BIBA_TRIM_GESTURE_THRESHOLD, BIBA_TRIM_CONFIRM_HOLD_MS)
33. Motor ramp (BIBA_RAMP_ACCEL_RATE, DECEL_RATE, REVERSE_DECEL_RATE, ZERO_HOLD_MS)
34. Blackbox (BIBA_BLACKBOX_RATE_HZ, FIELD_MASK, MIN_FREE_KB, BIBA_CH_BLACKBOX)
   ─── DEPENDENCY VALIDATION ───
35. #error checks (see Section 8)
   ─── BACKWARD COMPAT ───
36. BIBA_OPEN_LOOP deprecation (see Section 12)
```

### 5.2 Section Template (per CONTEXT.md D-04)

```c
/* --- Feature: RPM PI Controller ---------------------------------------- */
#ifndef BIBA_FEATURE_RPM_PI
#  define BIBA_FEATURE_RPM_PI             1
#endif
#ifndef BIBA_RPM_PI_KP
#  define BIBA_RPM_PI_KP                  0.003f
#endif
#ifndef BIBA_RPM_PI_KI
#  define BIBA_RPM_PI_KI                  0.010f
#endif
/* ... remaining params ... */
```

## 6. Parameters That Move Files

These parameters currently live in module `.h` files but should move to `biba_config.h` feature sections so all feature-config is in one place:

| Parameter | Current Location | Move To |
|-----------|-----------------|---------|
| ZC_SUBWIN_K, ZC_SUBWIN_MIN_PKPK, ZC_SUBWIN_MIN_STD, ZC_MIN_VALID_HZ, ZC_EMA_ALPHA | `zc_detector.h` lines 24-65 | `biba_config.h` → Feature: RPM ZC Detector |
| BIBA_RPM_SPECTRAL_MIN_TARGET_HZ, MAX_TARGET_HZ, REL_BAND, ABS_BAND_HZ, MIN_PEAK_AMP_LSB, MIN_QUALITY | `rpm_spectral_estimator.h` lines 11-16 | `biba_config.h` → Feature: RPM Spectral Estimator |
| BIBA_RPM_PI_KP, KI, KI_LOW, KI_LOW_THRESH, FF_SLOPE, FF_DEAD, STICTION, P_CLAMP, DT_S | `rpm_pi.h` lines 51-59 | `biba_config.h` → Feature: RPM PI Controller |

**Risk:** These constants are included by other `.c` files (e.g., `rpm_dr.h` includes `rpm_spectral_estimator.h`). Moving them to `biba_config.h` requires ensuring `biba_config.h` is included before these headers, which it already is — `mode_standalone.c` line 14: `#include "biba_config.h"` comes first.

**Migration strategy:**
1. Copy definitions into `biba_config.h` with `#ifndef` guards
2. Wrap originals in module `.h` files with `#ifndef` guards (so `biba_config.h` wins)
3. OR: replace originals with `#include "biba_config.h"` at top of each module `.h`

**Recommendation:** Option 1 (copy + `#ifndef` guards in both places). During Phase 12 transition, keep originals in module `.h` files with `#ifndef` guards so nothing breaks if include order changes. Mark with `/* Moved to biba_config.h — keep for backward compat */`. Clean up in a follow-up phase.

## 7. Parameters That Stay Local

| Constant | Location | Reason |
|----------|----------|--------|
| LATCH_IS_RAW_MIN, LATCH_BLOCKS_CONFIRM, LATCH_COOLDOWN_WINDOWS | `mode_standalone.c` lines 200-203 | Used only in latch detection ISR; tied to hardware specifics |
| ANTISTALL_RAMP_STEP, ANTISTALL_MAX_DUTY, ANTISTALL_CONFIRM | `mode_standalone.c` lines 213-215 | Used only in anti-stall logic; simple thresholds |
| STANDALONE_RPM_MAX_HZ | `mode_standalone.c` line 172 | Local calibration constant |
| STANDALONE_RPM_SAMPLES_PER_WHEEL, ADC_AGGREGATE_SPS, WHEEL_SPS | `mode_standalone.c` lines 131-133 | Hardware timing constants |
| s_heading_cfg PID gains | `mode_standalone.c` lines 85-88 | Currently hardcoded; could move to biba_config.h as BIBA_HEADING_KP/KI/KD |

## 8. Dependency Validation Strategy

### 8.1 `#error` Checks (placed at END of `biba_config.h`, after all toggles defined)

```c
/* --- Dependency validation ---------------------------------------------- */
#if BIBA_FEATURE_RPM_CLOSED_LOOP
#  if BIBA_FEATURE_RPM_PI && !BIBA_FEATURE_RPM_DR
#    error "BIBA_FEATURE_RPM_PI requires BIBA_FEATURE_RPM_DR (PI uses DR as measurement source)"
#  endif
#  if BIBA_FEATURE_RPM_DUAL_WINDOW && !BIBA_FEATURE_RPM_SPECTRAL
#    error "BIBA_FEATURE_RPM_DUAL_WINDOW requires BIBA_FEATURE_RPM_SPECTRAL (hint is a second Goertzel search)"
#  endif
#  if BIBA_FEATURE_RPM_LOAD_GATE && !BIBA_FEATURE_RPM_SPECTRAL
#    error "BIBA_FEATURE_RPM_LOAD_GATE requires BIBA_FEATURE_RPM_SPECTRAL (gate applied to spectral result)"
#  endif
#  if BIBA_FEATURE_RPM_ANTI_STALL && !BIBA_FEATURE_RPM_SPECTRAL
#    error "BIBA_FEATURE_RPM_ANTI_STALL requires BIBA_FEATURE_RPM_SPECTRAL (uses HIGH_LOAD from spectral)"
#  endif
#endif /* BIBA_FEATURE_RPM_CLOSED_LOOP */

/* --- Master-switch consistency ------------------------------------------ */
#if !BIBA_FEATURE_RPM_CLOSED_LOOP
/* When the master is off, all sub-features are implicitly disabled.
 * Individual sub-feature settings are ignored — this is documented, not an error. */
#endif
```

### 8.2 Why `#error` at the BOTTOM of `biba_config.h`

1. All toggles must be defined first (with `#ifndef` guards allowing target override)
2. `#include "target_config.h"` is pulled in near the top (line 21 of current `biba_config.h`)
3. After all `#ifndef`-guarded defaults + target overrides, we know the FINAL value of each toggle
4. `#error` checks at the bottom see the resolved values

### 8.3 `#warning` for Soft Deprecation

```c
/* Backward compatibility: old BIBA_OPEN_LOOP maps to master switch */
#ifdef BIBA_OPEN_LOOP
#  warning "BIBA_OPEN_LOOP is deprecated — use BIBA_FEATURE_RPM_CLOSED_LOOP=0 instead"
#  undef BIBA_FEATURE_RPM_CLOSED_LOOP
#  define BIBA_FEATURE_RPM_CLOSED_LOOP 0
#endif
```

## 9. Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature flag system | Custom preprocessor framework | C `#if`/`#ifdef`/`#error` with `#ifndef`-guard pattern already used in `biba_config.h` | No need for external tools; Kconfig would be overkill for 17 toggles |
| Build matrix testing | Custom script to test all toggle combos | PlatformIO `build_flags` per env | Can define multiple `[env:rpico_no_rpm]` with `-DBIBA_FEATURE_RPM_CLOSED_LOOP=0` |
| Config validation at build time | Runtime assertions | `#error` at compile time | Catches misconfiguration before flashing; zero runtime cost |

## 10. Architecture Patterns

### 10.1 Gate-at-Call-Site Pattern

All `#if` guards go in `mode_standalone.c` at the point where the feature function is called, NOT inside the module's own `.c` file. Rationale:
- Each module `.c`/`.h` remains a pure, reusable library
- The "orchestration" file (`mode_standalone.c`) owns the composition decisions
- Tests of individual modules don't need to care about feature gating

### 10.2 Default-Value Pattern for Disabled Features

When a feature is off, the code must set sensible defaults:

```c
#if BIBA_FEATURE_SPEED_MODE
    /* ... 3-position switch logic ... */
#else
    float speed_scale = 1.0f;
#endif
```

Or for chained dependencies:

```c
#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_PI
    s_rpm_duty_left = biba_rpm_pi_step(...);
#else
    s_rpm_duty_left = 0.0f;
#endif
```

### 10.3 State Variable Gating

Variables only needed when the feature is enabled:

```c
#if BIBA_FEATURE_RPM_PI
static biba_rpm_pi_state_t  s_rpm_pi_left;
static biba_rpm_pi_state_t  s_rpm_pi_right;
static biba_rpm_pi_config_t s_rpm_cfg;
#endif
```

**Caution:** The blackbox record (line 1176) and telemetry (lines 1218-1277) reference `s_rpm_pi_left.integral` etc. These references must also be gated or use default-zero values.

### 10.4 Include Gating Pattern

Module headers that become unnecessary when a feature is off:

```c
#if BIBA_FEATURE_RPM_PI
#include "app/rpm_pi.h"
#endif
```

**Current includes in mode_standalone.c (lines 11-31) that COULD be gated:**
- `#include "app/zc_detector.h"` — gated by RPM_ZC || RPM_SPECTRAL (both need ZC)
- `#include "app/rpm_spectral_estimator.h"` — gated by RPM_SPECTRAL
- `#include "app/rpm_pi.h"` — gated by RPM_PI
- `#include "app/rpm_dr.h"` — gated by RPM_DR
- `#include "app/melody.h"` — gated by MELODY || REVERSE_PIP
- `#include "app/ramp.h"` — gated by RPM_RAMP

**Recommendation:** DON'T gate includes in Phase 12. The complexity of conditional includes with dependency chains (DR includes spectral_estimator.h already) creates fragile include-order bugs. The linker will dead-strip unused symbols anyway. Only gate the call sites.

## 11. Common Pitfalls

### Pitfall 1: Include-Order Dependency in `#error` Checks
**What goes wrong:** `#error` checks run before target_config.h is included, so they see default values, not target overrides.
**Why it happens:** `#include "target_config.h"` is near the top, but `#error` must be after all `#ifndef`-guarded defaults are set.
**How to avoid:** Place ALL `#ifndef` toggle defaults BEFORE `#error` checks. Use a clear section marker. The `#include "target_config.h"` at line 21 stays; defaults between lines 37-310; `#error` at the very end.
**Warning signs:** Build fails with `#error` saying PI requires DR, but DR is set to 1 in target_config.h.

### Pitfall 2: `#if` vs `#ifdef` Confusion
**What goes wrong:** Using `#ifdef BIBA_FEATURE_RPM_PI` when the toggle is always defined (as 0 or 1). `#ifdef` is true for both `#define BIBA_FEATURE_RPM_PI 0` and `#define BIBA_FEATURE_RPM_PI 1`.
**Why it happens:** Current codebase uses `#ifndef BIBA_OPEN_LOOP` (checking if NOT defined). Toggles use `=0`/`=1`, so must use `#if` not `#ifdef`.
**How to avoid:** ALWAYS use `#if BIBA_FEATURE_<NAME>` (value check), NEVER `#ifdef BIBA_FEATURE_<NAME>`.
**Existing counterexample to fix:** `#if BIBA_REVERSE_PIP_ENABLED` at line ~1080 already uses `#if` (value check) — correct pattern. The `#ifndef BIBA_OPEN_LOOP` blocks use `#ifndef` (definition check) which is correct for a flag that may or may not be defined.

### Pitfall 3: Orphaned State After Disable
**What goes wrong:** Disabling RPM ZC but leaving RPM SPECTRAL enabled → spectral gets stale `s_hint_hz` values, producing garbage RPM estimates.
**Why it happens:** The RPM chain is a pipeline; disabling an early stage breaks later stages.
**How to avoid:** Dependency `#error` checks catch most of these. For non-enforced dependencies (e.g., ZC → SPECTRAL), document that certain combinations are untested and may produce unexpected behavior. The master switch (`RPM_CLOSED_LOOP=0`) is the canonical "safe" way to disable the whole chain.

### Pitfall 4: Blackbox Record Field Gating
**What goes wrong:** `#if`-gating state variables used in blackbox record construction causes compile errors because `s_rpm_pi_left.integral` doesn't exist when RPM_PI=0.
**Why it happens:** Blackbox record (lines 1156-1200) reads multiple gated variables unconditionally.
**How to avoid:** Gate each field in the record write:
```c
#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_PI
    rec.pi_integral_l = (int16_t)(s_rpm_pi_left.integral * 10000.0f);
    rec.pi_integral_r = (int16_t)(s_rpm_pi_right.integral * 10000.0f);
#else
    rec.pi_integral_l = 0;
    rec.pi_integral_r = 0;
#endif
```

### Pitfall 5: DRIVE_DATA Telemetry References Gated Variables
**What goes wrong:** The debug telemetry printf (lines 1030-1070) references `s_spec_hz_*`, `s_spec_quality_*`, etc. — these are set to 0.0f in the ISR when features are off, but if the variable declarations are gated, they won't exist at all.
**Why it happens:** Variable gating for RAM savings conflicts with telemetry that reads them.
**How to avoid:** Either: (a) don't gate variable declarations (waste ~200 bytes RAM), or (b) gate the DRIVE_DATA printf line too. Option (b) is cleaner — if features are disabled, debug telemetry for those features should also be suppressed.

### Pitfall 6: `#if` Nesting Limit
**What goes wrong:** Deeply nested `#if`/`#else`/`#endif` blocks become unreadable.
**Why it happens:** The RPM chain in `on_adc_pair_done()` already has a 120-line `#ifndef BIBA_OPEN_LOOP` block. Adding 7 sub-toggles inside could create 3-4 levels of nesting.
**How to avoid:** Use flat sequential gates, not nested:
```c
/* GOOD: flat gates */
#if BIBA_FEATURE_RPM_ZC
    zc_left = zc_freq_analyze(...);
#else
    zc_left = (zc_detector_result_t){0};
#endif

#if BIBA_FEATURE_RPM_SPECTRAL
    spec_left = biba_rpm_spectral_estimate(...);
#else
    spec_left = (biba_rpm_spectral_result_t){0};
#endif
```
Not:
```c
/* BAD: nested gates */
#if BIBA_FEATURE_RPM_ZC
    ...
    #if BIBA_FEATURE_RPM_SPECTRAL
        ...
    #endif
#endif
```

## 12. Backward Compatibility — BIBA_OPEN_LOOP → BIBA_FEATURE_RPM_CLOSED_LOOP

### 12.1 Migration Path

1. **In `biba_config.h`**, add before the RPM Closed-Loop Master section:
```c
/* Backward compatibility: old BIBA_OPEN_LOOP maps to master switch */
#ifdef BIBA_OPEN_LOOP
#  warning "BIBA_OPEN_LOOP is deprecated — use BIBA_FEATURE_RPM_CLOSED_LOOP=0"
#  ifndef BIBA_FEATURE_RPM_CLOSED_LOOP
#    define BIBA_FEATURE_RPM_CLOSED_LOOP 0
#  endif
#endif
```

2. **Replace all `#ifndef BIBA_OPEN_LOOP`** → `#if BIBA_FEATURE_RPM_CLOSED_LOOP`
3. **Replace all `#ifdef BIBA_OPEN_LOOP`** → `#if !BIBA_FEATURE_RPM_CLOSED_LOOP`
4. **Remove the `#define BIBA_OPEN_LOOP`** line from `biba_config.h` (line 310)

### 12.2 Equivalence Verification

| Old Behavior (BIBA_OPEN_LOOP defined) | New Behavior (BIBA_FEATURE_RPM_CLOSED_LOOP=0) |
|---------------------------------------|-----------------------------------------------|
| ZC skipped | ZC skipped (outer `#if BIBA_FEATURE_RPM_CLOSED_LOOP` fails) |
| Spectral skipped | Spectral skipped |
| DR skipped | DR skipped |
| PI skipped | PI skipped |
| Anti-stall skipped | Anti-stall skipped |
| RPM ramp skipped | RPM ramp skipped (inner `&& BIBA_FEATURE_RPM_RAMP` also fails) |
| s_rpm_duty_* not updated | s_rpm_duty_* not updated |
| left_out/right_out from mixer direct | left_out/right_out from mixer direct |
| Blackbox rpm_hz = 0 | Blackbox rpm_hz = 0 |
| `(void)dt;` | `(void)dt;` |

**Identical behavior confirmed.** The migration preserves exact runtime semantics.

## 13. Risk Areas

### Risk 1: Silent Break When RPM Sub-Toggle Off But Master On
**Severity:** HIGH
**Scenario:** User sets `BIBA_FEATURE_RPM_ZC=0` but leaves `BIBA_FEATURE_RPM_SPECTRAL=1` and `BIBA_FEATURE_RPM_PI=1`. ZC is skipped → `raw_hz` stays 0.0f → spectral gets no hint from ZC → spectral may still work (uses target_hz as band center). But `raw_hz`=0 means telemetry shows 0 for ZC frequency.
**Mitigation:** Document that ZC is optional input; spectral operates independently. PI gets measurement from DR (which wraps spectral). No dependency `#error` for ZC → anything downstream.
**Actually runs?** Yes, the robot will drive fine — spectral and PI don't depend on ZC output at all (they use spec results). ZC telemetry will be zeroed.

### Risk 2: LATCH_RECOVERY Off With No Alternative
**Severity:** MEDIUM
**Scenario:** `BIBA_FEATURE_LATCH_RECOVERY=0` — BTS7960 thermal latch is never auto-cleared. Robot stops moving after a latch event until power cycle.
**Mitigation:** Document clearly. This is an intentional trade-off for users who want to disable the feature (e.g., for debugging). The hardware SSR interlock still protects.

### Risk 3: CURRENT_LIMITER Off → No Overcurrent Protection
**Severity:** HIGH
**Scenario:** `BIBA_FEATURE_CURRENT_LIMITER=0` → mixer output goes directly to motors without current/power clamping. BTS7960 can overheat and latch.
**Mitigation:** Document as "expert mode only." Consider adding `#warning "Current limiter disabled — BTS7960 overcurrent protection is OFF"` when this toggle is 0.

### Risk 4: Include-Order of Gated Headers
**Severity:** LOW
**Scenario:** If we gate `#include` directives (Section 10.4), a module `.c` file that transitively depends on a gated header may fail to compile.
**Why low severity:** We recommend NOT gating includes (Section 10.4). Let the linker dead-strip.

### Risk 5: RP2040 Native Test Build
**Severity:** MEDIUM
**Scenario:** The `BIBA_NATIVE_TEST` path in `biba_config.h` (lines 20-35) provides minimal defaults. Feature toggles must also be defaulted here for native tests to compile.
**Mitigation:** Add all 17 toggle defaults inside the `#ifdef BIBA_NATIVE_TEST` block, or better, keep toggles OUTSIDE the `BIBA_NATIVE_TEST` conditional so they're always defined.

### Risk 6: Target Override Order
**Severity:** LOW
**Scenario:** RP2040 `target_config.h` currently sets current/power limits to 0.0f (line 51-54 of target_config.h). These will move into the `BIBA_FEATURE_CURRENT_LIMITER` section. If target_config.h is included before toggle defaults, the `#ifndef` guard will see the target's value and skip the default — correct behavior. If included after, the default wins — incorrect.
**Mitigation:** Target_config.h MUST be included before toggle defaults. Current code already does this (line 21: `#include "target_config.h"` before any `#ifndef BIBA_*` defaults at line 37).

## 14. State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `BIBA_OPEN_LOOP` toggle | 17 individual `BIBA_FEATURE_*` toggles + master `RPM_CLOSED_LOOP` | Phase 12 | Fine-grained control; any feature can be independently disabled |
| Flat `#define` list in `biba_config.h` | Feature-scoped sections with toggle + params grouped | Phase 12 | Discoverability; all params for a feature are in one place |
| Module `.h` files hold their own defaults | `biba_config.h` is the single source of truth for all feature-config | Phase 12 | Single file to read for understanding all configurable behavior |
| `#if BIBA_REVERSE_PIP_ENABLED` (value check) | `#if BIBA_FEATURE_REVERSE_PIP` (same pattern) | Phase 12 | Consistent naming convention across all toggles |

## 15. Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | All 17 toggles default to 1 (except REVERSE_PIP=0 per D-07). No feature is disabled by default. | 1, 5 | LOW — this is a locked decision from CONTEXT.md |
| A2 | `biba_mix_differential()` produces identical behavior to the inlined L∞ ball when `speed_scale=1.0` and throttle/steer don't saturate. | 1.4, 3.3 | MEDIUM — `biba_mix_differential()` does `biba_clamp_unit(throttle ± steer)` which is hard-clip, not proportional projection. At low throttle+steer sums (no saturation), behavior is identical. At saturation, L∞ ball preserves steering ratio; differential mix clips asymmetrically. This is the intended difference per CONTEXT.md. |
| A3 | The `#ifndef` guard pattern in `biba_config.h` works correctly with `target_config.h` overrides — target_config.h uses direct `#define` (no `#ifndef` guard), so its values always win. | 1, 5 | LOW — verified by reading both files |
| A4 | Parameter constants moved from module `.h` files to `biba_config.h` will not break module compilation because `biba_config.h` is included first. | 6 | LOW — verified by reading include order in mode_standalone.c line 14 |
| A5 | No other `.c` files besides `mode_standalone.c` call the gated functions. | 3 | MEDIUM — `motor_bridge.c` exists but is excluded from RP2040 build via `build_src_filter`. The `blackbox.cpp` references `s_rpm_pi_left.integral` indirectly through the record struct, not through function calls. This is handled in Pitfall 4. |

## 16. Open Questions

1. **Should ZC detector parameters (ZC_SUBWIN_K, ZC_SUBWIN_MIN_PKPK, etc.) move to biba_config.h?**
   - What we know: They are currently in `zc_detector.h` as `#define`s. They are user-tunable per calibration data.
   - What's unclear: Whether the user wants these to be toggle-scoped or remain in the module header.
   - Recommendation: Move them to the `BIBA_FEATURE_RPM_ZC` section per D-04 (all params for a feature grouped). The module `.h` keeps backward-compat `#ifndef` guards.

2. **Should heading-hold PID gains (s_heading_cfg) move to biba_config.h?**
   - What we know: Currently hardcoded in `mode_standalone.c` lines 85-88 as a static const struct.
   - What's unclear: Whether the user wants to make these configurable.
   - Recommendation: Move to `BIBA_FEATURE_HEADING_HOLD` section as `BIBA_HEADING_KP`, `BIBA_HEADING_KI`, `BIBA_HEADING_KD`, `BIBA_HEADING_OUTPUT_LIMIT`, `BIBA_HEADING_INTEGRAL_LIMIT`. Simple migration, no risk.

3. **Should state variables be `#if`-gated for RAM savings?**
   - What we know: ~219 bytes potential savings (Section 4).
   - What's unclear: Whether RP2040 RAM pressure warrants the added complexity.
   - Recommendation: Gate only the largest consumers (RPM_PI ~76 bytes, HEADING_HOLD ~44 bytes) in Wave 1. Leave smaller variables ungated for simplicity. Add full gating in Wave 2 if needed.

## 17. Environment Availability

Step 2.6: SKIPPED (no external dependencies identified). This phase is pure C preprocessor + code reorganization. The tools needed (arm-none-eabi-gcc via PlatformIO) are already confirmed working from Phase 11.

## 18. Security Domain

`security_enforcement` not explicitly false in config.json, so include per default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | CRSF frame validation already exists; not affected by toggles |
| V6 Cryptography | no | — |

### Known Threat Patterns for C Preprocessor Feature Gating

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Misconfiguration (feature off that should be on for safety) | Tampering | `#error` for hard dependencies; `#warning` for soft recommendations; documentation |
| Undefined behavior from stale variables after disable | Denial of Service | Explicit zero-initialization in `#else` branches |

## 19. Sources

### Primary (HIGH confidence)
- `firmware/src/modes/mode_standalone.c` (1277 lines) — Full CRSF→motor signal chain, all integration points [VERIFIED: codebase grep]
- `firmware/include/biba_config.h` (310 lines) — Current flat #define list [VERIFIED: codebase grep]
- `firmware/targets/RPICO_RP2040/target_config.h` (55 lines) — Target overrides [VERIFIED: codebase grep]
- `firmware/src/app/*.h` — All 17 feature module headers [VERIFIED: codebase grep]
- `.planning/phases/12-feature-gating/12-CONTEXT.md` — All 7 locked decisions [CITED: CONTEXT.md]
- `.planning/phases/12-feature-gating/12-DISCUSSION-LOG.md` — Decision rationale [CITED: DISCUSSION-LOG.md]

### Secondary (MEDIUM confidence)
- `firmware/platformio.ini` — Build configuration, native_test env [VERIFIED: codebase grep]
- `.planning/config.json` — nyquist_validation=false confirmed [VERIFIED: codebase grep]

### Tertiary (LOW confidence)
- None. All claims verified against the codebase.

## 20. Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools (C preprocessor, PlatformIO) already in use
- Architecture: HIGH — all integration points mapped with exact line numbers
- Pitfalls: HIGH — identified from existing code patterns and preprocessor gotchas

**Research date:** 2026-05-27
**Valid until:** 2026-06-27 (stable phase — no external dependency churn)

**Lines of code audited:** ~1,950 (mode_standalone.c 1277 + biba_config.h 310 + target_config.h 55 + all 14 app/driver headers ~310)
