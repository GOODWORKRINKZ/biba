---
doc: TESTING
last_mapped: 2026-05-14
---

# Testing

## Framework & Tools

**Runner:** pytest >= 8, < 9 (declared in `requirements-dev.txt`)  
**Config:** `pytest.ini` at repo root — `testpaths = tests`

**Dev dependencies** (`requirements-dev.txt`):
- `pytest >= 8, < 9`
- `ruff >= 0.11, < 1`
- `matplotlib >= 3.9, < 4` (used for audio/spectral analysis tests)
- `PyYAML >= 6, < 7` (used for ROS2 config tests)
- All of `biba-controller/requirements.txt` (runtime deps included)

**No coverage plugin configured.** No `pytest-cov`, `pytest-asyncio`, or other pytest plugins in requirements.

## Test Structure

**Location:** All tests flat in `tests/` — no sub-directories.

**Naming:** `test_<module_name>.py` mirrors source module names:
- `tests/test_motors.py` → `biba-controller/motors/driver.py`
- `tests/test_bms_poller.py` → `biba-controller/bms/poller.py`
- `tests/test_crsf.py` → `biba-controller/crsf/`
- `tests/test_config.py` → `biba-controller/config.py`
- `tests/test_main.py` → `biba-controller/main.py`

**Test function naming:** Extremely descriptive snake_case sentences:
```
test_motor_driver_initializes_pins_and_pwm
test_bts7960_motor_driver_uses_rpwm_for_forward_motion
test_is_armed_uses_configured_channel_threshold
test_poller_returns_none_before_first_poll
```

**Test organization:** Mix of styles:
- Flat functions for single-concern tests (majority pattern)
- `class Test<Topic>` grouping for related parametric cases:
  ```python
  class TestDeadband:
      def test_small_target_zeroed(self) -> None: ...
      def test_above_deadband_not_zeroed(self) -> None: ...

  class TestAcceleration:
      def test_ramps_up_from_zero(self) -> None: ...
  ```
  Used in `tests/test_ramping.py`. Not common — most tests are top-level functions.

**Type annotations:** All test functions are annotated `-> None`.

## Test Categories

### Unit / pure-logic tests
Test isolated pure functions and classes, no I/O:
- `tests/test_ramping.py` — `SpeedRamp`, `ScalarKalmanFilter` step math
- `tests/test_current_control.py` — current limiting logic
- `tests/test_assisted_drive.py` — PID steering calculations
- `tests/test_blheli_parser.py` — melody string parsing
- `tests/test_crsf.py` — CRSF frame encoding/CRC/channel normalization
- `tests/test_stm32_link_protocol.py` — SPI protocol encoding

### Hardware-mock integration tests
Test real classes with fake hardware objects:
- `tests/test_motors.py` — `MotorDriver`, `BTS7960MotorDriver`, `DifferentialDrive` with `FakePi`
- `tests/test_bms_poller.py` — `BMSPoller` threaded polling with `FakeBMS`
- `tests/test_daly.py` — Daly BMS UART with `FakeSerial`
- `tests/test_daly_ble.py` — Daly BMS BLE with `FakeBleClient`
- `tests/test_current_sense.py` — ADS1115 reader with `FakeSMBus`
- `tests/test_lsm6ds3.py`, `tests/test_bmi160.py` — IMU drivers with `FakeBus`
- `tests/test_stm32_link_client.py` — SPI client with `FakeSpi`

### Config / environment tests
Test config loading with env var manipulation:
- `tests/test_config.py` — exhaustive default-value assertions after clearing all env vars, uses `importlib.reload(config)`

### Main controller tests
Test internal `main.py` functions via module-level monkeypatching:
- `tests/test_main.py` (5475 lines — largest test file) — tests `_is_armed`, `_is_muted`, drive mode selection, voice playback logic, trim gestures, current limiting dispatch, telemetry encoding
- `tests/test_main_voice_groups.py`, `tests/test_main_voice_audition.py`

### Voice / audio tests
- `tests/test_wav_player.py` — WAV loading, spectral cache, motor playback
- `tests/test_motor_synth.py` — motor synth PWM scheduling
- `tests/test_voice_prep_*.py` — voice asset processing pipeline (4 test files)
- `tests/test_voice_selector.py` — voice file selection policy
- `tests/test_voice_spectral_cache.py` — spectral cache read/write

### ROS2 workspace structure tests
Verify ROS2 workspace shape without running ROS:
- `tests/test_ros2_ws_skeleton.py` — package.xml presence, hook points
- `tests/test_biba_description_urdf.py` — URDF links/joints
- `tests/test_biba_description_ros2_control.py` — ros2_control XML
- `tests/test_biba_bringup_control.py`, `tests/test_biba_bringup_twist_mux.py` — launch YAML structure
- `tests/test_biba_proto_drift.py` — checks vendored proto files haven't drifted

### Script tests
- `tests/test_biba_aliases.py` — shell alias file structure
- `tests/test_setup_node.py`, `tests/test_setup_node_ros2.py` — setup scripts
- `tests/test_vcp_capture.py` — VCP telemetry capture script
- `tests/test_voice_prep_*.py` — voice asset preparation scripts

## Mocking Approach

**No `unittest.mock` / `MagicMock`** — the codebase explicitly avoids it.

**Pattern: handwritten `Fake*` classes** defined at the top of each test file, implementing only the methods actually used by the code under test:

```python
class FakePi:
    def __init__(self) -> None:
        self.mode_calls: list[tuple[int, int]] = []
        self.write_calls: list[tuple[int, int]] = []
        self._real_range = 255

    def set_mode(self, pin: int, mode: int) -> None:
        self.mode_calls.append((pin, mode))

    def write(self, pin: int, value: int) -> None:
        self.write_calls.append((pin, value))
    # ... other methods
```
`tests/test_motors.py` — `FakePi` simulates `pigpio.pi`  
`tests/test_bms_poller.py` — `FakeBMS`  
`tests/test_daly.py` — `FakeSerial`  
`tests/test_daly_ble.py` — `FakeBleClient`  
`tests/test_current_sense.py` — `FakeSMBus`  
`tests/test_lsm6ds3.py`, `tests/test_bmi160.py` — `FakeBus`  
`tests/test_stm32_link_client.py` — `FakeSpi`  
`tests/test_telemetry.py` — `FakeSerial`

**Fake classes record calls as lists** for assertion: `assert pi.mode_calls == [(18, 1), (23, 1)]`

**`monkeypatch.setattr`** for patching module attributes, config values, and class members:
```python
def test_is_armed_uses_configured_channel_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "CH_ARM", 2)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.25)
```
Most heavily used in `tests/test_main.py` (~950 `monkeypatch` occurrences).

**`monkeypatch.delenv` / `monkeypatch.setenv`** — manipulating environment variables before `importlib.reload(config)` in `tests/test_config.py`.

**`pigpio` stub** — globally injected in `tests/conftest.py` so all tests can import biba-controller modules without the daemon:
```python
if "pigpio" not in sys.modules:
    sys.modules["pigpio"] = types.SimpleNamespace(OUTPUT=1, pi=object)
```

**Inline fake classes** — `FakeBuzzer`, `FakeSelector`, `FakeDrive` etc. defined inline inside test functions for single-use cases in `test_main.py`.

## Fixtures

### `tests/conftest.py`
Minimal — only performs path setup and pigpio stubbing:
```python
ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_DIR = ROOT / "biba-controller"
sys.path.insert(0, str(CONTROLLER_DIR))

sys.modules["pigpio"] = types.SimpleNamespace(OUTPUT=1, pi=object)
```
No shared test fixtures are defined in conftest.

### Per-file fixtures
Each test file defines its own local fixtures as needed:

```python
# tests/test_config.py
@pytest.fixture
def config_module():
    return importlib.import_module("config")

# tests/test_biba_bringup_twist_mux.py
@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

# tests/test_biba_description_ros2_control.py
@pytest.fixture(scope="module")
def root() -> ET.Element:
    return ET.parse(URDF_PATH).getroot()
```

### pytest built-in fixtures used
- **`monkeypatch`** — most common (950+ usages), primarily in `test_main.py` and `test_config.py`
- **`tmp_path`** — file-system tests: `test_settings_store.py`, `test_pid_tuning.py`, `test_wav_player.py` (~178 usages)

## Running Tests

```bash
# Run all tests (from repo root)
pytest

# Run all tests with verbose output
pytest -v

# Run a specific test file
pytest tests/test_motors.py

# Run a specific test
pytest tests/test_motors.py::test_motor_driver_initializes_pins_and_pwm

# Fail fast on first failure
pytest -x

# Run linter
ruff check biba-controller/

# Run tests matching a keyword
pytest -k "bms"
```

## Coverage

**No coverage enforcement configured.** No `pytest-cov` in requirements, no `[coverage]` section in `pytest.ini`.

**Observed coverage distribution:**
- `biba-controller/config.py` — thorough (exhaustive env-var defaults in `test_config.py`)
- `biba-controller/motors/` — well covered (driver, ramping, current_control, current_sense, assisted_drive all have dedicated test files)
- `biba-controller/main.py` — heavily tested via monkeypatching in `test_main.py` (5475 lines)
- `biba-controller/bms/` — covered (daly, daly_ble, poller)
- `biba-controller/crsf/` — covered (protocol, receiver)
- `biba-controller/buzzer/` — covered (wav_player, motor_synth, blheli_parser, voice_selector)
- `biba-controller/imu/` — covered (bmi160, lsm6ds3, factory)

**Gaps / low coverage areas:**
- `biba-controller/stm32_link/client.py` — hardware SPI path only partially testable without real hardware
- `biba-controller/web/` — no web tests found
- Integration/end-to-end with live pigpio daemon — excluded by design

## Common Patterns

### Float comparison
```python
assert result == pytest.approx(0.04)
assert channels[1] == pytest.approx(0.0, abs=0.001)
```
`pytest.approx` used throughout for all float assertions (~275 occurrences).

### Error testing
```python
with pytest.raises(ValueError, match="at least 22 bytes"):
    CRSFReceiver.parse_channels(b"\x00" * 21)
```

### Parametrize
```python
@pytest.mark.parametrize("pkg", CORE_PACKAGES)
def test_package_xml_exists(pkg: str) -> None: ...
```
Used in `test_ros2_ws_skeleton.py`, `test_stm32_link_protocol.py`, `test_biba_description_urdf.py`, `test_biba_proto_drift.py`.

### Real threading with deadline
For tests involving background threads (`BMSPoller`), use a real deadline loop rather than `time.sleep`:
```python
deadline = time.monotonic() + 2.0
while poller.latest_state is None and time.monotonic() < deadline:
    time.sleep(0.01)
poller.stop()
assert poller.latest_state is not None
```
`tests/test_bms_poller.py`

### Module-level import with `importlib`
For testing `main.py` (which has side effects on import), use `importlib.import_module`:
```python
main = importlib.import_module("main")
monkeypatch.setattr(main.config, "CH_ARM", 2)
```
`tests/test_main.py`, `tests/test_config.py`

### Helper factory functions
Test files define private `_make_*` functions to build test data objects:
```python
def _make_state(voltage: float = 24.0) -> BatteryState:
    return BatteryState(voltage=voltage, current=1.0, soc=80.0, ...)
```
`tests/test_bms_poller.py`, `tests/test_main.py`
