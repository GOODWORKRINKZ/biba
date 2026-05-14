---
doc: FEATURES-RESEARCH
last_mapped: 2026-05-14
---

# Features Research: RC Robot Controller

**Domain:** Embedded RC wheeled-robot controller (ELRS/CRSF, RP2040 target)
**Scope:** RP2040 port of existing Python BiBa controller — Phase 1 (standalone embedded)
**Source confidence:** HIGH for table-stakes (derived directly from working Python implementation + field tests);
MEDIUM for differentiators nuance (cross-referenced against community RC/Betaflight patterns);
LOW flagged where relevant.

---

## Table Stakes (Must Have)

Every RC robot controller that drives a differential platform via ELRS must have these.
Missing any one = the robot is not minimally usable in the field.

| Feature | Why Mandatory | Current Status | Notes |
|---------|--------------|----------------|-------|
| **CRSF packet decoding** | All ELRS receivers output CRSF frames at 420 kbaud; without a decoder there is no control | ✓ Python + STM32 firmware (`drivers/crsf.c`) | 8-byte sync + type + length + payload + CRC8 over UART |
| **RC channels → steering/throttle mapping** | Raw CRSF channel values (172–1811 μs nominal) must map to [-1.0, +1.0] drive commands | ✓ Python `crsf/receiver.py` | Typically CH1=throttle, CH3=steering (mode 2); must be configurable |
| **Differential drive mixing** | Two independent H-bridges require throttle+steering to be mixed into left/right duty cycles | ✓ Python `motors/driver.py DifferentialDrive` | Mix: left = throttle + steering, right = throttle − steering, then clamp |
| **BTS7960 H-bridge PWM output** | The physical driver ICs need RPWM/LPWM/REN/LEN signals at correct frequency | ✓ Python pigpio + firmware `drivers/bts7960.c` + `hal/biba_hal_motor_rp2040.c` | RP2040: hardware PWM slices; recommended carrier 20–25 kHz (above audible, below BTS7960 heating zone) |
| **Arm/disarm state machine** | Robot must be safe at rest; motors must not spin until operator explicitly arms | ✓ Python `main.py` arm/disarm logic | Disarmed = zero output; typically bound to a two-position switch on CRSF CH5 |
| **Failsafe on CRSF link loss** | Link drop must immediately stop motors and hold brakes, not drift | ✓ Python + firmware `app/failsafe.c` | CRSF has built-in failsafe frame type; also watchdog timer if no packets for >250 ms |
| **Input deadband** | Joystick noise near center must not cause slow motor creep | ✓ Python `AssistedDriveConfig.throttle_deadband=0.05` | ±5% deadband on throttle and steering independently |
| **Output ramping / slew-rate limiting** | Hard step changes damage motors and cause wheel spin; ramps improve traction | ✓ Python `motors/ramping.py ScalarKalmanFilter` | Separate accel/decel ramps; target: ~100 ms 0→100% accel |
| **Motor enable/disable logic** | BTS7960 REN/LEN must be asserted before PWM; must be deasserted on disarm/failsafe | ✓ firmware `drivers/bts7960.c` | Low on both = coast; low RPWM+high RPWM+LEN = forward; reverse = invert |
| **Buzzer / beeper feedback** | Audible status indication (armed, disarmed, failsafe, low battery) is field-critical; without it operator has no feedback when headset is off | ✓ Python `buzzer/` | On RP2040: PWM tone output sufficient; melody engine is a differentiator |

### CRSF Implementation Notes (RP2040-specific)

- **UART0 at GP0/GP1**, 420000 baud (not standard UART speed — requires exact integer divisor via RP2040 UART fractional baud gen)
- CRSF frames: sync byte `0xC8`, max 64 bytes, CRC8/DVB-S2
- ELRS sends RC channels as `CRSF_FRAMETYPE_RC_CHANNELS_PACKED` (22 bytes, 11 bits per channel × 16 ch)
- Link statistics frame (`CRSF_FRAMETYPE_LINK_STATISTICS`) provides RSSI, SNR, LQ — table stakes for operator visibility
- Failsafe frame (`CRSF_FRAMETYPE_FAILSAFE`) explicitly signals link loss; supplement with inter-packet timeout watchdog

---

## Differentiators (Competitive Advantage)

Features that elevate BiBa above a basic RC drive platform. Not every RC robot has these.

| Feature | Value | Complexity | Current Status |
|---------|-------|------------|----------------|
| **IMU gyro stabilization (heading-hold)** | Prevents the robot from spinning/drifting on uneven terrain; operator commands a _yaw rate_, not raw motor mix | HIGH — makes outdoor driving feel planted | ✓ Python `motors/assisted_drive.py AssistedDriveController` |
| **Gyro bias calibration on boot** | Without bias removal, heading-hold drifts continuously; automatic calibration during stationary window is mandatory complement | Medium | ✓ Python: 1 s window, stability band ±1 dps |
| **Manual ↔ stabilized mode switch** | Operator can toggle IMU assist on a CRSF channel; allows recovery if IMU fails mid-session | Low | ✓ Python `DriveMode.MANUAL` / `.STABILIZED` |
| **Per-motor current limiting** | BTS7960 has no built-in current limit; without software limiting, sustained stall can thermally destroy the board | HIGH — field-critical for BTS7960 longevity | ✓ Python `motors/current_control.py` |
| **Per-motor power limiting** | Voltage × current cap prevents overload when battery is full (high voltage × same current = higher power) | Medium | ✓ Python `MotorLimitConfig.power_limit_w` |
| **Current sense via BTS7960 IS pin** | BTS7960 provides proportional current sense output (~8.5 mV/A on IS pin); reading it via ADC avoids a separate shunt resistor | Medium | ✓ RP2040 ADC1/ADC2 mapped to L_IS/R_IS at GP27/GP28 |
| **Battery voltage monitoring** | Low-voltage detection triggers audible warning before BMS cutoff; prevents operator-invisible brownout | Medium | ✓ RP2040 ADC0 at GP26 with resistive divider |
| **Channel trim persistence** | RC transmitters have hardware trim, but robot-side trim compensates mechanical asymmetry (one motor stronger than other); survives power cycle | Medium | ✓ Python `settings_store.py MotorTrimStore` |
| **Trim mode via gesture** | Entering trim mode from the RC stick (e.g., hold throttle/steering high for N frames) avoids needing a spare switch | Low | ✓ Python: 4-channel gesture detection |
| **Firmware variant matrix** | Single codebase, multiple hardware targets; operator can swap MCU or driver board without forking firmware | High (architecture) | ✓ PlatformIO target system (see Hardware Variant Matrix below) |
| **Standalone + companion dual mode** | Same firmware can run standalone (CRSF→PWM directly) or as SPI slave under ROS2/Pi; expands capability envelope without hardware change | Medium | ✓ `BIBA_MODE_STANDALONE` / `BIBA_MODE_COMPANION` |
| **Telemetry back to transmitter** | CRSF supports bidirectional telemetry (ELRS → TX → Lua screen); returning battery voltage and LQ to transmitter gives operator heads-up display | Medium | ✓ Python `crsf/telemetry.py`; firmware `app/telemetry.c` |
| **Soft thermal protection** | Throttle-back when estimated or sensed motor temperature approaches limit; prevents hard cutoff under load | Medium | Active requirement `THERMAL-02`; not yet ported to RP2040 |

### IMU Stabilization Implementation Notes

- **Algorithm:** Proportional yaw-rate controller (PD with tunable Kp/Kd). Operator steers provide _desired yaw rate_ (not absolute heading). At neutral stick the heading is locked.
- **Gyro:** BMI160 or LSM6DS3 over I2C (GP20/GP21 on RP2040). Both supported via factory `open_imu_reader()`.
- **Bias removal:** Required; RP2040 port must replicate stationary calibration window on arm.
- **Fallback:** If IMU read fails (I2C error, timeout), `imu_healthy=False` → fall back to MANUAL mode silently.
- **Deadband:** 4 dps yaw-rate deadband prevents overcorrection on micro-vibrations.

---

## Anti-Features (Deliberately NOT for RP2040 Phase)

Features in the Python implementation that are explicitly out of scope for the RP2040 firmware port.
Rationale: resource constraints (264 KB SRAM, no OS), complexity cost vs. field value in Phase 1.

| Anti-Feature | Why Excluded | Where It Lives | Can Add Later? |
|-------------|-------------|----------------|----------------|
| **Voice / audio synthesis** | RP2040 has insufficient flash for compressed audio assets (voice-cache holds ~10 MB WAV); no SD card in target | Python `buzzer/voice_selector.py`, `voice-src/` | Only with external audio IC or SPI flash; post-Phase-1 |
| **BMS (Daly 6S) integration** | BLE/UART BMS polling is a Pi Zero 2W responsibility; RP2040 lacks BLE and sufficient state to manage pack-level SoC | Python `bms/daly.py`, `bms/poller.py` | BMS telemetry can be relayed _through_ Pi over SPI companion channel |
| **Web UI / PID browser tuning** | No TCP/IP stack on RP2040 standalone; web server requires OS scheduler | Python `web/`, `motor_test_api.py` | PID values can be flashed via target_config.h or serial command in future phase |
| **ROS2 integration** | ROS2 is a Pi-side concern; RP2040 only speaks biba_proto SPI when in companion mode | `ros2_ws/`, `biba_stm32_bridge/` | Companion mode SPI bridge is the integration point — already designed in |
| **LED matrix / faro lights** | Hardware not present on current RPICO_RP2040 target; no spare PWM slices budgeted | Not yet implemented anywhere | Next hardware revision |
| **ODrive / VESC motor drivers** | Different driver topology (brushless); requires VESC UART protocol or CAN; separate firmware effort | Documented in variant matrix as `planned` | Future target if brushless drivetrain |
| **Follow-me / autonomous nav** | Requires positioning system (GPS/lidar); out of Phase 1 scope | Conceptual only | ROS2 composition C is the planned path |
| **STM32 SPI bridge from Python side** | Python `stm32_link/` connects Pi → STM32; RP2040 is the replacement MCU, not an add-on | Python `stm32_link/` | Not needed — RP2040 IS the MCU |

---

## Hardware Variant Matrix Patterns

How BiBa and similar projects document multiple board/driver configurations.

### BiBa's Current Pattern: PlatformIO Target Stanzas

```
firmware/
├── platformio.ini          ← env matrix: target × mode
├── targets/
│   ├── BLUEPILL_F103C8/
│   │   ├── target.h        ← pin assignments + BIBA_TARGET_HAS_* flags
│   │   ├── target_config.h ← calibration constants, current limits
│   │   └── target.md       ← human-readable: what this board is, wiring notes
│   ├── BLUEPILL_F103C8_CLONE/  (reuses BLUEPILL_F103C8/target.h, overrides linker)
│   ├── BIBA_F103_REV_A/
│   └── RPICO_RP2040/
└── include/
    ├── biba_board.h        ← shim: #include "target.h" (resolved by -I flag)
    └── biba_config.h       ← shim: #include "target_config.h"
```

**Key rules:**
- Portable `src/` code only includes `biba_board.h` / `biba_config.h` — never `targets/X/target.h` directly
- Feature presence flags: `BIBA_TARGET_HAS_BTS7960_2CH`, `BIBA_TARGET_HAS_CRSF`, `BIBA_TARGET_HAS_IMU`, etc.
- env names: `<target_lowercase>_<mode>` (e.g. `rpico_rp2040_standalone`)
- Clone variants that only differ in RAM size/linker inherit the parent target.h — no directory needed

**VARIANT-01/VARIANT-02 requirements** are satisfied by this pattern: each `target.md` documents wiring, pin assignments, and which features are ready vs. planned.

### Recommended Variant Matrix Table (for `targets/README.md` or `VARIANT-01` doc)

| Target | MCU | Driver | CRSF | IMU | Current Sense | Mode(s) | Status |
|--------|-----|--------|------|-----|--------------|---------|--------|
| `BLUEPILL_F103C8` | STM32F103C8 (20 KB) | BTS7960 2ch | ✓ | ✓ | ADC IS pins | standalone, companion | Ready |
| `BLUEPILL_F103C8_CLONE` | STM32F103C8 clone (8 KB) | BTS7960 2ch | ✓ | ✓ | ADC IS pins | standalone, companion | Ready |
| `BIBA_F103_REV_A` | STM32F103C8 custom | BTS7960 2ch | ✓ | ✓ | ADC IS pins | standalone | Ready |
| `RPICO_RP2040` | RP2040 (264 KB) | BTS7960 2ch | ✓ | ✓ | ADC IS pins | standalone, companion | WIP (Phase 1) |
| `RPICO_RP2040_VESC` | RP2040 | VESC UART | ✓ | ✓ | VESC telemetry | standalone | Planned |

### Comparable Projects' Patterns

**Betaflight / ELRS (HIGH confidence — public repos):**
- `src/target/<BOARD>/target.h` + `target.c` per physical board
- Feature flags: `USE_UART1`, `USE_IMU_MPU6000`, `USE_DSHOT` etc.
- Build matrix: `PLATFORM=STM32F405 make TARGET=OMNIBUSF4`
- Lessons: Keep HAL flags boolean and additive; never use negative flags (`NO_IMU`) — confusing

**PX4 / ArduPilot (MEDIUM confidence):**
- `boards/<manufacturer>/<board>/` with `hwdef.dat` (pin assignments in declarative format)
- Separate `bootloader/` per board
- Lesson: `hwdef.dat` declarative style beats `#define` forests when pin count grows beyond ~30

**BiBa's approach is appropriate for this scale.** PX4-style declarative hwdef would add tooling complexity not justified until >4 targets with >40 pins each.

---

## Feature Complexity Notes

Implementation effort estimates for RP2040 port, relative to existing Python reference.

| Feature | Effort | Risk | Notes |
|---------|--------|------|-------|
| CRSF UART decoder | **Low** | Low | `drivers/crsf.c` already exists for STM32; RP2040 UART API is straightforward. Port = pin/baud config change + DMA buffer |
| BTS7960 PWM output | **Low** | Low | `hal/biba_hal_motor_rp2040.c` already exists (target.h maps GP2/3/6/7). Verify carrier frequency and wrap value |
| Differential drive mixing | **Low** | Low | Pure arithmetic; no hardware dependency |
| Arm/disarm state machine | **Low** | Low | Port Python logic; must gate motor enable pins |
| Failsafe watchdog | **Low** | Medium | Requires hardware timer on RP2040 (use `repeating_timer` or PIO); must survive CRSF parse errors without false triggers |
| Input deadband + ramping | **Low** | Low | Fixed-point arithmetic; Kalman filter from Python is overkill — simple slew-rate limiter sufficient for RP2040 |
| Current sense ADC | **Medium** | Medium | RP2040 ADC is 12-bit, 500 kSPS; BTS7960 IS pin outputs ~8.5 mV/A; need calibration constants in `target_config.h`. ADC noise floor may require oversampling (4× average). Verify IS pin behavior under fast PWM transitions |
| Battery voltage ADC | **Low** | Low | Same ADC infrastructure as current sense; resistive divider constants in `target_config.h` |
| IMU I2C read (BMI160/LSM6DS3) | **Medium** | Low | RP2040 hardware I2C on GP20/GP21; both drivers exist in Python — need C port. GP22 INT1 allows interrupt-driven reads (better than polling) |
| Gyro bias calibration | **Low** | Low | Accumulate N samples on arm if accel magnitude ≈ 1g; subtract mean |
| Yaw-rate PID stabilization | **Medium** | Medium | Port Python PID from `AssistedDriveController`; fixed-point vs float: RP2040 has no FPU (M0+), but soft-float at 125 MHz is adequate (~30 ns/op); profile before optimizing |
| Channel trim persistence | **Medium** | Medium | RP2040 has no EEPROM; must use flash (last 4 KB of 2 MB). RP2040 flash write requires sector erase (4 KB); use wear-leveling ring buffer or simply write on disarm. `littlefs` is available but adds ~20 KB flash |
| Soft thermal protection | **Medium** | High | BTS7960 has no temp sensor; must derive throttle-back from current × time integral (thermal model) or use NTC if wired. High risk: model accuracy depends on mounting thermal resistance — must be tuned per physical build |
| Telemetry back to TX | **Medium** | Low | CRSF bidirectional: RP2040 must TX on same UART0; half-duplex timing critical. Battery voltage frame is simplest to start |
| SPI slave (companion mode) | **High** | Medium | RP2040 SPI1 in slave mode; biba_proto 64-byte CRC-16 frames; DATA_READY GPIO handshake at GP14. Already designed in target.h — implementation effort is the biba_proto state machine in C |
| Melody / buzzer engine | **Low** | Low | PWM tone output; melody table in ROM; port Python `buzzer/melodies.py` note table to C array |

### Phase 1 Critical Path

The following form the hard dependency chain for field-usable RP2040:

```
CRSF decode → channel mapping → arm/disarm → drive mixing → BTS7960 PWM → FAILSAFE
                                                    ↓
                                           current sense → limiter
                                                    ↓
                                              IMU read → yaw-rate PID
```

Trim and telemetry are parallel/additive — implement after the critical path validates.

### Flash / RAM Budget (RP2040 context)

| Component | Estimated Flash | Estimated RAM |
|-----------|----------------|--------------|
| CRSF decoder | ~2 KB | ~0.5 KB |
| BTS7960 driver + HAL | ~1 KB | ~0.1 KB |
| Drive mixing + ramping | ~1 KB | ~0.2 KB |
| Current sense + limiter | ~2 KB | ~0.3 KB |
| IMU driver (BMI160 or LSM6DS3) | ~4 KB | ~0.5 KB |
| Yaw-rate PID | ~1 KB | ~0.2 KB |
| Failsafe + watchdog | ~1 KB | ~0.2 KB |
| Trim store (flash ring) | ~3 KB | ~0.5 KB |
| Telemetry | ~2 KB | ~0.3 KB |
| biba_proto SPI slave | ~4 KB | ~1 KB |
| Melody engine | ~2 KB | ~0.5 KB |
| **Total estimate** | **~23 KB** | **~4.3 KB** |
| **RP2040 budget** | **2048 KB flash** | **264 KB SRAM** |
| **Headroom** | **>2000 KB** | **>259 KB** |

Flash and RAM are not constraints for Phase 1. Build size optimizations are unnecessary.
