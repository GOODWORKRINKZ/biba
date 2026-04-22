# STM32F103 Firmware Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a separate PlatformIO STM32F103 firmware project, shared SPI protocol definitions, host-side firmware tests, optional Python SPI link scaffolding, firmware docs, and a dedicated CI workflow without breaking the current Raspberry Pi controller path.

**Architecture:** Keep the new firmware fully isolated under `firmware/`, implement shared protocol and control logic in hardware-agnostic C modules that can be exercised by `native_test`, and keep board-specific STM32Cube/HAL code as thin wrappers behind internal interfaces. On the Linux side, add a minimal `biba-controller/stm32_link/` package that mirrors the protocol, stays off by default behind a feature flag, and coexists with the existing GPIO/motor runtime.

**Tech Stack:** PlatformIO, STM32Cube HAL, C11, Unity test framework through PlatformIO `native`, Python 3, pytest, GitHub Actions.

---

### Task 1: Create the STM32 project skeleton and build matrix

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/platformio.ini`
- Create: `/home/runner/work/biba/biba/firmware/include/biba_board.h`
- Create: `/home/runner/work/biba/biba/firmware/include/biba_config.h`
- Create: `/home/runner/work/biba/biba/firmware/include/biba_version.h`
- Create: `/home/runner/work/biba/biba/firmware/src/main.c`
- Create: `/home/runner/work/biba/biba/firmware/src/modes/mode_dispatcher.c`
- Create: `/home/runner/work/biba/biba/firmware/src/modes/mode_dispatcher.h`

**Step 1: Write the failing build skeleton**

Create the directory tree and `platformio.ini` with four envs:

- `standalone`
- `companion`
- `combined`
- `native_test`

Set:

- `platform = ststm32`
- `board = bluepill_f103c8`
- `framework = stm32cube`
- `upload_protocol = stlink`
- `debug_tool = stlink`
- per-env `build_flags` for `BIBA_MODE_STANDALONE`, `BIBA_MODE_COMPANION`, `BIBA_MODE_COMBINED`

**Step 2: Run build to verify it fails in a useful way**

Run: `cd /home/runner/work/biba/biba/firmware && pio run -e standalone`
Expected: FAIL because source modules referenced by `main.c` and the dispatcher do not exist yet.

**Step 3: Write minimal implementation**

Add:

- board pin macros matching the agreed STM32F103 mapping
- protocol/config/version constants
- a `main.c` entrypoint that calls `biba_mode_dispatcher_boot()` and `biba_mode_dispatcher_run_forever()`
- a dispatcher stub that compiles for all three firmware envs

**Step 4: Run build to verify it passes**

Run: `cd /home/runner/work/biba/biba/firmware && pio run -e standalone -e companion -e combined`
Expected: PASS for all three envs.

### Task 2: Add shared protocol framing and native tests first

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/src/proto/biba_proto.h`
- Create: `/home/runner/work/biba/biba/firmware/src/proto/biba_proto.c`
- Create: `/home/runner/work/biba/biba/firmware/test/test_biba_proto/test_main.c`

**Step 1: Write the failing test**

Add native tests covering:

- CRC16/CCITT known vectors
- encode/decode of a 64-byte command frame
- sync/version rejection
- payload length bounds
- sequence echo behavior for telemetry replies

**Step 2: Run test to verify it fails**

Run: `cd /home/runner/work/biba/biba/firmware && pio test -e native_test -f test_biba_proto`
Expected: FAIL because protocol functions are missing.

**Step 3: Write minimal implementation**

Implement:

- fixed frame size constants
- `biba_proto_crc16_ccitt()`
- `biba_proto_build_command_frame()`
- `biba_proto_build_telemetry_frame()`
- `biba_proto_parse_frame()`
- enums for `PING`, `SET_SETPOINT`, `GET_TELEMETRY`, `ARM`, `DISARM`, `PLAY_TONE`

**Step 4: Run test to verify it passes**

Run: `cd /home/runner/work/biba/biba/firmware && pio test -e native_test -f test_biba_proto`
Expected: PASS.

### Task 3: Add control math modules behind host-side tests

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/src/app/control_loop.h`
- Create: `/home/runner/work/biba/biba/firmware/src/app/control_loop.c`
- Create: `/home/runner/work/biba/biba/firmware/src/app/failsafe.h`
- Create: `/home/runner/work/biba/biba/firmware/src/app/failsafe.c`
- Create: `/home/runner/work/biba/biba/firmware/test/test_control_loop/test_main.c`

**Step 1: Write the failing test**

Add native tests for:

- independent current limiting per motor
- power limiting using measured battery voltage and fallback voltage
- heading-hold PID clamping
- companion SPI link timeout forcing zero setpoints
- standalone CRSF timeout forcing disarm-safe outputs

**Step 2: Run test to verify it fails**

Run: `cd /home/runner/work/biba/biba/firmware && pio test -e native_test -f test_control_loop`
Expected: FAIL because the limiter, PID, and failsafe code does not exist.

**Step 3: Write minimal implementation**

Implement:

- plain C structs for setpoints, IMU feedback, current samples, and control outputs
- limiter logic equivalent to `/home/runner/work/biba/biba/biba-controller/motors/current_control.py`
- heading-hold PID state with reset-on-disarm
- failsafe helpers for CRSF timeout and SPI timeout

**Step 4: Run test to verify it passes**

Run: `cd /home/runner/work/biba/biba/firmware && pio test -e native_test -f test_control_loop`
Expected: PASS.

### Task 4: Add CRSF parser coverage before firmware-side integration

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/crsf.h`
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/crsf.c`
- Create: `/home/runner/work/biba/biba/firmware/test/test_crsf/test_main.c`

**Step 1: Write the failing test**

Add tests for:

- CRC8 validation
- packed RC channel unpacking
- noise skipping in a byte stream
- stale/incomplete frame rejection
- extraction of link statistics fields needed for telemetry

Use `/home/runner/work/biba/biba/tests/test_crsf.py` as the behavior reference.

**Step 2: Run test to verify it fails**

Run: `cd /home/runner/work/biba/biba/firmware && pio test -e native_test -f test_crsf`
Expected: FAIL because the parser module is missing.

**Step 3: Write minimal implementation**

Implement:

- byte-buffer frame extraction
- CRC8 DVB-S2
- 16-channel RC payload unpacking
- link stats snapshot parsing for RSSI/LQ/SNR fields

**Step 4: Run test to verify it passes**

Run: `cd /home/runner/work/biba/biba/firmware && pio test -e native_test -f test_crsf`
Expected: PASS.

### Task 5: Add the HAL and driver seams needed for all firmware envs to compile

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_clock.c`
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_gpio.c`
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_pwm.c`
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_adc.c`
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_spi_slave.c`
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_i2c.c`
- Create: `/home/runner/work/biba/biba/firmware/src/hal/biba_hal_usart.c`
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/bts7960.c`
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/current_sense.c`
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/voltage_sense.c`
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/imu.c`
- Create: `/home/runner/work/biba/biba/firmware/src/drivers/buzzer_motor.c`

**Step 1: Write the compile target**

Wire these files into the STM32 envs and make the dispatcher depend on them.

**Step 2: Run build to verify it fails**

Run: `cd /home/runner/work/biba/biba/firmware && pio run -e standalone`
Expected: FAIL on missing HAL symbols and incomplete init paths.

**Step 3: Write minimal implementation**

Implement thin HAL wrappers only:

- AFIO/JTAG remap release
- TIM1 PWM init for PA8/PA9/PA10/PA11
- GPIO enable lines on PB3/PB4/PB5/PB8
- ADC1 circular scan buffers for PA0..PA6
- SPI2 slave DMA buffers on PB12..PB15 plus PA12 data-ready line
- USART3 DMA RX/TX for CRSF
- I2C1 init for PB6/PB7

Keep sensor and actuator drivers as small stateful wrappers over the HAL functions so `native_test` stays independent from STM32 headers.

**Step 4: Run build to verify it passes**

Run: `cd /home/runner/work/biba/biba/firmware && pio run -e standalone -e companion -e combined`
Expected: PASS.

### Task 6: Implement mode-specific runtime glue

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/src/modes/mode_standalone.c`
- Create: `/home/runner/work/biba/biba/firmware/src/modes/mode_companion.c`
- Modify: `/home/runner/work/biba/biba/firmware/src/modes/mode_dispatcher.c`
- Create: `/home/runner/work/biba/biba/firmware/src/app/telemetry.h`
- Create: `/home/runner/work/biba/biba/firmware/src/app/telemetry.c`

**Step 1: Add failing native coverage where practical**

Add tests asserting:

- `combined` selects standalone or companion mode based on `MODE_SEL`
- standalone mode prefers CRSF setpoints
- companion mode prefers SPI setpoints and times out safely
- telemetry snapshots carry setpoint echo, currents, voltages, IMU, and CRSF status flags

**Step 2: Run tests/builds to verify gaps**

Run:

- `cd /home/runner/work/biba/biba/firmware && pio test -e native_test`
- `cd /home/runner/work/biba/biba/firmware && pio run -e combined`

Expected: FAIL because runtime glue is incomplete.

**Step 3: Write minimal implementation**

Implement a cooperative super-loop with:

- boot-time mode selection
- periodic ADC/IMU/CRSF polling
- per-mode setpoint ownership
- unified telemetry snapshot generation
- data-ready pulse when a fresh telemetry frame is published

**Step 4: Run tests/builds to verify they pass**

Run:

- `cd /home/runner/work/biba/biba/firmware && pio test -e native_test`
- `cd /home/runner/work/biba/biba/firmware && pio run -e standalone -e companion -e combined`

Expected: PASS.

### Task 7: Add the optional Python STM32 SPI link package

**Files:**
- Create: `/home/runner/work/biba/biba/biba-controller/stm32_link/__init__.py`
- Create: `/home/runner/work/biba/biba/biba-controller/stm32_link/protocol.py`
- Create: `/home/runner/work/biba/biba/biba-controller/stm32_link/client.py`
- Create: `/home/runner/work/biba/biba/tests/test_stm32_link_protocol.py`
- Create: `/home/runner/work/biba/biba/tests/test_stm32_link_client.py`
- Modify: `/home/runner/work/biba/biba/biba-controller/config.py`
- Modify: `/home/runner/work/biba/biba/tests/test_config.py`
- Modify: `/home/runner/work/biba/biba/biba-controller/requirements.txt`

**Step 1: Write the failing Python tests**

Add tests covering:

- CRC16 parity with the firmware protocol
- frame encode/decode round-trips
- optional feature flag defaults staying disabled
- client handling of missing `spidev`
- client exchange returning parsed telemetry snapshots

**Step 2: Run tests to verify they fail**

Run: `cd /home/runner/work/biba/biba && pytest tests/test_stm32_link_protocol.py tests/test_stm32_link_client.py tests/test_config.py -q`
Expected: FAIL because the package and config fields do not exist.

**Step 3: Write minimal implementation**

Add:

- `STM32_LINK_ENABLED=0` and SPI device/bus/speed config defaults
- pure-Python protocol mirror matching `biba_proto.h`
- a minimal client wrapper that imports `spidev` lazily and raises a clear runtime error when unavailable

Only add the package dependency that is strictly required for the optional client.

**Step 4: Check new dependency safety before keeping it**

Run the advisory check for the exact added package version.

**Step 5: Run tests to verify they pass**

Run: `cd /home/runner/work/biba/biba && pytest tests/test_stm32_link_protocol.py tests/test_stm32_link_client.py tests/test_config.py -q`
Expected: PASS.

### Task 8: Document the new hardware path and firmware architecture

**Files:**
- Create: `/home/runner/work/biba/biba/firmware/README.md`
- Create: `/home/runner/work/biba/biba/docs/stm32_architecture.md`
- Modify: `/home/runner/work/biba/biba/docs/wiring.md`
- Modify: `/home/runner/work/biba/biba/README.md`

**Step 1: Document firmware usage**

Add:

- how to build each PlatformIO env
- how to flash with ST-Link
- what `standalone`, `companion`, and `combined` mean
- what is covered by host-side tests vs hardware validation

**Step 2: Document wiring and protocol**

Add:

- the STM32F103 pin table
- Pi companion vs no-Pi integration variants
- SPI frame layout
- data flow and block diagram description

**Step 3: Verify docs reference the current controller defaults**

Cross-check the calibration, current limit, and IMU terminology against:

- `/home/runner/work/biba/biba/biba-controller/config.py`
- `/home/runner/work/biba/biba/docs/wiring.md`

### Task 9: Add a dedicated GitHub Actions workflow for firmware

**Files:**
- Create: `/home/runner/work/biba/biba/.github/workflows/G-Build-STM32-Firmware.yml`

**Step 1: Write the workflow**

Add a workflow that:

- runs on push to `main` and `workflow_dispatch`
- installs PlatformIO
- runs `pio run -e standalone`
- runs `pio run -e companion`
- runs `pio run -e combined`
- runs `pio test -e native_test`
- uploads `.bin` and `.elf` artifacts for each firmware env

**Step 2: Validate workflow syntax locally**

Run a YAML sanity check through the existing test/lint path or repository tooling already in use.

**Step 3: Verify it does not modify the current build workflows**

Keep `/home/runner/work/biba/biba/.github/workflows/G-Build-All.yml` and `/home/runner/work/biba/biba/.github/workflows/G-Build-Controller-Image.yml` untouched.

### Task 10: Update ignores and final verification

**Files:**
- Modify: `/home/runner/work/biba/biba/.gitignore`

**Step 1: Add firmware local build ignores**

Add:

- `firmware/.pio/`
- `firmware/.vscode/`

**Step 2: Run focused firmware and Python verification**

Run:

- `cd /home/runner/work/biba/biba/firmware && pio test -e native_test`
- `cd /home/runner/work/biba/biba/firmware && pio run -e standalone -e companion -e combined`
- `cd /home/runner/work/biba/biba && pytest tests/test_stm32_link_protocol.py tests/test_stm32_link_client.py tests/test_config.py tests/test_current_control.py tests/test_crsf.py -q`

Expected: PASS.

**Step 3: Run the full repository checks already used here**

Run:

- `cd /home/runner/work/biba/biba && ruff check .`
- `cd /home/runner/work/biba/biba && pytest -q`

Expected: PASS, or existing unrelated failures documented separately before merge.

**Step 4: Run PR validation**

After committing the implementation, run the parallel validation tool with a PR summary covering:

- new STM32 firmware project
- new Python SPI link scaffolding
- docs and workflow additions

### Task 11: Hardware follow-up checklist after merge candidate build

**Files:**
- No source changes expected

**Step 1: Flash standalone firmware**

Run: `cd /home/runner/work/biba/biba/firmware && pio run -e standalone -t upload`

Verify:

- ST-Link flash succeeds
- CRSF input is received
- PWM appears on TIM1 outputs
- ADC scans report sane voltage/current values

**Step 2: Flash companion or combined firmware**

Run: `cd /home/runner/work/biba/biba/firmware && pio run -e combined -t upload`

Verify:

- boot-time mode selection follows `MODE_SEL`
- SPI heartbeat works with the Pi
- telemetry echo matches the last setpoint frame
- timeout safety drops outputs to zero when SPI stops

**Step 3: Calibrate current sense**

Compare:

- STM32 ADC-derived BTS7960 current readings
- existing ADS1115 readings from the Pi path

Expected: same trend and acceptable calibration agreement on the same hardware.
