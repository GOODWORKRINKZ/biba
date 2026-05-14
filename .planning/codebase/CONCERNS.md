---
doc: CONCERNS
last_mapped: 2026-05-14
---

# Technical Concerns

## Critical / High Priority

### Unauthenticated Motor Control HTTP API

- **Risk:** `MOTOR_TEST_API_HOST` defaults to `0.0.0.0` (`biba-controller/config.py:184`). The `ThreadingHTTPServer` in `biba-controller/motor_test_api.py:777` has no authentication, CORS restrictions, or IP allowlist. Anyone on the same network can POST to `/api/motor-test` and spin motors regardless of arm state.
- **Impact:** Safety hazard — remote motor actuation without operator intent. Especially critical when the robot is powered but disarmed and within reach.
- **Fix approach:** Restrict `MOTOR_TEST_API_HOST` default to `127.0.0.1` for field deployments, or add a token-based auth header check in `MotorTestRequestHandler.do_POST`. At minimum, document this as requiring a trusted-network firewall rule.

### Failsafe is Pure-Python / Soft-Timed

- **Risk:** `DifferentialDrive.check_failsafe()` (`biba-controller/motors/driver.py:345`) fires only when the main loop calls it. If the main loop is stalled — e.g., during a slow BMS BLE poll, ADS1115 I2C busy-wait, or file I/O — the failsafe timeout (`FAILSAFE_TIMEOUT_S=0.5s`) will not be respected.
- **Impact:** Runaway robot on link loss. The STM32 firmware (`firmware/`) has a hardware failsafe, but that path is only active in composition B/C. In composition A (Pi-only), failsafe is fully at Python's mercy.
- **Fix approach:** Move the motor stop call to a watchdog thread separate from the main loop; or implement a hardware timeout via the STM32 companion once composition C is stable.

### BMS Failure Silent During Operation

- **Risk:** `BMSPoller._run()` (`biba-controller/bms/poller.py:60`) catches `Exception`, logs a warning, sets `_state = None`, and continues polling. The main loop then falls back to `MOTOR_LIMIT_FALLBACK_VOLTAGE=24.0V` for current limiting. A real battery fault (cell imbalance, overcurrent) could be missed indefinitely if BMS comms drop.
- **Impact:** No low-voltage cutoff; potential battery damage or fire risk.
- **Fix approach:** Add a BMS-stale counter; after N consecutive failures trigger a voice alarm and (when armed) a gradual power reduction or disarm.

### Legacy and ROS2 Stacks Are Mutually Exclusive but Not Enforced

- **Risk:** `docker/legacy-pi/` (composition A) and `docker/ros2/` (composition C) both claim SPI/GPIO ownership. The docs (`docs/ros2_stack.md`) note they are mutually exclusive, but there is no startup guard preventing both from running simultaneously on the same Pi.
- **Impact:** SPI bus contention, GPIO conflicts, motor runaway if both stacks start.
- **Fix approach:** Add a lockfile or systemd `ConditionPathExists` guard to prevent simultaneous stack activation.

---

## Technical Debt

### `main.py` God-File (1929 lines)

- **Files:** `biba-controller/main.py`
- **Issue:** The entire robot control loop, signal handling, motor test executor, PID update logic, voice/audio playback dispatch, BMS telemetry encoding, and motor current tracing all live in one file. The `main()` function itself runs hundreds of lines inline.
- **Impact:** High cognitive load for contributors; hard to unit-test the inner loop without importing the full module; regressions in one subsystem are invisible across the file.
- **Fix approach:** Extract the main loop body into a `ControlLoop` class; move BMS/telemetry encode helpers into `crsf/telemetry.py`; move audio dispatch helpers into a `buzzer/dispatcher.py`. Do not split speculatively — extract only when a subsystem is being modified.

### HTML/JS Embedded as Python String Literals

- **Files:** `biba-controller/motor_test_api.py` (lines 140–550 approximately)
- **Issue:** `build_control_page()` and `build_pid_tuning_page()` produce full HTML pages by string interpolation inside Python. The `_WEB_ASSET_DIR` path exists (`biba-controller/web/`) and is used for settings assets, but the motor-test and PID pages are still inline.
- **Impact:** Syntax errors in HTML/JS are silent at Python load time; no IDE support for the embedded markup; difficult to extend.
- **Fix approach:** Move motor-test and PID HTML into `biba-controller/web/` as static files, loaded the same way as `settings.html`.

### Runtime Reflection API Compatibility Checks

- **Files:** `biba-controller/main.py` (functions `_supports_kwarg`, `_supports_positional_argument`)
- **Issue:** `_supports_kwarg` and `_supports_positional_argument` use `inspect.signature` to check whether the codebase's own functions accept certain arguments at runtime. These checks exist because the codebase was refactored incrementally and the function signatures changed over time.
- **Impact:** If a function is renamed or its signature changes, the fallback branch silently applies the wrong behavior. This is a form of API versioning debt that bypasses Python's own static type system.
- **Fix approach:** Remove the reflection checks once the signatures are stable; the current function `_create_assisted_drive_controller` always accepts `snapshot`.

### `STM32_LINK_ENABLED` Defaults to `0` — Code Always Dormant

- **Files:** `biba-controller/stm32_link/`, `biba-controller/config.py:162`
- **Issue:** The entire `stm32_link/` module (~200 lines) is dead code in production. The SPI bridge design (`docs/plans/2026-04-28-biba-hardware-stm32.md`) assigns SPI ownership to the C++ `ros2_control` plugin (composition C), making the Python SPI client architecturally obsolete for the new stack.
- **Impact:** Confusion about which code path to extend; maintenance overhead.
- **Fix approach:** Keep for composition A fallback experimentation; add a clear comment in `config.py` flagging the module as composition-C-deprecated once the hardware plugin is stable.

### BLE BMS Reconnect Not Implemented

- **Files:** `biba-controller/bms/daly.py` (`DalyBMSBle.close`, `_send_command`)
- **Issue:** If BLE drops mid-session, `self._client` becomes `None`. `_send_command` raises `RuntimeError("DalyBMSBle client is not connected")`, which `BMSPoller` catches and logs. The poller continues calling `read_state()` but every call immediately raises — no reconnect attempt is made.
- **Impact:** After a BLE dropout, BMS data is permanently unavailable until process restart; low-voltage detection stops working.
- **Fix approach:** Add a reconnect retry in `BMSPoller._run()` with exponential backoff; or expose a `reconnect()` method on `DalyBMSBle`.

---

## Security

### HTTP Motor API with No Authentication (see Critical section)

- **Files:** `biba-controller/motor_test_api.py`, `biba-controller/config.py:184`
- **Risk:** Open by default on all interfaces.
- **Current mitigation:** None. The service is enabled by default (`MOTOR_TEST_API_ENABLED=1`).

### No HTTPS / TLS on Settings UI

- **Files:** `biba-controller/motor_test_api.py` (`ThreadingHTTPServer`)
- **Risk:** PID parameters and motor-trim values are transmitted in cleartext. If the robot's Wi-Fi is ever shared with untrusted devices, passive sniffing can reveal configuration.
- **Current mitigation:** Robot typically on isolated Wi-Fi or hotspot.
- **Recommendation:** Add an optional TLS wrapper or restrict UI to localhost-only in production profiles.

### Pickle / YAML Deserialisation Scope

- **Files:** `biba-controller/main.py` (`_load_voice_audition_candidates`), `biba-controller/pid_tuning.py`, `biba-controller/settings_store.py`
- **Risk:** `yaml.safe_load` is used correctly. JSON files (`motor-trim.json`, `pid-tuning.json`) are parsed with `json.loads` — no arbitrary code execution risk. YAML audition manifest uses `safe_load`. No unsafe deserialisation detected.
- **Status:** No actionable issue; recorded for completeness.

---

## Performance

### ADS1115 Blocking I2C Busy-Wait in Main Loop

- **Files:** `biba-controller/motors/current_sense.py` (`_wait_for_conversion`, lines ~210–220)
- **Problem:** `_wait_for_conversion` busy-polls the I2C config register with `time.sleep(poll_interval)` inside the main loop thread. At 32 SPS the conversion timeout is `max(2/32, 0.01) = 62.5 ms`. If the ADC conversion stalls, the main loop can miss the CRSF frame deadline.
- **Impact:** Increased loop jitter; worst-case failsafe latency exceeds `FAILSAFE_TIMEOUT_S`.
- **Fix approach:** Move current sensing to a background thread (similar to `BMSPoller`) and expose latest values non-blockingly.

### Motor Current Trace I/O at Full Loop Rate

- **Files:** `biba-controller/main.py` (`_append_jsonl_record`, enabled by `MOTOR_CURRENT_TRACE_ENABLED`)
- **Problem:** When `MOTOR_CURRENT_TRACE_ENABLED=1`, `_append_jsonl_record` opens, writes, and flushes a JSONL file every loop tick (up to 50 Hz). On an SD-card-backed Pi Zero 2W, this causes significant write amplification and blocking I/O.
- **Impact:** Loop jitter, SD card wear, eventual SD failure.
- **Fix approach:** Buffer trace records in memory and flush in batches from a background writer thread; or write to a tmpfs path and rsync periodically.

### Pi Zero 2W Resource Budget Pressure

- **Context:** Pi Zero 2W (1 GB RAM, 4× Cortex-A53 1 GHz). Running Docker + pigpiod + Python controller + BLE stack + optional voice playback.
- **Known tight areas:** Spectral voice playback (`biba-controller/buzzer/wav_player.py`) loads PCM into memory; at 50 Hz control loop + BLE + Docker overhead the CPU can approach 100%.
- **Fix approach:** Profile with `py-spy` during a full-load run to identify the dominant CPU consumer before adding new subsystems.

### BMS BLE Timeout Propagates to Background Thread

- **Files:** `biba-controller/bms/daly.py` (`DalyBMSBle._send_command`, `BMS_BLE_TIMEOUT_S=1.5`)
- **Problem:** Each BLE command waits up to 1.5 s. Multiple commands per `read_state()` call (SOC + cell voltages + temperatures) can take up to ~5 s total at worst. While this runs in `BMSPoller`'s background thread, it blocks that thread from yielding the next poll — causing BMS data to go stale for multiple seconds.
- **Impact:** Late low-voltage detection.
- **Fix approach:** Use a shorter per-command timeout and add a per-`read_state()` deadline.

---

## Fragile Areas

### `bms/daly.py` `get_cell_voltages()` Unbounded Loop

- **Files:** `biba-controller/bms/daly.py` (line ~310 in `DalyBMSBle.get_cell_voltages()`)
- **Why fragile:** The BLE variant uses `while len(cells) < 6:` and breaks only when `_send_command` returns `None` or `_extract_cell_values` returns nothing. If the BMS firmware sends continuous valid responses that pass checksum but contain only zeroes (filtered out by `if value > 0` in `_extract_cell_values`), the loop never accumulates 6 cells and never breaks via the empty-frame path — it relies on the BLE timeout eventually returning `None`.
- **Safe modification:** Add an explicit iteration cap (`max_attempts = 10`).

### BLE Client's Async Event Loop in a Daemon Thread

- **Files:** `biba-controller/bms/daly.py` (`_BleakClientAdapter`)
- **Why fragile:** `_BleakClientAdapter` creates a new `asyncio` event loop in a daemon thread. If `future.result(timeout=10.0)` in `_run_coroutine` times out, the future is abandoned but the coroutine may still be running in the loop — leading to resource leaks and undefined state. The `disconnect()` path calls `loop.stop()` after a 1.0 s join timeout with no guarantee the loop fully stopped.
- **Impact:** Memory/handle leaks on repeated BLE reconnects; hard to reproduce in tests.

### IMU `open_imu_reader` Double-Raises Without Closing Bus

- **Files:** `biba-controller/imu/factory.py:53`
- **Why fragile:** `open_imu_reader` opens `SMBus(bus_index)`, then wraps the body in `try/except Exception: close_fn(); raise`. However, `detect_imu_kind` itself raises a bare `ValueError` (not an `Exception` subclass issue — `ValueError` IS a subclass, so it is caught). The close happens correctly, but if `SMBus.__init__` itself raises, the `close_fn = getattr(bus, "close", None)` line has already executed on an uninitialized object. Low risk but fragile.

### `_create_test_motor_synth` Uses `getattr` Duck-Typing

- **Files:** `biba-controller/main.py` (`_create_test_motor_synth`)
- **Why fragile:** Uses `getattr(buzzer, "pi", ...)`, `getattr(buzzer, "pwm_pins", ...)`, etc., to reconstruct a `MotorSynth` from an existing instance's internal attributes. If `MotorSynth`'s `__init__` signature or private attributes change, this silently returns `None` and the motor-test PWM-mode switch stops working.

### Voice Thread Lifecycle Unmanaged

- **Files:** `biba-controller/main.py` (various `threading.Thread(target=player, daemon=True).start()` calls)
- **Why fragile:** Voice playback threads are spawned as bare daemon threads with no handle retained. If playback blocks (e.g., pigpio `wave_send_once` hangs), the thread accumulates without bound. No join or cancellation mechanism exists.

---

## TODOs & FIXMEs

No `TODO` / `FIXME` / `HACK` markers found in production Python source (`biba-controller/`, `ros2_ws/src/`).

**Pending design-level work tracked in docs:**

- `docs/plans/2026-04-28-sbc-architecture-redesign-design.md` — Split SPI ownership between Python bridge and C++ `ros2_control` plugin. Composition C with a single Pi running both stacks simultaneously is explicitly documented as "separate epic" and not yet implemented.
- `docs/plans/2026-04-28-biba-hardware-stm32.md` (Phase 8a) — `spi_owner` flag-gated transition. Still incomplete.
- `docs/plans/2026-03-31-biba-synth-redesign-design.md` — Legacy shared-channel synth fallback paths not yet removed from `MotorSynth`.

---

## Hardware-Level Concerns

### BTS7960 Thermal Runaway / Overheating

- **Risk:** BTS7960 motor driver boards overheat after ~20–30 minutes of sustained operation → wheel dropout (motors stop responding). One driver was burned in March 2026 and required replacement.
- **Code surface:** `biba-controller/motors/driver.py` (`BTS7960MotorDriver`), `biba-controller/motors/current_control.py`. Current limiting (`MOTOR_CURRENT_LIMITING_ENABLED`) is disabled by default — thermal throttling is not implemented.
- **Proposed fix:** Mount drivers on metal heatsink with waterproofing; enable `MOTOR_CURRENT_LIMITING_ENABLED=1` with calibrated `LEFT/RIGHT_MOTOR_MAX_CURRENT_A` to reduce sustained load; add temperature monitoring if a thermistor can be wired to an ADC channel.

### Battery Selection Unresolved

- **Risk:** Drone LiPo batteries don't fit the chassis. No confirmed battery form factor as of 2026-05-14.
- **Code surface:** `biba-controller/config.py` (`LOW_CELL_VOLTAGE=3.5`, `LOW_PACK_VOLTAGE=21.0`) — these thresholds are tuned for a 6S LiPo; if a different cell count is used the low-voltage alarm will trigger at the wrong point.
- **Recommendation:** Parameterise cell count and per-cell thresholds separately; validate against chosen pack.

### Pi Zero 2W Resource Constraints

- **Risk:** The Pi Zero 2W (1 GB RAM, 4× Cortex-A53 1 GHz) is the sole CPU for Docker daemon, pigpiod, Python control loop, BLE stack, voice rendering, and the HTTP settings UI. Adding ROS2 nodes (composition C) to this board is explicitly flagged as "minimal profile only" in `docs/system_architecture.md`.
- **Code surface:** All of `biba-controller/` runs on this hardware.
- **Scaling path:** Pi 4/5 or Radxa CM5 for composition C. Pi Zero 2W stays composition-A-only.

### STM32 SPI Bridge Communication Complexity

- **Risk:** The SPI bridge (composition C) adds a frame-level protocol (`biba-controller/stm32_link/protocol.py`) between Pi and STM32. Any firmware/software version mismatch in the proto definition silently drops frames or corrupts setpoints. The Python SPI client is dormant (`STM32_LINK_ENABLED=0`); the C++ hardware plugin (`ros2_ws/src/biba_hardware_stm32/`) is the active path.
- **Code surface:** `biba-controller/stm32_link/protocol.py`, `firmware/src/`.
- **Mitigation:** `protocol.py` includes a CRC check; add proto version handshake to detect firmware/driver mismatch at startup.

### RP2040 Branch Divergence

- **Risk:** A `rp2040-port` branch exists (separate from `main`). As `main` evolves (new protocol fields, new config keys), the RP2040 port silently diverges. There is no CI job that builds or tests the RP2040 branch against the current protocol.
- **Impact:** RP2040 port may become unbuildable or behaviorally incompatible without warning.
- **Fix approach:** Add a CI workflow that builds the RP2040 firmware and runs the `firmware/test/` suite against it; or formally deprecate the branch if the hardware target is abandoned.

### ELRS/CRSF Failsafe Reliability (Soft-Timed, see Critical section)

- **Risk:** The only hardware-independent safety net on link loss in composition A is the 0.5 s Python polling timeout. See "Failsafe is Pure-Python / Soft-Timed" above.
- **Code surface:** `biba-controller/motors/driver.py:345`, `biba-controller/config.py:97`.

### Docker Stack Startup Overhead on Embedded Hardware

- **Risk:** Cold-boot time for the Docker stack (`docker/legacy-pi/`) on a Pi Zero 2W is measured in tens of seconds. During this window motors are uncontrolled and the CRSF receiver is not yet open. If power is applied while the transmitter is already live, the robot is briefly unresponsive without any indication.
- **Code surface:** `docker/legacy-pi/docker-compose.yml`.
- **Fix approach:** Add a startup indicator (LED or buzzer) driven by a lightweight non-Docker script that fires as soon as the Pi boots, before Docker comes up.

---

*Concerns audit: 2026-05-14*
