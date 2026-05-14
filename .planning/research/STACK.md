---
doc: STACK-RESEARCH
last_mapped: 2026-05-14
---

# Stack Research: RP2040 Robot Firmware

## RP2040 / PlatformIO Setup

**Board:** `vccgnd_yd_rp2040` (YD-RP2040, USB-C variant, Pico-compatible pinout).
This is an earlephilhower-only board — `board_build.core = earlephilhower` is NOT
required (the board definition already implies it).

**Platform:** Currently pinned to `file:///home/ros2/.platformio/platforms/rp2040` — a
local install of `maxgerhardt/platform-raspberrypi`. This is correct for a brownfield
project; it ensures reproducibility without relying on registry version drift.
**Do not switch to `platform = raspberrypi` (PlatformIO default) — that pulls the
mbed core**, not earlephilhower.

**Framework:** `arduino` (earlephilhower/arduino-pico). This gives access to both the
Arduino-Pico C++ API (Wire, Serial, analogWrite, etc.) and all raw pico-sdk headers
(`hardware/uart.h`, `hardware/pwm.h`, `hardware/i2c.h`, `hardware/adc.h`) from C
translation units.

**Upload / debug:** `upload_protocol = picotool` (USB boot mode) and
`debug_tool = cmsis-dap` (PicoProbe / any CMSIS-DAP adapter). Both are confirmed
working in the existing project. Note: newer PicoProbe firmware emulates CMSIS-DAP
rather than the legacy proprietary protocol — `cmsis-dap` is the correct selector.

**CPU speed:** Not explicitly set in current envs. The pico-sdk default is 125 MHz;
earlephilhower arduino-pico defaults to 125 MHz. Add `board_build.f_cpu = 133000000L`
to rpico envs if the extra headroom matters for IMU math — tested stable on most YD
boards at 133 MHz.

---

## CRSF/ELRS Decoding on RP2040

**Recommendation: Use the existing `firmware/src/drivers/crsf.c` — no external library
needed.**

The project already has a complete, pure-C biba CRSF parser (`biba_crsf_pop_frame`,
`biba_crsf_parse_frame`, DVB-S2 CRC8). It is cross-validated against the Python
reference implementation (`biba-controller/crsf/`) and covered by the test suite
(`tests/test_crsf.py`). Replacing it with a third-party library would break parity and
require retesting.

**Third-party libraries surveyed (for reference only):**
- **CrsfSerial (CapnBry/CRServoF):** Arduino C++ CRSF library, has RP2040/Pico support
  scaffolding in `include/`. Actively maintained (VBAT telemetry added Jan 2026).
  GPL-3.0. Good for a greenfield project; for BiBa it would duplicate biba_crsf.
- **crsf-wg/crsf:** Official CRSFWG specification wiki only — no C library, just docs.
  Useful as protocol reference.

**UART configuration for RP2040 HAL:**
- UART0, GP0 (TX) / GP1 (RX), 420000 bps — matches Pi Zero 2W reference.
- In the RP2040 HAL, use `uart_init(uart0, 420000)` + `gpio_set_function(0/1, GPIO_FUNC_UART)`.
- No flow control. The receiver drives TX continuously at ~50 Hz; the RP2040 RX FIFO
  has 32 bytes depth — service it at ≥2 kHz (main loop or UART IRQ) to avoid overrun.
- Back-channel telemetry (battery frame, link stats) uses the same UART TX; the CRSF
  protocol is half-duplex with fixed inter-frame timing.

**Failsafe:** The `biba_crsf_pop_frame` API returns 0 (no frame) when the UART is
silent. The mode dispatcher should track `last_frame_timestamp` and trigger failsafe
after `FAILSAFE_TIMEOUT_S = 0.5` s, matching the Pi Zero 2W behaviour.

---

## IMU Drivers (BMI160 / LSM6DS3) on RP2040

**Recommendation: Keep the existing `firmware/src/drivers/imu.c` with direct pico-sdk
`hardware/i2c.h` register accesses — no Arduino Wire, no third-party library.**

**Why not Arduino Wire-based libraries:**
- `hanyazou/BMI160-Arduino` (104 stars): Derived from Intel Arduino 101 CurieIMU,
  9 years since last commit. No RP2040/arduino-pico compatibility test. Uses `Wire`
  which is not available from C translation units.
- `SparkFun_LSM6DS3_Arduino_Library` (65 stars): Tested on UNO/ESP32/ESP8266/Teensy,
  not on RP2040. 5 years since last commit. Same Wire dependency issue.
- Both would require wrapping to bridge C ↔ C++ ABI and Wire ↔ pico-sdk I2C. The
  complexity exceeds any benefit.

**I2C configuration:**
- I2C0, GP20 (SDA) / GP21 (SCL), 400 kHz (Fast mode). Both chips support 400 kHz.
- `i2c_init(i2c0, 400000)` + `gpio_set_function(20/21, GPIO_FUNC_I2C)` + pull-ups.
- Address 0x68 for both BMI160 and LSM6DS3 (SDO/SA0 pin to GND).
- Auto-detection already implemented in `biba_imu_probe()`: read LSM6DS3 WHO_AM_I
  at 0x0F, then BMI160 CHIP_ID at 0x00 (expected 0xD1).

**DMP usage: Skip entirely.**
- BMI160 DMP (Bosch firmware blob) is poorly documented, adds ~3 KB binary dependency,
  and provides step counter / gesture features not needed by BiBa.
- LSM6DS3 embedded functions (tilt, free-fall, pedometer) similarly irrelevant.
- BiBa needs gyro Z (yaw rate) and accel XY at 100 Hz for heading-hold PID.
  Software integration (`heading += gyro_z_dps * dt`) is the correct approach.

**Sample rate:** Both chips can produce 100 Hz ODR without DRDY interrupts; polling
from the main loop at the desired rate is sufficient. GP22 (IMU INT1) is wired but
optional — use only if the main loop timing becomes irregular.

**LSM6DS3 register cheat sheet for BiBa:**
- `0x10` = CTRL1_XL: accel ODR + FS. `0x11` = CTRL2_G: gyro ODR + FS.
- `0x22-0x27` = OUTX_L/H_G (gyro). `0x28-0x2D` = OUTX_L/H_XL (accel).
- FS_G = ±250 dps → 8.75 mdps/LSB. FS_XL = ±2g → 0.061 mg/LSB.

**BMI160 register cheat sheet for BiBa:**
- `0x40` = ACC_CONF. `0x42` = GYR_CONF. `0x7E` = CMD (softReset = 0xB6).
- `0x0C-0x17` = GYR_X/Y/Z + ACC_X/Y/Z raw (little-endian int16).
- Gyro range reg `0x43`: range bits 0x00 = ±2000 dps, 0x01 = ±1000, etc.

---

## Motor PWM on RP2040

**Use pico-sdk `hardware/pwm.h` directly — not `analogWrite`.**

`analogWrite` in arduino-pico works but uses a global frequency that applies to all
channels on the same slice. For BTS7960 we need precise slice-level control.

**Slice assignment (from `target.h`):**
- Left motor: GP2 (L_RPWM) + GP3 (L_LPWM) → PWM slice 1, channels A/B.
- Right motor: GP6 (R_RPWM) + GP7 (R_LPWM) → PWM slice 3, channels A/B.
- `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM = 0`: both channels in a slice share the
  same wrap register, so carrier frequency is identical for A and B.

**Target frequency: 20 kHz** — matches Pi Zero 2W reference (`PWM_FREQUENCY_HZ=20000`).
At 125 MHz: `wrap = 125_000_000 / 20_000 = 6250`, giving 13-bit duty resolution (6250
levels). At 133 MHz: `wrap = 6650` (also 13-bit). Both are fine.

```c
// Initialization (once, in biba_hal_motor_init)
uint slice_l = pwm_gpio_to_slice_num(BIBA_PIN_LEFT_RPWM_GPIO);   // slice 1
uint slice_r = pwm_gpio_to_slice_num(BIBA_PIN_RIGHT_RPWM_GPIO);  // slice 3
pwm_set_wrap(slice_l, BIBA_PWM_WRAP);  // = sys_clk / PWM_FREQ - 1
pwm_set_wrap(slice_r, BIBA_PWM_WRAP);
pwm_set_enabled(slice_l, true);
pwm_set_enabled(slice_r, true);
```

**BTS7960 DIR+PWM pattern:**
- Forward: RPWM = duty, LPWM = 0 (channel A carries duty, channel B = 0).
- Reverse: RPWM = 0, LPWM = duty (channel B carries duty, channel A = 0).
- Braking: both RPWM and LPWM = 0 (both channels = 0; enables braking through the H-bridge).
- REN and LEN must be HIGH (GPIO OUT) to enable the driver before any PWM.
- REN/LEN to LOW = coast (disabled); use for failsafe / disarmed state.

```c
// biba_bts7960_drive(float duty)  — positive = fwd, negative = rev
if (duty >= 0) {
    pwm_set_chan_level(slice, PWM_CHAN_A, (uint16_t)(duty * BIBA_PWM_WRAP));
    pwm_set_chan_level(slice, PWM_CHAN_B, 0);
} else {
    pwm_set_chan_level(slice, PWM_CHAN_A, 0);
    pwm_set_chan_level(slice, PWM_CHAN_B, (uint16_t)(-duty * BIBA_PWM_WRAP));
}
```

**Thermal note:** BTS7960 without heatsink was the field failure mode (May 2026 tests).
PWM frequency does not directly affect BTS7960 die temperature, but keeping it at
20 kHz (inaudible, moderate switching losses) is correct. The thermal fix is
mechanical (heatsink mount), not firmware.

---

## Current Sensing on RP2040

**Internal ADC path (GP27=ADC1, GP28=ADC2) is viable for phase 1; understand limits.**

**RP2040 ADC specs:**
- 12-bit SAR ADC, 500 kSPS max, 3.3V reference (AVDD pin).
- Returns 0–4095 via `analogRead()` or `adc_read()`.
- Resolution: 3.3V / 4096 = 0.806 mV/LSB.
- Known noise: ≈2–3 LSB RMS in normal conditions; can increase to 5–10 LSB when PWM
  switching noise couples into AGND or AVDD. The RP2040 datasheet acknowledges ~±1 LSB
  integral nonlinearity.

**BTS7960 IS pin characteristics:**
- IS pin outputs `I_motor / 8500` (current mirror ratio). At 20A motor load: IS ≈ 2.35 mA.
- IS pin requires a sense resistor to GND to produce a voltage. With 330 Ω (typical):
  V_IS = 2.35 mA × 330 Ω ≈ 0.78 V at 20A. This fits within the 3.3V ADC range well.
- Calibration struct `biba_current_calibration_t {zero_offset_v, amps_per_volt}` is
  the correct model. Zero offset must be calibrated with motor stopped (IS leakage
  current produces a small non-zero voltage).

**Oversampling for noise reduction:**
```c
// 16x oversample via hardware (pico-sdk adc_set_round_robin off, burst in loop)
uint32_t sum = 0;
for (int i = 0; i < 16; i++) {
    adc_select_input(1);   // ADC1 = GP27 = L_IS
    sum += adc_read();
}
float v = (sum / 16.0f) * (3.3f / 4095.0f);
```
Alternatively, use `ADCInput` with DMA averaging (arduino-pico `ADCInput` API) —
`ADCInput adc(A1, A2)` captures both IS channels in round-robin with DMA, then
average in software.

**ADC vs ADS1115 comparison:**
| | RP2040 internal ADC | ADS1115 I2C |
|---|---|---|
| Resolution | 12-bit (0.806 mV/LSB) | 16-bit (0.125 mV/LSB @ ±4.096V) |
| Noise | ~2-5 LSB in motor environment | ~1 LSB (delta-sigma) |
| Channels | 3 free (ADC0=VBAT, ADC1=L_IS, ADC2=R_IS) | 4 (as on Pi Zero 2W) |
| Latency | <50 µs | ~1 ms (I2C poll) |
| Cost | Free (on-chip) | External component |

**Recommendation:** Internal ADC with 16x oversampling is sufficient for overcurrent
protection and thermal management (±5% accuracy acceptable). ADS1115 is deferred
(matches Pi Zero 2W reference parity but adds BOM complexity). If precision matters
later, the I2C0 bus (GP20/GP21) already has IMU; ADS1115 at `0x48` can share it.

**Critical hardware note:** Add 100 nF ceramic decoupling between AVDD (pin 33) and
AGND (pin 31) as close to the RP2040 as possible. PWM-induced switching noise on the
PCB power planes is the #1 cause of ADC inaccuracy on motor controller boards.
Do not run ADC sampling synchronously with PWM edge transitions — sample mid-period.

---

## Multi-Target PlatformIO

**The existing `[target_xxx]` + `[env:target_mode]` pattern is correct and
well-established. Key conventions to follow:**

**Pattern (already in use):**
```ini
[target_rpico_rp2040]
board = vccgnd_yd_rp2040
target_include = targets/RPICO_RP2040
build_flags = -DBIBA_TARGET_RPICO_RP2040=1

[rp2040_src_filter]
build_src_filter =
    +<*>
    -<hal/biba_hal.c>
    -<hal/biba_hal_motor.c>
    -<hal/biba_hal_debug.c>
    -<main.c>

[env:rpico_rp2040_standalone]
platform = file:///home/ros2/.platformio/platforms/rp2040
framework = arduino
board = ${target_rpico_rp2040.board}
upload_protocol = picotool
debug_tool = cmsis-dap
build_src_filter = ${rp2040_src_filter.build_src_filter}
build_flags =
    -Iinclude
    -Isrc
    -Isrc/proto
    -I${target_rpico_rp2040.target_include}
    ${target_rpico_rp2040.build_flags}
    ${mode_standalone.build_flags}
```

**`target.h` / `target.md` pattern** (already in `targets/RPICO_RP2040/`):
- `target.h` defines pin macros, capability flags (`BIBA_TARGET_HAS_*`), and includes
  pico-sdk headers guarded by `#if !defined(BIBA_NATIVE_TEST)`.
- `target.md` is the human-readable wiring diagram (Markdown with ASCII art).
- `target_config.h` holds tunable defaults (wrap value, baud rate, etc.) specific to
  this board — keep board-variant values here, not in shared `include/`.

**`build_flags` inheritance caveat:** PlatformIO `extends` stacks INI sections but does
NOT auto-merge `build_flags` arrays. Each env must explicitly concatenate with
`${parent.build_flags}`. The existing pattern does this correctly — do not use
`[common]` for RP2040 flags that conflict with STM32 defaults.

**STM32 vs RP2040 file exclusion:** `build_src_filter` in `[rp2040_src_filter]` is the
right mechanism. The HAL abstraction (`biba_hal.h`) allows shared mode code
(`mode_standalone.c`, `mode_companion.c`) to compile for both targets; only the HAL
implementation files (`biba_hal_rp2040.c` vs `biba_hal_stm32.c`) are target-specific.

**Adding new RP2040 HAL files:** Add them to `firmware/src/hal/` and list them in
`rp2040_src_filter` with `+<hal/biba_hal_rp2040_motor.c>` etc. Do not add to the
`[common]` build_src_filter — it will break STM32 builds.

**Local platform path:** `/home/ros2/.platformio/platforms/rp2040` is a local path tied
to this machine. In CI (GitHub Actions `G-Build-STM32F103.yml`), it likely uses the
registry. Verify the CI workflow handles the RP2040 env; the current workflow filename
implies STM32-only. A `G-Build-RP2040.yml` workflow may be needed.

**`board_build.filesystem_size = 0m`:** Add to all rpico envs. No filesystem needed;
this reclaims flash space for code and avoids LittleFS initialization overhead.

---

## Recommendations

1. **Do not replace the CRSF parser with a third-party library.** `biba_crsf_pop_frame`
   is already proven, cross-validated with Python, and battle-tested in the STM32
   builds. Wire UART0 at 420000 bps in the RP2040 HAL and use the existing API.

2. **Use pico-sdk hardware/pwm.h directly for BTS7960, not `analogWrite`.** Set wrap
   explicitly for 20 kHz (matching Pi reference), use `pwm_set_chan_level` for
   direction via A/B channel toggling. Ensure REN/LEN GPIO pins are asserted HIGH
   before enabling PWM.

3. **Keep IMU as direct I2C register reads via `hardware/i2c.h`.** The existing
   `biba_imu.c` abstraction with `biba_imu_probe` + auto-detect is the correct
   approach. Skip DMP for both chips — raw 100 Hz gyro + software heading integration
   is sufficient and transparent.

4. **Use RP2040 internal ADC with 16x oversampling for current sensing.** Calibrate
   zero offset at startup (motors disarmed). Add 100 nF AVDD decoupling on board.
   Sample mid-PWM-period to avoid switching noise. This is adequate for phase 1
   overcurrent protection; ADS1115 I2C can be added later if precision is needed.

5. **Add `board_build.filesystem_size = 0m` and consider `board_build.f_cpu = 133000000L`
   to all rpico envs.** Add a dedicated `G-Build-RP2040.yml` CI workflow if the RP2040
   build is not currently covered by CI.

---

## Confidence & Caveats

| Area | Confidence | Notes |
|---|---|---|
| PlatformIO / arduino-pico config | HIGH | Verified against official arduino-pico docs (readthedocs.io). Local platform path confirmed in `platformio.ini`. |
| CRSF decoder — keep existing | HIGH | Code confirmed in `firmware/src/drivers/crsf.c`. Cross-validation with Python proven by test suite. |
| pico-sdk PWM for BTS7960 | HIGH | `hardware/pwm.h` API confirmed. Slice/channel assignments from `target.h`. |
| IMU — direct I2C register access | HIGH | Approach confirmed in `biba_imu.h` API. Chip register addresses from datasheets (training knowledge); verify against chip datasheet before implementation. |
| RP2040 ADC noise characteristics | MEDIUM | Known issue from community + datasheet; ±2–5 LSB noise figure is empirical, will vary with board layout and switching noise coupling. Must be measured on actual hardware. |
| ADS1115 via I2C0 (deferred) | MEDIUM | Address 0x48 confirmed for Pi Zero 2W reference. I2C bus sharing with IMU (0x68) is standard; verify no address conflict with other I2C devices on RP2040 board. |
| hanyazou/BMI160-Arduino RP2040 compat | LOW | Not explicitly tested on arduino-pico; avoid per recommendation above. |
| CI workflow for RP2040 | LOW | Current `G-Build-STM32F103.yml` filename suggests RP2040 may not be covered. Verify `.github/workflows/` before shipping. |

**Things to verify on hardware:**
- Actual IS sense resistor value on the BTS7960 boards in use (may differ from the 330 Ω assumption).
- Whether `vccgnd_yd_rp2040` board definition uses 125 MHz or 133 MHz as default — run `F_CPU` check in firmware init.
- UART0 at 420000 bps: confirm the YD-RP2040 USB-UART bridge does not intercept GP0/GP1 (some YD variants multiplex the USB-UART on GP0/GP1). Use USB CDC (`Serial`) for debug output instead of `Serial1`.
