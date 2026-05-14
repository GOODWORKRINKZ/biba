---
doc: STRUCTURE
last_mapped: 2026-05-14
---

# Directory Structure

## Top-Level Layout

```
biba/
├── biba-controller/        # Composition A: Python runtime (Pi-only)
│   ├── main.py             # Entry point — ~20 Hz control loop
│   ├── config.py           # Env-var driven runtime configuration
│   ├── motor_test_api.py   # HTTP debug/test API + web UI server
│   ├── pid_tuning.py       # PID param persistence (JSON file store)
│   ├── settings_store.py   # Motor trim persistence (JSON, atomic write)
│   ├── system_stats.py     # CPU/mem % from /proc/stat
│   ├── bms/                # Battery Management System drivers
│   ├── buzzer/             # Audio output (synth, WAV, spectral, beacon)
│   ├── crsf/               # ExpressLRS CRSF UART receiver + telemetry TX
│   ├── imu/                # IMU drivers (BMI160, LSM6DS3) + factory
│   ├── motors/             # Motor drivers, differential drive, current control
│   ├── stm32_link/         # SPI protocol client to STM32 (optional)
│   ├── voice/              # Production WAV voice files + spectral cache builder
│   ├── voice-cache/        # Runtime spectral cache (generated, not committed)
│   ├── web/                # Static assets for motor_test_api HTTP UI
│   ├── Dockerfile          # Composition A container image
│   └── requirements.txt    # Runtime Python dependencies
│
├── firmware/               # STM32F103 + RP2040 firmware (PlatformIO)
│   ├── platformio.ini      # Build environments and targets
│   ├── src/                # Shared C/C++ source
│   │   ├── main.c          # STM32F103 entry point
│   │   ├── main_rp2040.cpp # RP2040 entry point
│   │   ├── app/            # Application logic (control loop, failsafe, telemetry, melody)
│   │   ├── drivers/        # Peripheral drivers (BTS7960, CRSF, current sense, IMU, voltage)
│   │   ├── hal/            # Hardware abstraction layer (STM32 + RP2040 variants)
│   │   ├── modes/          # Mode dispatcher (standalone / companion / combined)
│   │   └── proto/          # biba_proto SPI wire protocol (C side)
│   ├── targets/            # Per-board header overrides (biba_board.h, biba_config.h)
│   ├── include/            # Shared public headers
│   └── test/               # Native PlatformIO unit tests (runs on host)
│
├── ros2_ws/                # Composition C: ROS2 workspace
│   └── src/
│       ├── biba_description/      # URDF/xacro robot description
│       ├── biba_msgs/             # Custom message types
│       ├── biba_stm32_bridge/     # ROS2 node: /cmd_vel → SPI → STM32
│       ├── biba_hardware_stm32/   # ros2_control C++ SystemInterface
│       ├── biba_bringup/          # Launch files + controller config
│       ├── biba_autonomy/         # Hook-point placeholder (Nav2/SLAM)
│       ├── biba_camera/           # Hook-point placeholder (FPV/ML)
│       ├── biba_manipulator/      # Hook-point placeholder (servo arm)
│       ├── biba_remote_bridge/    # Hook-point placeholder (Zenoh/WebRTC)
│       └── biba_uwb_follow/       # Hook-point placeholder (UWB tag follow)
│
├── docker/
│   ├── legacy-pi/          # Composition A: docker-compose.yml
│   ├── ros2/               # Composition C: docker-compose.yml
│   └── base/               # Shared base images (ros2-zenoh, ros2-control)
│
├── tests/                  # Pytest suite (~40 test files, no hardware required)
├── scripts/                # Deployment and diagnostic scripts
├── docs/                   # Architecture, deployment, wiring, ROS2 docs
├── artifacts/              # Runtime captures (telemetry traces, VCP)
├── voice-src/              # Voice phrase definitions (phrases.yml)
├── voice-work/             # TTS processing workspace (per-event subdirs)
├── lua/                    # ExpressLRS Lua telemetry screen scripts
└── pytest.ini              # Pytest configuration
```

---

## Key Files

| File | Purpose |
|------|---------|
| `biba-controller/main.py` | Main runtime entry point. `main()` at line 1298. ~1800 lines. Contains the 20 Hz loop, all subsystem wiring, arm/disarm logic, voice event dispatch. |
| `biba-controller/config.py` | ~190 env-var constants. All hardware pin assignments, thresholds, feature flags. Read once at import; never modified at runtime. |
| `biba-controller/motor_test_api.py` | stdlib `ThreadingHTTPServer` serving motor PWM test UI and PID tuning page. Runs as a sidecar thread in main(). |
| `biba-controller/stm32_link/protocol.py` | Pure-Python codec for `biba_proto` SPI frames. Must stay in lock-step with `firmware/src/proto/biba_proto.h`. |
| `firmware/src/proto/biba_proto.h` | C header defining the 64-byte SPI wire protocol shared between firmware and Python. |
| `firmware/src/modes/mode_companion.c` | STM32 companion mode: SPI slave, receives setpoints from SBC, applies current limiting, returns telemetry. |
| `firmware/src/app/control_loop.c` | Motor current limiting, PID helpers. Mirrored in Python as `motors/current_control.py`. |
| `ros2_ws/src/biba_stm32_bridge/biba_stm32_bridge/bridge_node.py` | `Stm32BridgeNode` — the only ROS2 node that talks SPI to STM32. Imports `stm32_link/` from biba-controller path. |
| `ros2_ws/src/biba_stm32_bridge/biba_stm32_bridge/translator.py` | Twist → differential setpoint math. Pure logic, no ROS2 imports. |
| `docs/system_architecture.md` | Canonical three-composition overview. Russian language. Authoritative source for architectural decisions. |
| `tests/test_biba_proto_drift.py` | CI drift test that diffs Python and C protocol implementations. Fails if they diverge. |
| `pytest.ini` | Pytest config; all tests in `tests/`. |

---

## Module Map

### `biba-controller/bms/`

| File | Responsibility |
|------|---------------|
| `daly.py` | Daly BMS serial (UART) and BLE protocol decoder; `DalyBMS` / `DalyBMSBle` classes; `BatteryState` dataclass |
| `poller.py` | `BMSPoller`: background thread that calls `bms.read_state()` on an interval; thread-safe `latest_state` property |
| `__init__.py` | Re-exports `BatteryState` |

### `biba-controller/buzzer/`

| File | Responsibility |
|------|---------------|
| `beacon.py` | `BeaconManager`: manages SOS beacon state (manual trigger + automatic on failsafe) |
| `blheli_parser.py` | Parser for BLHeli melody strings (note + duration tokens) |
| `melodies.py` | Hard-coded `FUN_PLAYLIST` melody list |
| `motor_synth.py` | `MotorSynth`: plays tones via motor coil PWM; wraps `WavPlayer` for named melody dispatch |
| `voice_selector.py` | `VoiceSelector`: round-robin selection of variant WAV files per event from a base directory |
| `wav_player.py` | PCM-over-PWM and spectral vocoder playback through pigpio hardware PWM; spectral cache read/write |

### `biba-controller/crsf/`

| File | Responsibility |
|------|---------------|
| `protocol.py` | Pure CRSF frame parser: `parse_frame()`, `pop_frame_from_buffer()`, `build_frame()` |
| `receiver.py` | `CRSFReceiver`: serial port reader + channel decoder (11-bit packed → 16 floats normalized to -1..1) |
| `telemetry.py` | `CRSFTelemetry`: sends CRSF battery and GPS (repurposed for system metrics) telemetry frames back to TX |

### `biba-controller/imu/`

| File | Responsibility |
|------|---------------|
| `__init__.py` | `IMUSample` dataclass; `IMUReader` base class; `NullIMUReader` |
| `bmi160.py` | `BMI160Reader`: BMI160 gyro/accel over I2C (smbus2) |
| `lsm6ds3.py` | `LSM6DS3Reader`: LSM6DS3 gyro/accel over I2C |
| `factory.py` | `open_imu_reader()`: WHO_AM_I autodetect → BMI160 or LSM6DS3 instance |

### `biba-controller/motors/`

| File | Responsibility |
|------|---------------|
| `driver.py` | `MotorDriver` (PWM+DIR), `BTS7960MotorDriver` (RPWM/LPWM/REN/LEN); `DifferentialDrive`: mix+ramp+failsafe |
| `ramping.py` | `SpeedRamp` (slew limiter), `ScalarKalmanFilter` (throttle smoothing) |
| `assisted_drive.py` | `AssistedDriveController`: yaw-rate PID stabilization; `DriveMode` enum (MANUAL / STABILIZED) |
| `current_control.py` | `apply_motor_limits()`: scale down duty if current or power exceeds configured limits |
| `current_sense.py` | `ADS1115CurrentReader`: ADS1115 I2C ADC polling; `NullMotorCurrentReader` |

### `biba-controller/stm32_link/`

| File | Responsibility |
|------|---------------|
| `protocol.py` | `biba_proto` Python codec: frame encode/decode, CRC-16/CCITT, `Command`/`TelemetryId` enums, `Flag` bitfield |
| `client.py` | `STM32Link`: spidev SPI master; `send_receive()` for full-duplex frame exchange; lazy-imports `spidev` |

### `biba-controller/voice/`

Production WAV files for 8 event names: `startup`, `arm`, `disarm`, `connected`, `disconnected`, `failsafe`, `low_voltage`, `sos`. `build_spectral_cache.py` regenerates the spectral frame cache.

### `biba-controller/web/`

Static assets for the motor test HTTP UI: `settings.html`, `settings.css`, `settings.js`, `biba-neon-sign.svg`. Served directly from disk by `motor_test_api.py`.

### `ros2_ws/src/biba_stm32_bridge/`

| File | Responsibility |
|------|---------------|
| `bridge_node.py` | `Stm32BridgeNode`: subscribes `/cmd_vel`, publishes `/biba/stm32/telemetry` + `/biba/crsf/status`; service `/biba/arm` |
| `translator.py` | `Twist` → `(left_duty, right_duty)` pure math; no ROS2 imports |

### `ros2_ws/src/biba_msgs/`

Custom message definitions: `CrsfStatus.msg`, `Stm32Telemetry.msg`, `MotorAudio.msg` (in `msg/` subdirectory).

### `ros2_ws/src/biba_hardware_stm32/`

C++ ros2_control `SystemInterface` plugin. Bridges `controller_manager` joint commands to `STM32Link::send_receive()`. Plugin registered in `biba_hardware_stm32_plugin.xml`.

### `ros2_ws/src/biba_bringup/`

ROS2 launch files:
- `launch/control.launch.py` — starts controller_manager with diff_drive_controller
- `launch/twist_mux.launch.py` — starts twist_mux with priority-ordered input topics
- `config/` — YAML controller and twist_mux configs

### `ros2_ws/src/biba_description/`

URDF/xacro robot description. Launch file publishes TF via `robot_state_publisher`.

### `firmware/src/modes/`

| File | Responsibility |
|------|---------------|
| `mode_standalone.c` | CRSF → mixer → BTS7960 PWM; no SBC |
| `mode_companion.c` | SPI slave: receives `SET_SETPOINT` from SBC, applies current limiting, returns `SNAPSHOT` telemetry |
| `mode_dispatcher.c/h` | Selects active mode (compile-time flag or runtime detection) |

### `firmware/src/hal/`

Hardware abstraction for STM32F103 and RP2040 targets. `biba_hal.c` provides the common interface; `biba_hal_motor.c` and `biba_hal_motor_rp2040.c` provide target-specific PWM implementations.

### `scripts/`

| File | Responsibility |
|------|---------------|
| `update.sh` | Robot-side deployment: pulls latest GHCR image, restarts compose stack |
| `diagnostics.sh` | Runtime diagnostics: service status, GPIO, logs |
| `biba_monitor.py` | Live telemetry monitor |
| `vcp_capture.py` | VCP (virtual COM port) capture for CRSF telemetry logging |
| `voice_prep.py` | Voice file processing pipeline: TTS → ffmpeg → WAV profiles |
| `biba_aliases.sh` | Shell aliases for common robot operations |
| `setup/` | Initial setup scripts |

### `tests/`

Pytest test suite. All tests run without hardware (pigpio, spidev, smbus2 are mocked). ~40 test files, each named `test_<module>.py`. Key coverage areas: CRSF protocol, STM32 link protocol, motors, BMS, IMU, buzzer, voice, PID tuning, settings store, ROS2 package skeleton.

---

## Naming Conventions

### Files
- Python modules: `snake_case.py`
- Test files: `test_<module>.py` in `tests/`
- ROS2 packages: `biba_<subsystem>` (underscore-separated)
- Firmware C files: `snake_case.c` / `snake_case.h`
- Docker: `Dockerfile`, `Dockerfile.<variant>`, `docker-compose.yml`

### Classes
- Python: `PascalCase` (e.g., `BTS7960MotorDriver`, `CRSFReceiver`, `AssistedDriveController`)
- Null objects: `_Null<Name>` with leading underscore (e.g., `_NullDrive`, `_NullBuzzer`)
- Dataclasses: `PascalCase`, often `frozen=True` (e.g., `BatteryState`, `PidTuningSnapshot`)
- Firmware C: `biba_<subsystem>_<entity>_t` for types, `biba_<verb>_<noun>()` for functions

### Functions
- Python: `snake_case`; private/internal: `_snake_case` with leading underscore
- Factory functions: `open_<thing>()`, `create_<thing>()`, `_create_<thing>()`
- Constants: `UPPER_SNAKE_CASE` at module level

### Environment Variables / Config
- All config driven by env vars in `UPPER_SNAKE_CASE`
- GPIO pin assignments: `<SIDE>_MOTOR_<SIGNAL>` (e.g., `LEFT_MOTOR_RPWM`, `RIGHT_MOTOR_LEN`)
- Feature flags: `<FEATURE>_ENABLED` (e.g., `MOTOR_CURRENT_LIMITING_ENABLED`, `STM32_LINK_ENABLED`)
- Channel indices: `CH_<FUNCTION>` (e.g., `CH_THROTTLE`, `CH_ARM`, `CH_BEACON`)

### Where to Add New Code

| Task | Location |
|------|----------|
| New hardware driver (sensor/actuator) | New subdirectory under `biba-controller/<subsystem>/`; `__init__.py` + `<driver>.py` + factory function |
| New ROS2 node | New package under `ros2_ws/src/biba_<name>/` following existing `biba_stm32_bridge` layout |
| New firmware driver | `firmware/src/drivers/<name>.c` + `<name>.h`; add HAL variant if hardware-specific |
| New config parameter | Add to `biba-controller/config.py` using existing `_get_env_*()` helpers |
| New test | `tests/test_<module>.py`; use `monkeypatch` for env vars, mock hardware with fakes |
| New custom ROS2 message | `ros2_ws/src/biba_msgs/msg/<Name>.msg` + update `CMakeLists.txt` |
| New voice event | Add WAV file to `biba-controller/voice/`; add key to `_SYNTH_EVENT_NAMES` in `main.py`; add config vars for voice group |
