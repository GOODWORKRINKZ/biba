---
doc: ARCHITECTURE
last_mapped: 2026-05-14
---

# Architecture

## Pattern

**Dual-stack embedded platform with optional ROS2 overlay.**

BiBa supports three hardware compositions managed from the same repository:

- **Composition A (Pi-only):** Raspberry Pi Zero 2W runs the full Python runtime in `biba-controller/`. Pi reads CRSF over UART, mixes, ramps, and directly drives BTS7960 H-bridges via GPIO/pigpio.
- **Composition B (STM32-only):** STM32F103 operates standalone — reads CRSF, drives PWM, provides telemetry. No SBC.
- **Composition C (Pi + STM32):** STM32 handles all low-level CRSF/PWM/current-limiting. Pi runs a ROS2 stack (`ros2_ws/`) and sends setpoints via SPI. This is the path for Nav2, SLAM, manipulation, and internet bridging.

The key architectural rule: **wherever STM32 is present, it owns CRSF UART.** The SBC receives channel values and RSSI only through SPI telemetry from the STM32. Pi-only composition reads CRSF itself.

---

## Layers / Components

### Composition A — Python Runtime (`biba-controller/`)

```
┌─────────────────────────────────────────────────────────────────┐
│            Entry Point: biba-controller/main.py                  │
│   ~20 Hz control loop: read CRSF → mix → ramp → limit → drive   │
├──────────────┬──────────────┬───────────────┬───────────────────┤
│  CRSF Layer  │  Motor Layer │  Sensor Layer │  Audio Layer      │
│  crsf/       │  motors/     │  bms/, imu/   │  buzzer/, voice/  │
├──────────────┴──────────────┴───────────────┴───────────────────┤
│              Configuration: config.py (env-var driven)           │
│              Persistence: settings_store.py, pid_tuning.py       │
├──────────────────────────────────────────────────────────────────┤
│      Web / Debug API: motor_test_api.py + web/                   │
│      (stdlib ThreadingHTTPServer on MOTOR_TEST_API_PORT)         │
├──────────────────────────────────────────────────────────────────┤
│   STM32 SPI Link (optional): stm32_link/  [STM32_LINK_ENABLED=1] │
└──────────────────────────────────────────────────────────────────┘
         │ pigpio GPIO/PWM          │ UART (serial)
         ▼                          ▼
   BTS7960 H-bridges            CRSF receiver / ExpressLRS TX
```

### Composition C — ROS2 Stack (`ros2_ws/`)

```
┌──────────────────────────────────────────────────────────────────┐
│  twist_mux  →  /cmd_vel  →  biba_stm32_bridge (Python ROS2 node) │
│                              ros2_ws/src/biba_stm32_bridge/       │
├──────────────────────────────────────────────────────────────────┤
│  biba_hardware_stm32 (C++ ros2_control SystemInterface)          │
│  ros2_ws/src/biba_hardware_stm32/                                │
├──────────────────────────────────────────────────────────────────┤
│  biba_stm32_bridge/stm32_link/  ←  reuses biba-controller code   │
└────────────────────────┬─────────────────────────────────────────┘
                         │ SPI (biba_proto)
                         ▼
              STM32F103 firmware/  (companion mode)
```

### Firmware (`firmware/`)

```
firmware/src/
├── main.c / main_rp2040.cpp     # MCU entry point, peripheral init
├── modes/
│   ├── mode_standalone.c        # CRSF → local PWM (no SBC)
│   ├── mode_companion.c         # SPI slave, SBC owns setpoints
│   └── mode_dispatcher.c        # selects mode at compile/runtime
├── app/
│   ├── control_loop.c/h         # current limiting, PID helpers
│   ├── failsafe.c/h             # SPI watchdog + CRSF watchdog
│   ├── telemetry.c/h            # builds SPI telemetry snapshots
│   └── melody.c/h               # buzzer melody engine
├── drivers/
│   ├── bts7960.c/h              # H-bridge PWM driver
│   ├── crsf.c/h                 # CRSF UART decoder
│   ├── current_sense.c/h        # ADC current sense
│   ├── imu.c/h                  # gyro/accel I2C
│   └── voltage_sense.c/h        # battery voltage ADC
├── hal/
│   ├── biba_hal.c/h             # hardware abstraction layer
│   ├── biba_hal_motor.c         # STM32F103 PWM output
│   └── biba_hal_motor_rp2040.c  # RP2040 PWM output
└── proto/
    ├── biba_proto.c/h           # SPI wire protocol (64-byte frames, CRC-16/CCITT)
```

---

## Entry Points

| Entry Point | Path | Description |
|-------------|------|-------------|
| Python runtime | `biba-controller/main.py` → `main()` at line 1298 | ~20 Hz control loop; initializes all subsystems, runs until SIGTERM |
| Firmware (STM32F103) | `firmware/src/main.c` | PlatformIO C entry; dispatches to standalone/companion mode |
| Firmware (RP2040) | `firmware/src/main_rp2040.cpp` | RP2040 variant |
| ROS2 bridge node | `ros2_ws/src/biba_stm32_bridge/biba_stm32_bridge/bridge_node.py` | `Stm32BridgeNode` — subscribes `/cmd_vel`, publishes telemetry |
| Voice audition mode | `biba-controller/main.py` → `_run_voice_audition_mode()` at line 505 | Activated by `VOICE_AUDITION_ENABLED=1` env var |
| Motor test web API | `biba-controller/motor_test_api.py` → `create_motor_test_server()` | stdlib `ThreadingHTTPServer`, runs in sidecar thread |

---

## Data Flow

### Composition A — Primary Control Loop (~20 Hz)

1. **CRSF read** — `CRSFReceiver.read_frame()` (`biba-controller/crsf/receiver.py`) reads serial bytes; returns 16 RC channels normalized to -1.0..1.0
2. **Arm/mode decode** — `main.py:_is_armed()`, `_get_drive_mode()`, `_get_speed_mode_scale()` interpret specific channels
3. **IMU-assisted drive** (optional) — `AssistedDriveController.compute()` (`motors/assisted_drive.py`) applies yaw-rate PID stabilization if drive mode ≠ MANUAL
4. **Throttle filter** — `ScalarKalmanFilter` (`motors/ramping.py`) smooths throttle input
5. **Mix + ramp** — `DifferentialDrive.mix_and_ramp()` (`motors/driver.py`) converts throttle/steering to left/right duty with speed ramps
6. **Motor trim** — `_apply_motor_trim()` in `main.py` adds saved trim offset
7. **Current limiting** — `apply_motor_limits()` (`motors/current_control.py`) reads ADS1115 ADC samples and scales down duty if current/power exceeded
8. **Drive output** — `DifferentialDrive.apply_output()` → `BTS7960MotorDriver.set_speed()` → pigpio PWM
9. **CRSF telemetry TX** — `CRSFTelemetry.send_battery()` + `send_system()` (`crsf/telemetry.py`) at `BMS_POLL_INTERVAL_S` cadence
10. **BMS** — `BMSPoller` runs in background thread; exposes `latest_state: Optional[BatteryState]` with a lock

### Composition A — STM32 SPI Path (opt-in, `STM32_LINK_ENABLED=1`)

1. `STM32Link.send_receive()` (`stm32_link/client.py`) performs full-duplex SPI exchange of 64-byte `biba_proto` frames
2. Pi sends `SET_SETPOINT` command with Q15 left/right duty; STM32 replies with `SNAPSHOT` telemetry
3. Protocol defined in `stm32_link/protocol.py` (Python) and `firmware/src/proto/biba_proto.h` (C) — kept byte-for-byte identical; CI drift test in `tests/test_biba_proto_drift.py`

### Composition C — ROS2 Control Flow

1. `twist_mux` (launch `ros2_ws/src/biba_bringup/launch/twist_mux.launch.py`) arbitrates competing `/cmd_vel` sources with priorities: CRSF > manual teleop > autonomy
2. `Stm32BridgeNode` subscribes `/cmd_vel`, converts `Twist` to differential setpoint via `translator.py`, sends `SET_SETPOINT` to STM32 via SPI at `setpoint_rate_hz` (default 50 Hz)
3. STM32 telemetry is read at `telemetry_rate_hz` (default 20 Hz) and published as `biba_msgs/Stm32Telemetry` and `biba_msgs/CrsfStatus`
4. `biba_hardware_stm32` implements `ros2_control` `SystemInterface` — exposes wheel joints to `diff_drive_controller`

### Audio / Voice

- **Synth mode:** `MotorSynth` (`buzzer/motor_synth.py`) generates motor-coil tones via hardware PWM pins (pigpio)
- **Voice mode:** `WavPlayer` (`buzzer/wav_player.py`) plays WAV files either as PCM-over-PWM (carrier modulation) or as spectral vocoder (STFT → dominant-frequency frame sequence)
- `VoiceSelector` (`buzzer/voice_selector.py`) implements round-robin selection across variant files for each event
- `BeaconManager` (`buzzer/beacon.py`) manages SOS/beacon state independent of main arm state

---

## Abstractions

### Null Object Pattern (Composition A)

`main.py` defines two null objects used when hardware is absent:

- `_NullDrive` — duck-type compatible with `DifferentialDrive`; all motor methods return `(0.0, 0.0)`. Used when motor driver init fails.
- `_NullBuzzer` — duck-type compatible with the full buzzer; all methods are no-ops. Used when `SOUND_MODE=none` or init fails.

Also from library code:
- `NullIMUReader` (`imu/__init__.py`) — returns stale zero samples
- `NullMotorCurrentReader` (`motors/current_sense.py`) — returns `valid=False` samples

### Protocol Codecs (biba_proto)

`stm32_link/protocol.py` is the canonical Python implementation of the SPI wire format. It mirrors `firmware/src/proto/biba_proto.h` field-for-field:
- 64-byte fixed frames: 8 byte header, up to 54 byte payload, 2 byte CRC-16/CCITT
- Sync bytes `0xBA 0xBB`, version, command/telemetry ID, sequence counter, flags bitfield

### Factory Functions

- `imu/factory.py:open_imu_reader()` — autodetects BMI160 vs LSM6DS3 by WHO_AM_I register; returns typed reader
- `motors/current_sense.py:open_ads1115_current_reader()` — creates configured ADS1115 reader
- `main.py:_create_buzzer()`, `_create_motor_pair()`, `_create_bms()` — all env-var driven factories

### Configuration Module

`config.py` is a flat module of constants read from environment variables at import time. No classes. All values are module-level. Tests patch via `monkeypatch.setattr(main.config, ...)` or `monkeypatch.setenv(...)` + reimport.

### Dataclasses (immutable state)

- `BatteryState` (`bms/daly.py`) — voltage, current, SOC, cells, temps
- `IMUSample` (`imu/__init__.py`) — gyro_z_dps, accel_x/y/z_g, timestamp
- `AssistedDriveConfig`, `AssistedDriveResult` (`motors/assisted_drive.py`) — frozen PID config and per-tick result
- `PidTuningSnapshot` (`pid_tuning.py`) — 8 PID parameters, serializable to JSON
- `MotorCurrentSample`, `MotorLimitConfig`, `MotorLimitResult` (`motors/current_control.py`)
- `STM32LinkConfig` (`stm32_link/client.py`) — SPI bus params

---

## Component Boundaries

### How Subsystems Decouple

| Boundary | Mechanism |
|----------|-----------|
| BMS → main loop | `BMSPoller` background thread; `latest_state` property behind `threading.Lock`; main loop reads at `BMS_POLL_INTERVAL_S` cadence |
| IMU → main loop | `IMUReader.read_sample()` called inline each loop tick; returns stale `NullIMUReader` sample on error |
| Motor current → main loop | `MotorCurrentReader.read_sample()` called inline; returns `valid=False` on error; current limiting is fail-open (keeps requested duty) |
| STM32 ↔ Pi (Composition C) | Full-duplex 64-byte SPI frames via `biba_proto`; Python `stm32_link/` reused by both `biba-controller/` (as optional path) and `ros2_ws/src/biba_stm32_bridge/` (as main path) |
| ROS2 ↔ STM32 | `Stm32BridgeNode` is the sole SPI master in Composition C; no other ROS2 node touches SPI directly |
| Web API ↔ main loop | `MotorTestExecutor` shares state with main loop via `threading.Event` and `threading.Lock`; HTTP server runs in `ThreadingHTTPServer` sidecar thread |
| Voice playback ↔ main loop | Fire-and-forget: either direct call (synth) or `threading.Thread(..., daemon=True).start()` for wav/spectral playback |
| Config ↔ everything | All subsystems import `config` as a module; no dependency injection of config. Tests patch module attributes directly. |

### Failsafe Architecture

- **Composition A:** `DifferentialDrive.check_failsafe()` detects CRSF frame timeout (`CRSF_TIMEOUT_S`); immediately calls `drive(0.0, 0.0)` and disarms
- **Composition C:** STM32 owns independent dual-watchdog: CRSF timeout cuts PWM directly; SPI watchdog (`SPI_LINK_TIMEOUT_MS`) cuts PWM if Pi stops sending frames. Pi failure is safe by design.
- **Arm/Disarm ownership:** In Composition C, arm/disarm is owned by STM32 (CRSF channel). The ROS2 `/biba/arm` service can only request disarm, not force arm during CRSF failsafe.

### Protocol Lock-Step Guarantee

`stm32_link/protocol.py` and `firmware/src/proto/biba_proto.h` must stay identical. CI enforces this via `tests/test_biba_proto_drift.py`, which diffs vendored copies against the canonical source.
