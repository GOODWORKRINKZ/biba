---
doc: STACK
last_mapped: 2026-05-14
---

# Tech Stack

## Languages

| Language | Version | Where used |
|----------|---------|------------|
| Python | 3.11 | Primary controller runtime (`biba-controller/`) |
| C (GNU11) | C11 | STM32/RP2040 firmware (`firmware/src/`) |
| C++ | via Arduino | RP2040 main entry (`firmware/src/main_rp2040.cpp`), `biba_hardware_stm32` ROS2 plugin |
| Lua | ELRS v3 | RC telemetry screen (`lua/elrsV3.lua`, `lua/SCRIPTS/`) |
| YAML | - | Voice phrases manifest (`voice-src/phrases.yml`), ROS2 launch configs |
| Bash | - | Deployment scripts (`scripts/biba_aliases.sh`, `scripts/update.sh`, `scripts/diagnostics.sh`) |

## Runtime & Platform

**Target hardware:** Raspberry Pi Zero 2W (`linux/arm64`)

**Container runtime:**
- Docker Engine with Compose V2
- Images built for `linux/arm64` via Docker Buildx (dev machine) and GitHub Actions `setup-qemu-action`
- Registry: `ghcr.io/goodworkrinkz/biba/`

**Python runtime:** `python:3.11-slim-bookworm` (base image in `biba-controller/Dockerfile`)

**ROS2 distribution:** Humble (`ros:humble-ros-base`, base image in `docker/base/Dockerfile.ros2-zenoh`)

**OS dependencies (controller container):**
- `pigpiod` v79 — built from source in multi-stage `biba-controller/Dockerfile`, provides GPIO/PWM daemon
- `procps` — system stats from `/proc`

## Frameworks & Libraries

### Python Controller (`biba-controller/requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| `pigpio` | latest | GPIO/PWM via pigpiod daemon; motor drive, buzzer, spectral voice PWM |
| `pyserial` | latest | UART: CRSF receiver (`/dev/ttyS0`), Daly BMS UART (`/dev/ttyUSB0`) |
| `bleak` | latest | BLE async client: Daly BMS BLE transport |
| `smbus2` | latest | I2C: ADS1115 current sense, BMI160/LSM6DS3 IMU |
| `PyYAML` | `>=6,<7` | Config/manifest loading |

### ROS2 Stack (Composition C)

| Package | Source |
|---------|--------|
| `rclpy`, `rclcpp` | ROS2 Humble |
| `rclcpp_lifecycle` | ROS2 Humble |
| `ros2_control` / `hardware_interface` | `docker/base/Dockerfile.ros2-control` |
| `diff_drive_controller` | ros2_control |
| `joint_state_broadcaster` | ros2_control |
| `controller_manager` | ros2_control |
| `twist_mux` | `docker/base/Dockerfile.ros2-control` |
| `robot_state_publisher` | ROS2 Humble |
| `rmw_zenoh_cpp` (Zenoh DDS) | `docker/base/Dockerfile.ros2-zenoh` |
| `xacro` | ROS2 Humble |
| `pluginlib` | ROS2 Humble |
| `rosidl_default_generators` | ROS2 Humble (for `biba_msgs`) |

### Firmware (`firmware/`)

| Tool/Framework | Usage |
|----------------|-------|
| PlatformIO | Build system and board abstraction |
| `ststm32` platform + `stm32cube` framework | STM32F103 targets |
| `earlephilhower/arduino-pico` (rp2040 platform) | RP2040 target |
| Unity (`throwtheswitch/Unity@^2.6.1`) | Native host unit tests (`env:native_test`) |

## Dependencies

### Core (production, `biba-controller/requirements.txt`)
- `pigpio` — GPIO/PWM daemon client
- `pyserial` — UART serial ports
- `bleak` — BLE async (Daly BMS BLE transport)
- `smbus2` — I2C bus (ADS1115, IMU)
- `PyYAML>=6,<7` — YAML parsing

### Dev/Test (`requirements-dev.txt`)
Extends core requirements with:
- `pytest>=8,<9` — test runner
- `ruff>=0.11,<1` — Python linter/formatter
- `matplotlib>=3.9,<4` — telemetry analysis scripts (e.g., `scripts/biba_monitor.py`)
- `PyYAML>=6,<7` — (shared with core)

### Implicit runtime deps (not in requirements.txt)
- `spidev` — SPI master for STM32 link (`biba-controller/stm32_link/client.py`), imported lazily only when `STM32_LINK_ENABLED=1`
- `wave` (stdlib) — WAV file parsing for voice playback

## Build & Tooling

### Python
- **Linter/formatter:** `ruff` (config not committed; CI runs `ruff check` + `ruff format`)
- **Test runner:** `pytest` with config in `pytest.ini` (`testpaths = tests`)
- **No setup.py / pyproject.toml** — controller runs directly from source in Docker

### Firmware
- **Build system:** PlatformIO (`firmware/platformio.ini`)
- **Targets:** `bluepill_f103c8`, `bluepill_f103c8_clone`, `biba_f103_rev_a`, `rpico_rp2040`
- **Modes per target:** `standalone`, `companion`, `combined` → e.g. `bluepill_f103c8_clone_companion`
- **Default env:** `rpico_rp2040_standalone`
- **Native tests:** `env:native_test` (platform=native, Unity framework)
- **Upload:** ST-Link (`upload_protocol = stlink`) for STM32; `picotool` for RP2040
- **Debug:** ST-Link + semihosting for F103 clone; CMSIS-DAP for RP2040

### ROS2
- **Build system:** `colcon` (builds `ros2_ws/` inside `docker/ros2/Dockerfile`)
- **Message IDL:** `rosidl_default_generators` for `biba_msgs`

### CI/CD (GitHub Actions, `.github/workflows/`)
| Workflow | Trigger | What it builds |
|----------|---------|----------------|
| `G-Build-All.yml` | push to `main`, manual | Orchestrates all 4 workflows |
| `G-Build-Controller-Image.yml` | push/tag/PR | `biba-controller` Docker image → GHCR |
| `G-Build-STM32F103.yml` | push/tag | PlatformIO firmware build |
| `G-Build-ROS2-Bases.yml` | push/tag | `biba-ros2-zenoh` + `biba-ros2-control` base images → GHCR |
| `G-Build-ROS2-Stack.yml` | after bases | Full ROS2 colcon build image → GHCR |

**Image tags:** `latest` (main), `dev` (develop), `test` (other branches), `v*` (git tags), `<sha>` (always)

## Configuration

### Controller configuration (`biba-controller/config.py`)
All settings are environment variables with defaults. No YAML/TOML config files for runtime.
Key config groups:
- Motor driver: `MOTOR_DRIVER_TYPE`, `BTS7960_PWM_MODE`, GPIO pin assignments (`LEFT_MOTOR_RPWM`, etc.)
- CRSF: `CRSF_PORT=/dev/ttyS0`, `CRSF_BAUD=420000`
- BMS: `BMS_TRANSPORT={BLE|UART}`, `BMS_PORT`, `BMS_BLE_ADDRESS`, BLE UUIDs
- IMU: `IMU_ENABLED`, `IMU_I2C_BUS`, `IMU_I2C_ADDRESS`, `IMU_EXPECTED_CHIP_ID`
- Current sense: `MOTOR_CURRENT_SENSE_ENABLED`, `MOTOR_CURRENT_SENSE_I2C_ADDRESS=0x48`
- STM32 SPI link: `STM32_LINK_ENABLED=0`, `STM32_LINK_SPI_BUS`, `STM32_LINK_SPI_SPEED_HZ=8000000`
- PID/drive: `DRIVE_MODE_YAW_RATE_KP/KI/KD`, `RAMP_ACCEL_RATE`, `THROTTLE_FILTER_MODE`
- Voice/sound: `SOUND_MODE={VOICE|SPECTRAL_VOICE|SYNTH}`, `STARTUP_VOICES`, etc.
- HTTP API: `MOTOR_TEST_API_PORT=8765`
- Logging: `LOG_LEVEL=INFO`

### Persistent data (Docker volume `biba-controller-data` → `/data`)
- `/data/motor-trim.json` — persisted motor trim value
- `/data/pid-tuning.json` — persisted PID tuning snapshot
- `/data/current-trace.jsonl` — motor current telemetry trace (when enabled)

### ROS2 config (in `ros2_ws/src/biba_bringup/config/`)
- `diff_drive_controller.yaml` — wheel geometry, max wheel speed
- `twist_mux.yaml` — cmd_vel arbitration priorities

### Secrets management
No secrets in codebase. BMS BLE address and image tags injected via Docker Compose `.env` file (not committed; `.env.example` provided).
