---
doc: CONVENTIONS
last_mapped: 2026-05-14
---

# Code Conventions

## Language & Style

**Python version:** 3.10+ (cpython-310 `.pyc` in `biba-controller/__pycache__/`)

**Future annotations:** Every source file begins with `from __future__ import annotations` — enables PEP 563 deferred evaluation, allowing forward references in type hints.

**Linter:** `ruff >= 0.11` (declared in `requirements-dev.txt`). No `pyproject.toml` or `.ruff.toml` config file — ruff runs with defaults. Type ignore comments are rare: `# type: ignore import` in `stm32_link/client.py` and `# type: ignore[import]` in ROS2 bridge node.

**No formatter config found** — ruff's built-in formatter is implied.

## Naming Conventions

**Files:** `snake_case.py` — e.g., `motor_test_api.py`, `wav_player.py`, `assisted_drive.py`, `voice_selector.py`

**Modules/packages:** same `snake_case` — e.g., `biba-controller/bms/`, `biba-controller/motors/`, `biba-controller/buzzer/`

**Classes:** `PascalCase` — e.g., `BTS7960MotorDriver`, `DifferentialDrive`, `AssistedDriveController`, `BMSPoller`, `CRSFReceiver`

**Functions:** `snake_case`; private helpers prefixed with `_`  
- Public: `set_speed()`, `read_state()`, `open_imu_reader()`  
- Private: `_clamp_motor_trim()`, `_get_env_int()`, `_build_ble_client()`

**Module-level constants:**
- Public (config): `UPPER_SNAKE_CASE` — e.g., `MOTOR1_PWM`, `CRSF_PORT`, `FAILSAFE_TIMEOUT_S` in `config.py`
- Private (internal): `_UPPER_SNAKE_CASE` — e.g., `_BATTERY_TELEMETRY_LOG_INTERVAL_S`, `_ARM_SOUND_HOLD_S` in `main.py`

**Logger variable:** always named `LOGGER` (not `logger`), declared at module level immediately after imports

## Project-Specific Patterns

### `from __future__ import annotations` (universal)
Required in every production source file. Allows `X | Y` union types and `list[int]` generics in all Python 3.10+ code.

### Module-level docstring (universal)
Every `.py` module starts with a one-liner or short docstring:
```python
"""Motor driver and differential drive helpers."""
```
`biba-controller/motors/driver.py`, `biba-controller/bms/daly.py`, `biba-controller/buzzer/wav_player.py`, etc.

### `@dataclass(frozen=True)` for value objects
All result/config structs are immutable frozen dataclasses:
```python
@dataclass(frozen=True)
class AssistedDriveResult:
    throttle: float
    steering: float
    mode: DriveMode
    ...
```
Used in: `biba-controller/motors/assisted_drive.py`, `biba-controller/motors/current_control.py`, `biba-controller/motors/current_sense.py`, `biba-controller/imu/__init__.py`, `biba-controller/buzzer/motor_synth.py`, `biba-controller/crsf/telemetry.py`, `biba-controller/pid_tuning.py`

`@dataclass(slots=True)` used for mutable objects: `BatteryState` in `biba-controller/bms/daly.py`

### `typing.Protocol` for structural interfaces
Hardware dependencies are abstracted with `Protocol` rather than ABC:
```python
class BMSReader(Protocol):
    def read_state(self) -> Optional[BatteryState]: ...
```
Used in: `biba-controller/bms/poller.py` (`BMSReader`), `biba-controller/bms/daly.py` (`BleClientProtocol`)

### `_Null*` / no-op classes for hardware-absent mode
Classes with the same public interface but no-op bodies, used when hardware is unavailable:
```python
class _NullDrive:
    def mix_and_ramp(self, throttle, steering, dt=0.02) -> tuple[float, float]:
        del throttle, steering, dt
        return (0.0, 0.0)
```
Examples: `_NullDrive`, `NullIMUReader` (`biba-controller/imu/__init__.py`), `NullMotorCurrentReader` (`biba-controller/motors/current_sense.py`)

### `del` for suppressing unused arguments
When implementing a protocol method that must accept args but ignores them, use `del` instead of `_` names:
```python
def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
    del throttle, steering, dt
    return (0.0, 0.0)
```
Seen throughout `main.py` and `biba-controller/motors/current_sense.py`.

### `str(Enum)` for string enums
```python
class DriveMode(str, Enum):
    MANUAL = "manual"
    STABILIZED = "stabilized"
```
Used in `biba-controller/motors/assisted_drive.py`.

### Factory functions for complex construction
Hardware objects built via private `_create_*` functions in `main.py`:
- `_create_buzzer()`, `_create_motor_pair()`, `_create_imu_reader()`, `_create_bms()`, `_create_assisted_drive_controller()`

## Error Handling

**`ValueError`** — invalid configuration or input values at API boundaries:
```python
raise ValueError(f"Unsupported ADS1115 gain: {gain}")     # current_sense.py
raise ValueError("Packed CRSF channel payload must be at least 22 bytes")  # crsf/receiver.py
```

**`RuntimeError`** — invalid object state (e.g., using a resource before `open()`):
```python
raise RuntimeError("DalyBMS serial port is not open")  # bms/daly.py
raise RuntimeError("CRSFReceiver serial port is not open")  # crsf/receiver.py
```

**`NotImplementedError`** — abstract interface stubs:
```python
def read_sample(self) -> Optional[IMUSample]:
    raise NotImplementedError   # imu/__init__.py
```

**`OSError`** — hardware/IO failures; caught and handled silently (e.g., `system_stats.py`) or logged.

**Background thread exception handling** — broad `except Exception` is acceptable only in worker thread loops; always logs with `%s` format:
```python
except Exception as exc:
    LOGGER.warning("BMS poll failed: %s", exc)  # bms/poller.py
```

**Config parsing** — silent fallback to default, never raises:
```python
except ValueError:
    return default  # config.py _get_env_int/_get_env_float
```

## Logging

**Library:** `logging` (stdlib), no third-party logging framework.

**Logger declaration** — module-level `LOGGER` constant, immediately after imports:
```python
LOGGER = logging.getLogger("biba-controller")  # main.py, motors/driver.py, motors/current_sense.py, buzzer/beacon.py
LOGGER = logging.getLogger(__name__)            # bms/poller.py, motor_test_api.py
```
Main controller and driver code uses the named `"biba-controller"` logger. Library/utility modules use `__name__`.

**Log call format** — `%`-style format strings (not f-strings) in all LOGGER calls:
```python
LOGGER.warning("BMS poll failed: %s", exc)
LOGGER.info("Applied PID tuning revision %s", revision)
LOGGER.exception("Hardware initialization failed: %s", exc)
```

**Log levels used:**
- `LOGGER.info` — normal lifecycle events (start, state changes, applied revisions)
- `LOGGER.warning` — degraded operation, hardware unavailable, retry failures
- `LOGGER.exception` — fatal-path hardware init failures (includes traceback)
- `LOGGER.debug` — not used in current codebase

**Logging setup:** Configured via `_setup_logging()` in `main.py`; level controlled by `LOG_LEVEL` env var.

## Configuration

All runtime configuration lives in `biba-controller/config.py`. Config values are module-level constants loaded from environment variables via private helpers:

```python
MOTOR1_PWM = _get_env_int("MOTOR1_PWM", 18)
BMS_TRANSPORT = _get_env_choice("BMS_TRANSPORT", "BLE", {"UART", "BLE"})
CRSF_PORT = os.getenv("CRSF_PORT", "/dev/ttyS0")
```

**Helpers in `config.py`:**
- `_get_env_int(name, default)` — int with silent fallback
- `_get_env_float(name, default)` — float with silent fallback
- `_get_env_choice(name, default, choices)` — enum-like string with validation
- `_get_env_list(name, default)` — semicolon-separated list

**Access pattern:** `import config` then `config.MOTOR1_PWM` — always imported as module, never `from config import *`. Config module is hot-reloadable via `importlib.reload(config)` for tests.

**No `.env` file loading** — env vars must be set externally (Docker Compose, shell). See `docker/legacy-pi/docker-compose.yml` for production env.
