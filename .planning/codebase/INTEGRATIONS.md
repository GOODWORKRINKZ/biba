---
doc: INTEGRATIONS
last_mapped: 2026-05-14
---

# Integrations

## Hardware Interfaces

### GPIO / PWM — pigpio daemon
- **Library:** `pigpio` (Python client) + `pigpiod` v79 (C daemon)
- **Purpose:** Motor PWM signals, buzzer tone generation, spectral voice playback
- **Devices exposed to container:** `/dev/gpiomem`, `/dev/vcio`, `/dev/mem` (all `privileged: true`)
- **Motor pins (BTS7960 mode, defaults):**
  - Left: `RPWM=12`, `LPWM=18`, `REN=23`, `LEN=24`
  - Right: `RPWM=19`, `LPWM=13`, `REN=20`, `LEN=21`
- **Buzzer pin:** `BUZZER_PIN=17`
- **PWM frequency:** `PWM_FREQUENCY_HZ=20000` Hz (software or hardware mode)
- **Config:** `biba-controller/config.py` (`LEFT_MOTOR_*`, `RIGHT_MOTOR_*`, `BUZZER_PIN`)
- **Driver code:** `biba-controller/motors/driver.py` (BTS7960MotorDriver, DifferentialDrive)

### UART — CRSF / ExpressLRS receiver
- **Port:** `/dev/ttyS0` (default), env `CRSF_PORT`
- **Baud rate:** 420000 bps (`CRSF_BAUD`)
- **Protocol:** CRSF (Crossfire Serial Protocol) — 16 channels, 11-bit packed, ~50 Hz
- **Library:** `pyserial`
- **Receiver code:** `biba-controller/crsf/receiver.py` (`CRSFReceiver`)
- **Protocol code:** `biba-controller/crsf/protocol.py`
- **Back-channel telemetry:** Battery sensor frame + GPS frame (repurposed for BiBa system metrics: CPU%, RAM%, per-motor current mA) sent back via same UART using `CRSFTelemetry` (`biba-controller/crsf/telemetry.py`)
- **Exposed to container:** `/dev/ttyS0:/dev/ttyS0`

### UART — Daly BMS (USB-UART mode)
- **Port:** `/dev/ttyUSB0` (default), env `BMS_PORT`
- **Baud rate:** 9600 bps (`BMS_BAUD`)
- **Enabled when:** `BMS_TRANSPORT=UART`
- **Library:** `pyserial`
- **Driver:** `biba-controller/bms/daly.py` (`DalyBMS`)
- **Exposed to container:** `/dev/ttyUSB0:/dev/ttyUSB0`

### BLE — Daly BMS (Bluetooth Low Energy mode)
- **Default mode:** `BMS_TRANSPORT=BLE`
- **Library:** `bleak` (async BLE client)
- **Configuration:**
  - `BMS_BLE_ADDRESS` — BLE MAC address (required, set in `.env`)
  - `BMS_BLE_SERVICE_UUID` — `0000fff0-0000-1000-8000-00805f9b34fb`
  - `BMS_BLE_WRITE_UUID` — `0000fff2-0000-1000-8000-00805f9b34fb`
  - `BMS_BLE_NOTIFY_UUID` — `0000fff1-0000-1000-8000-00805f9b34fb`
  - `BMS_BLE_TIMEOUT_S=1.5`
- **D-Bus socket** mounted: `/run/dbus/system_bus_socket:/run/dbus/system_bus_socket` (BlueZ dependency)
- **Driver:** `biba-controller/bms/daly.py` (`DalyBMSBle`), `biba-controller/bms/poller.py` (`BMSPoller`)

### I2C — ADS1115 Current Sense ADC (optional)
- **Bus:** I2C bus 1 (default), `IMU_I2C_BUS`
- **Address:** `0x48` (`MOTOR_CURRENT_SENSE_I2C_ADDRESS`)
- **Channels:** 4 single-ended (ch0=right fwd, ch1=right rev, ch2=left fwd, ch3=left rev)
- **Sample rate:** `MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ=32.0` Hz
- **Library:** `smbus2`
- **Driver:** `biba-controller/motors/current_sense.py` (`ADS1115MotorCurrentReader`)
- **Enabled when:** `MOTOR_CURRENT_SENSE_ENABLED=1`

### I2C — IMU (optional)
- **Bus:** I2C bus 1 (default), `IMU_I2C_BUS`
- **Address:** `0x68` (`IMU_I2C_ADDRESS`)
- **Supported chips:** BMI160 / BMI166 (chip ID `0xD1` default), ST LSM6DS3 (auto-detected via WHO_AM_I register)
- **Autodetection:** `biba-controller/imu/factory.py` reads `0x0F` (LSM6DS3 WHO_AM_I) then `0x00` (BMI chip ID)
- **Library:** `smbus2`
- **Drivers:** `biba-controller/imu/bmi160.py`, `biba-controller/imu/lsm6ds3.py`
- **Sample rate:** `IMU_SAMPLE_RATE_HZ=100.0` Hz
- **Enabled when:** `IMU_ENABLED=1`

### SPI — STM32F103 companion link (optional)
- **Bus/device:** SPI0, CE0 (`STM32_LINK_SPI_BUS=0`, `STM32_LINK_SPI_DEVICE=0`)
- **Speed:** 8 MHz (`STM32_LINK_SPI_SPEED_HZ`)
- **Mode:** CPOL=0, CPHA=0 (Mode 0)
- **Library:** `spidev` (lazy import, only when `STM32_LINK_ENABLED=1`)
- **Protocol:** `biba_proto` — 64-byte full-duplex frames, CRC-16/CCITT-FALSE
  - Sync: `0xBA 0xBB`, version byte, cmd/tlm byte, seq, flags, payload_len, reserved, 54-byte payload, 2-byte CRC
  - Commands: `PING`, `SET_SETPOINT`, `GET_TELEMETRY`, `ARM`, `DISARM`, `SET_CONFIG`, `SET_MOTOR_AUDIO`
  - Flags: `FAILSAFE`, `ARMED`, `CRSF_ALIVE`, `CURRENT_LIMIT`, `POWER_LIMIT`
- **Python side:** `biba-controller/stm32_link/client.py` (`STM32Link`), `biba-controller/stm32_link/protocol.py`
- **Firmware side:** `firmware/src/proto/biba_proto.h`, `firmware/src/proto/biba_proto.c`

## Radio / Control Protocols

### ExpressLRS / CRSF
- **Radio system:** ExpressLRS (ELRS v3)
- **Protocol:** CRSF (Crossfire Serial Protocol) over UART
- **Channel data:** 16 channels, 11-bit values (172–1811), packed 22-byte payload
- **Frame rate:** ~50 Hz (determined by transmitter)
- **Failsafe timeout:** `FAILSAFE_TIMEOUT_S=0.5` s
- **Channel assignments (defaults):**
  - CH1: Throttle, CH3: Steering, CH4: Arm, CH5: Speed mode, CH6: Drive mode
  - CH7: Beacon toggle, CH8: Melody/Trim, CH9: Mute
- **Lua telemetry screen:** `lua/elrsV3.lua`, `lua/SCRIPTS/` — custom ELRS telemetry widget
- **Receiver code:** `biba-controller/crsf/receiver.py`, `biba-controller/crsf/protocol.py`

### Daly BMS Protocol
- **Protocol:** Proprietary Daly serial protocol over UART or BLE GATT
- **Poll interval:** `BMS_POLL_INTERVAL_S=1.0` s
- **Data retrieved:** voltage, current, SoC, per-cell voltages, temperatures
- **Thresholds:** `LOW_CELL_VOLTAGE=3.5` V, `LOW_PACK_VOLTAGE=21.0` V (6S pack)
- **Telemetry forwarded:** Battery data → CRSF telemetry battery frame → transmitter display

### biba_proto SPI Wire Protocol
- **Spec:** `firmware/src/proto/biba_proto.h` (C) ↔ `biba-controller/stm32_link/protocol.py` (Python)
- **Frame:** 64 bytes fixed-size, full-duplex exchange per transaction
- **CRC:** CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect)
- **Cross-validated:** Python and C implementations share test vectors; CI catches drift

## External Services

### GitHub Container Registry (GHCR)
- **Registry:** `ghcr.io/goodworkrinkz/biba/`
- **Images:**
  - `biba-controller:<tag>` — Python controller + pigpio
  - `biba-ros2-zenoh:<tag>` — ROS2 Humble + Zenoh base
  - `biba-ros2-control:<tag>` — adds ros2_control, diff_drive, twist_mux
  - `biba-ros2:<tag>` — full ROS2 stack with colcon-built workspace
- **Auth:** GHCR_TOKEN / `GITHUB_TOKEN` via GitHub Actions secrets

### GitHub Actions CI
- **Workflows:** `.github/workflows/G-Build-All.yml` (orchestrator), individual build workflows
- **Build platform:** `ubuntu-latest` with QEMU for `linux/arm64` cross-compilation
- **No external test services** — all tests run natively or in Docker

### No cloud APIs or webhooks
The robot operates fully offline. No REST APIs, no telemetry uploads, no cloud dependencies at runtime.

## Internal Service Boundaries

### Legacy Composition A (`docker/legacy-pi/docker-compose.yml`)
Single container `biba-controller`:
- Owns all hardware: `/dev/ttyS0` (CRSF), `/dev/ttyUSB0` (BMS UART), GPIO, D-Bus (BLE)
- Exposes HTTP API on port `8765` for web settings UI (`biba-controller/web/`)
- Main loop at `MAIN_LOOP_HZ=50` Hz: CRSF → decode → drive mix → motor PWM → BMS poll → voice/synth
- Threads: main control loop (sync), BMS poller (daemon thread), motor test API server (`ThreadingHTTPServer`), STM32 link (if enabled)

### ROS2 Composition C (`docker/ros2/docker-compose.yml`)
Three services, mutually exclusive with legacy (both claim SPI/GPIO):

| Service | Image | What it does |
|---------|-------|--------------|
| `zenoh-router` | `biba-ros2-zenoh` | DDS discovery bootstrap via `rmw_zenoh_cpp` |
| `biba-control` | `biba-ros2` | `controller_manager` + `diff_drive_controller` via `biba_hardware_stm32` SystemInterface; owns `/dev/spidev0.0`; publishes `/odom`, `/joint_states`, `/tf` |
| `twist-mux` | `biba-ros2` | Arbitrates `cmd_vel_teleop`, `cmd_vel_uwb`, `cmd_vel_nav` → `/cmd_vel`; respects `/biba/estop` lock |

### ROS2 Topics & Services
- `/cmd_vel` (sub, `geometry_msgs/Twist`) — diff_drive_controller input (from twist-mux)
- `cmd_vel_teleop`, `cmd_vel_uwb`, `cmd_vel_nav` — prioritized twist-mux inputs
- `/biba/estop` (sub, `std_msgs/Bool`) — emergency stop lock
- `/odom` (pub, `nav_msgs/Odometry`) — open-loop odometry
- `/joint_states` (pub, `sensor_msgs/JointState`) — wheel joint states
- `/tf` — `odom → base_link → wheels/imu/stm32` (RSP + diff_drive)
- `/controller_manager/*` — standard ros2_control management services

### Custom ROS2 Messages (`biba_msgs`)
- `CrsfStatus` — CRSF link status
- `Stm32Telemetry` — SPI telemetry snapshot from STM32
- Motor audio messages
- IDL in `ros2_ws/src/biba_msgs/`, built with `rosidl_default_generators`

### HTTP Settings API (legacy controller)
- **Endpoint:** `http://<robot>:8765/`
- **Server:** Python stdlib `ThreadingHTTPServer` (`biba-controller/motor_test_api.py`)
- **Routes:** `/api/settings`, `/api/settings/pid-tuning`, `/api/settings/motor-trim`, `/api/settings/motor-test`
- **Static assets:** `biba-controller/web/settings.html`, `settings.css`, `settings.js`, `biba-neon-sign.svg`
- **UI language:** Russian

### STM32 Firmware Modes
The firmware supports three compile-time modes (defined via `-DBIBA_MODE_*` build flags):
- **Standalone:** STM32 drives motors directly from CRSF input (no Pi dependency)
- **Companion:** STM32 acts as SPI slave coprocessor; Pi is master; `biba_proto` protocol
- **Combined:** Both CRSF decode and SPI slave active simultaneously

### Persistent Storage
- **Docker volume:** `biba-controller-data` → `/data` inside container
- `/data/motor-trim.json` — persisted trim offset (JSON, atomic write via temp-then-rename)
- `/data/pid-tuning.json` — persisted PID tuning overrides
- `/data/current-trace.jsonl` — rolling motor current log (when `MOTOR_CURRENT_TRACE_ENABLED=1`)
- Written by: `biba-controller/settings_store.py`, `biba-controller/pid_tuning.py`, `biba-controller/motors/current_sense.py`
