---
doc: RESEARCH-SUMMARY
last_mapped: 2026-05-14
---

# Research Summary: BiBa RP2040 Port

## Key Findings

### Stack

1. **Stay on earlephilhower arduino-pico, local platform pin, pico-sdk drivers** — The `vccgnd_yd_rp2040` board already implies the earlephilhower core; do not switch to the PlatformIO default `platform = raspberrypi` (pulls mbed). Keep the local platform pin for reproducibility. Use pico-sdk `hardware/pwm.h`, `hardware/i2c.h`, `hardware/uart.h` directly from C translation units — Arduino Wire wrappers are not compatible with the existing C drivers.

2. **No third-party IMU or CRSF libraries** — `firmware/src/drivers/crsf.c` and `imu.c` already implement the required functionality with direct pico-sdk register access. Both BMI160 and LSM6DS3 auto-detection (`biba_imu_probe()`) are in place. Third-party Arduino libraries (hanyazou/BMI160-Arduino, SparkFun LSM6DS3) are stale, Wire-dependent, and would require C↔C++ ABI bridging — not worth it.

3. **PWM: 20 kHz carrier via hardware slices, not `analogWrite`** — Left motor GP2/GP3 → slice 1, right motor GP6/GP7 → slice 3. Wrap = `sys_clk / 20000` (6250 at 125 MHz). `analogWrite` shares frequency across the whole slice; pico-sdk `pwm_set_chan_level` gives independent A/B channel control needed for BTS7960 direction logic. Add `-Wdouble-promotion` to catch soft-float double literals in the hot path.

---

### Table Stakes Features

Must have all of these before the RP2040 port is field-usable:

| Feature | Impl Note |
|---------|-----------|
| CRSF packet decoding (UART0, 420 kbaud) | Use existing `crsf.c`; replace `memmove` ring buffer with head/tail indices |
| RC channels → throttle/steering mapping (11-bit, int32 intermediates) | Port Python `_decode_channels` tests to C unit tests |
| Differential drive mixing + output clamping | Direct port of `motors/driver.py DifferentialDrive` |
| BTS7960 RPWM/LPWM/REN/LEN PWM output | HAL must drive EN LOW as first GPIO op on boot |
| Arm/disarm state machine (CH5 switch) | Disarmed = zero duty + EN LOW |
| Failsafe on CRSF link loss ≤500 ms | Tick from hardware timer ISR, not main loop (I2C blocking hazard) |
| Input deadband (±5% throttle + steering) | Direct port from Python config |
| Output slew-rate limiting (~100 ms 0→100%) | Port `motors/ramping.py ScalarKalmanFilter` |
| Buzzer audible feedback (armed/disarmed/failsafe/low-bat) | PWM tone; melody is a differentiator |

---

### Architecture

1. **HAL shim pattern — extend, don't ifdef** — Each new RP2040 peripheral capability gets a new file: `biba_hal_imu_rp2040.c`, `biba_hal_spi_rp2040.c`, etc. PlatformIO `build_src_filter` selects the right file per env. Never add `#ifdef RPICO` inside shared `src/` files.

2. **Mode × Target matrix in `platformio.ini`** — `env:rpico_rp2040_standalone`, `env:rpico_rp2040_companion` naming convention is the contract. Modes (standalone/companion) are orthogonal to targets; any target can run any mode if hardware permits. Add a base `[env_rp2040]` stanza with `platform = file://...`, `framework = arduino`, `board = vccgnd_yd_rp2040` inherited by all RP2040 envs.

3. **Runtime calibration via LittleFS** — For RP2040-PORT-04/05, add a `calibration.c/h` module that reads/writes PID gains + trim values + current-sense offsets to LittleFS on onboard flash. Default to `target_config.h` defines when no persisted data exists. Manual mirror + drift test remains the correct pattern for `biba_proto`; only upgrade to nanopb if payload count exceeds ~6 command types.

4. **Failsafe must be hub-safe** — Spoke (RP2040) must stop motors safely if the hub (Pi) dies. All safety-critical ticks (failsafe, motor disable) must run independent of the main application loop — use RP2040 hardware alarm timers or core1 for CRSF/failsafe, core0 for slow I2C/ADC work.

---

### Watch Out For

1. **Motor pins float during boot** — BTS7960 EN pins are active-high; RP2040 GPIO is high-Z at power-on and during reflash. Without explicit `EN = LOW` as the first HAL operation, motors can spin on boot. Add 4.7 kΩ hardware pull-downs on REN/LEN as a second line of defence. This is the single highest-priority hardware safety issue.

2. **Failsafe ticked from I2C-blocked main loop fires late** — This exact bug existed in the Python reference (documented in CONCERNS.md). The RP2040 port reproduces it if `biba_failsafe_tick()` runs in the same loop as blocking I2C calls (BMI160 burst read + ADS1115 conversion = up to 1 ms). Mitigation: hardware alarm ISR or core1 for CRSF/failsafe.

3. **BTS7960 thermal shutdown without software throttle** — Field failure confirmed May 2026: driver overheated at 20–30 min driving. `THERMAL-02` (rolling current average + linear duty reduction + hard disable + buzzer alarm) is a required safety feature, not optional polish. Without it, the hardware damage mode will recur in longer sessions or hot weather.

---

## Phase Implications

Research strongly suggests a dependency-ordered sequence that matches the existing `RPICO_RP2040` target work:

| Suggested Phase | Rationale | Key Pitfalls to Avoid |
|----------------|-----------|----------------------|
| **PORT-01: CRSF UART** | Gate for everything else; no control without receiver data. Replace `memmove` ring buffer, port channel bit-unpack unit tests. | `volatile` on ISR-shared variables; int32 intermediates for channel scaling; UART init *after* final `set_sys_clock_khz()` |
| **PORT-02: BTS7960 PWM** | Physical output; required before any drive test. EN LOW first, PWM duty zero before enable. | Boot pin float (critical); inrush on enable; pico-sdk slice control not `analogWrite` |
| **PORT-03: IMU + heading-hold** | Differentiator, but depends on motor output being correct first. Gyro bias cal on arm, real `dt` from `time_us_32()`, axis sign from Python reference. | Variable-dt integration drift; missing zero-offset cal; axis mapping mismatch; BMI160 vs LSM6DS3 ODR defaults differ |
| **PORT-04: ADC current sense + VBAT** | Safety features (thermal throttle, low-battery alarm). Recalculate divider for 3.3V ADC; oversample 4–16 samples; saturation flag when ADC > 90% full scale. | IS pin saturation reporting false low; supply noise ±1–2 A spikes; voltage divider designed for ADS1115 4.096V ref |
| **PORT-05: Trim persistence** | Quality of life; store trim to LittleFS. int32 intermediates for trim arithmetic. | Calibration constants silently truncated if stored as int |
| **PORT-06: Failsafe + arming** | Safety hardening; must come after CRSF works. Hardware alarm ISR for tick; init order (structs → HAL → enable ISR). | ISR enabled before `failsafe_init`; I2C blocking main loop; uint32_t rollover (use `_Static_assert`); LQ < RSSI for pre-failsafe alarm |
| **THERMAL-02: Software throttle** | Required to prevent hardware damage recurrence. Rolling current average + duty reduction + hard disable. | IS saturation masking real overcurrent; bench tests missing PWM noise (characterize in field) |
| **Companion mode SPI slave** | Deferred; standalone must be complete and field-validated first. | Mode × target matrix must be clean before adding companion stanza |

**Phases that need `/gsd-research-phase`:** PORT-04 (RP2040 ADC noise characterization is hardware-specific), THERMAL-02 (BTS7960 saturation behaviour on this specific variant).

**Phases with well-documented patterns (skip research):** PORT-01 (CRSF parser exists, just port), PORT-02 (HAL exists for STM32, direct translate), PORT-06 (failsafe state machine exists in Python + firmware).

---

## Open Questions

1. **BTS7960 IS pin saturation current** — The specific BTS7960 variant on the target PCB determines the ADC clip point for current sense. Needs hardware measurement: full-stall test with known current meter to establish the saturation voltage and effective `amps_per_volt` floor.

2. **RP2040 ADC noise floor with motor PWM active** — Bench ADC readings will differ from field readings once 20 kHz PWM switching is coupled into the 3.3V rail. Run the noise characterization test (1 kHz ADC sampling at full duty cycle) before setting software filter coefficients for current sense and VBAT.

3. **PID gains require re-tuning on RP2040** — Pi Python gains were tuned against a ~50 Hz asyncio loop with scheduling jitter. RP2040 deterministic loop rate will likely need different Kp/Kd. Plan an explicit PID re-tuning session for PORT-03 field validation; do not declare heading-hold complete until gains are validated on the actual hardware.

4. **LittleFS wear-out budget** — If trim values are written on every arm cycle, and the robot is armed/disarmed hundreds of times, LittleFS wear levelling must be confirmed adequate. Measure write frequency vs. RP2040 flash endurance (~100K cycles); consider write-coalescing (write only on explicit "save" command) if arm-cycle write rate is high.

5. **Companion mode SPI frame rate vs. ROS2 topic rate** — Out of scope for Phase 1 standalone, but the `biba_proto` 64-byte fixed frame needs capacity planning before companion mode is designed. Current protocol handles motor commands + telemetry; adding IMU streaming to the Pi may require a protocol version bump.
