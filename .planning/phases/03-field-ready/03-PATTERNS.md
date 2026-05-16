# Phase 3: Field Ready - Pattern Map

**Mapped:** 2026-05-16
**Files analyzed:** 17
**Analogs found:** 15 / 17

## File Classification

| New/Modified File or Area | Role | Data Flow | Closest Analog | Match Quality |
| --- | --- | --- | --- | --- |
| `firmware/src/drivers/bts7960.c` | utility | request-response | `firmware/src/drivers/bts7960.c` | exact |
| `firmware/src/modes/mode_standalone.c` | controller | event-driven | `firmware/src/modes/mode_standalone.c` | exact |
| `firmware/src/hal/biba_hal_rp2040.c` | utility | request-response | `firmware/src/hal/biba_hal_rp2040.c` | exact |
| `biba-controller/motors/driver.py` | utility | request-response | `biba-controller/motors/driver.py` | exact |
| `biba-controller/main.py` | controller | event-driven | `biba-controller/main.py` | exact |
| `biba-controller/motors/current_control.py` | utility | transform | `biba-controller/motors/current_control.py` | exact |
| `tests/test_motors.py` | test | request-response | `tests/test_motors.py` | exact |
| `tests/test_current_control.py` | test | transform | `tests/test_current_control.py` | exact |
| `tests/test_main.py` | test | event-driven | `tests/test_main.py` | exact |
| `docs/variants.md` (new, inferred) | documentation | batch | `README.md` + `docs/system_architecture.md` + `docs/deployment.md` + `firmware/targets/*/target.md` | composite |
| `docs/wiring.md` | documentation | batch | `docs/wiring.md` | exact |
| `docs/deployment.md` | documentation | batch | `docs/deployment.md` | exact |
| `docs/field-validation.md` (new, inferred) | documentation | batch | `docs/plans/2026-03-30-current-sense-calibration-trace-design.md` + `docs/telemetry-investigation-2026-03-28.md` | composite |
| `artifacts/current-trace/` | artifact | file-I/O | current-trace JSONL flow in `biba-controller/main.py` | role-match |
| `artifacts/telemetry-captures/` | artifact | streaming | `scripts/vcp_capture.py` + existing `artifacts/telemetry-captures/vcp-*.log` | exact |
| `scripts/vcp_capture.py` | utility | streaming | `scripts/vcp_capture.py` | exact |
| `tests/test_vcp_capture.py` | test | streaming | `tests/test_vcp_capture.py` | exact |

## Pattern Assignments

### `firmware/src/drivers/bts7960.c` (utility, request-response)

**Analog:** `firmware/src/drivers/bts7960.c`

**Imports pattern** (`firmware/src/drivers/bts7960.c:1-4`):
```c
#include "bts7960.h"

#include "hal/biba_hal.h"
#include "biba_config.h"
```

**Enable owner pattern** (`firmware/src/drivers/bts7960.c:6-14`):
```c
void biba_bts7960_set_enabled(bool enabled)
{
    biba_hal_left_enable(enabled);
    biba_hal_right_enable(enabled);
    if (!enabled) {
        biba_hal_motor_pwm_left(0.0f);
        biba_hal_motor_pwm_right(0.0f);
    }
}
```

**Drive pattern** (`firmware/src/drivers/bts7960.c:16-20`):
```c
void biba_bts7960_drive(float left_duty, float right_duty)
{
    biba_hal_motor_pwm_left( left_duty  * BIBA_LEFT_MOTOR_DIR);
    biba_hal_motor_pwm_right(right_duty * BIBA_RIGHT_MOTOR_DIR);
}
```

**Planner guidance:** Put the Phase 3 thermal-reset primitive here, not inline in the mode loop. This file already owns the zero-PWM invariant when enable goes LOW.

---

### `firmware/src/modes/mode_standalone.c` (controller, event-driven)

**Analog:** `firmware/src/modes/mode_standalone.c`

**Arm-init hook pattern** (`firmware/src/modes/mode_standalone.c:157-169`):
```c
void biba_mode_standalone_init(void)
{
    biba_hal_crsf_begin(BIBA_CRSF_BAUD);
    biba_failsafe_init(&s_crsf_failsafe, BIBA_CRSF_TIMEOUT_MS);
    biba_pid_reset(&s_heading_pid);
    s_last_tick_ms = biba_hal_now_ms();
    biba_bts7960_set_enabled(true);
```

**Arm/disarm edge pattern** (`firmware/src/modes/mode_standalone.c:241-267`):
```c
bool armed = (!failsafe) && (arm_ch > BIBA_ARM_THRESHOLD);

if (failsafe && !s_last_failsafe) {
    biba_melody_player_start(&s_player, &biba_melody_failsafe);
    biba_ramp_reset(&s_ramp_left);
    biba_ramp_reset(&s_ramp_right);
    biba_hal_ssr_set(false);
}

if (armed && !s_armed) {
    printf("[biba] ARMED\r\n");
    biba_melody_player_start(&s_player, &biba_melody_arm);
} else if (!armed && s_armed) {
    printf("[biba] DISARMED\r\n");
    biba_pid_reset(&s_heading_pid);
    ...
    biba_ramp_reset(&s_ramp_left);
    biba_ramp_reset(&s_ramp_right);
}
s_armed = armed;
biba_hal_ssr_set(armed);
```

**Current-limit and output pipeline** (`firmware/src/modes/mode_standalone.c:371-410`):
```c
/* Mix -> current limiter -> trim -> drive */
if (armed) {
    biba_mix_output_t mix = biba_mix_differential(throttle, steering);

    biba_motor_current_t il = biba_current_sense_left();
    biba_motor_current_t ir = biba_current_sense_right();
    biba_motor_limit_t lim = {
        .current_limit_a  = BIBA_LEFT_MAX_CURRENT_A,
        .power_limit_w    = BIBA_LEFT_MAX_POWER_W,
        .supply_voltage_v = BIBA_FALLBACK_SUPPLY_V,
    };
    biba_motor_limit_t rim = {
        .current_limit_a  = BIBA_RIGHT_MAX_CURRENT_A,
        .power_limit_w    = BIBA_RIGHT_MAX_POWER_W,
        .supply_voltage_v = BIBA_FALLBACK_SUPPLY_V,
    };
    biba_limit_result_t out = biba_apply_motor_limits(mix.left, mix.right, il, ir, lim, rim);
    left_out  = out.left;
    right_out = out.right;

    if (trim > 0.0f) {
        right_out *= (1.0f - trim);
    } else if (trim < 0.0f) {
        left_out *= (1.0f + trim);
    }
}

left_out  = biba_ramp_update(&s_ramp_left,  left_out,  dt);
right_out = biba_ramp_update(&s_ramp_right, right_out, dt);
```

**Telemetry flagging pattern** (`firmware/src/modes/mode_standalone.c:483-500`):
```c
.error_flags = (failsafe      ? BIBA_PROTO_FLAG_FAILSAFE      : 0u)
              | (failsafe      ? 0u : BIBA_PROTO_FLAG_CRSF_ALIVE)
              | (!armed        ? BIBA_PROTO_FLAG_FAILSAFE       : 0u)
              | (left_limited || right_limited
                               ? BIBA_PROTO_FLAG_CURRENT_LIMIT  : 0u),
```

**Planner guidance:** The arm/disarm state machine should trigger the reset primitive on the arm edge, but the GPIO pulse itself should stay in the driver/HAL owner. This file is the right place for the timing decision and any post-enable guard.

---

### `firmware/src/hal/biba_hal_rp2040.c` (utility, request-response)

**Analog:** `firmware/src/hal/biba_hal_rp2040.c`

**Boot-safe enable initialization** (`firmware/src/hal/biba_hal_rp2040.c:102-118`):
```c
void biba_hal_init(void)
{
    ...
    const uint en_pins[] = {
        BIBA_PIN_LEFT_REN_GPIO, BIBA_PIN_LEFT_LEN_GPIO,
        BIBA_PIN_RIGHT_REN_GPIO, BIBA_PIN_RIGHT_LEN_GPIO,
    };
    for (unsigned i = 0; i < 4u; i++) {
        gpio_init(en_pins[i]);
        gpio_set_dir(en_pins[i], GPIO_OUT);
        gpio_put(en_pins[i], 0);
    }
```

**Per-side enable API pattern** (`firmware/src/hal/biba_hal_rp2040.c:249-260`):
```c
void biba_hal_left_enable(bool enabled)
{
    gpio_put(BIBA_PIN_LEFT_REN_GPIO, enabled ? 1u : 0u);
    gpio_put(BIBA_PIN_LEFT_LEN_GPIO, enabled ? 1u : 0u);
}

void biba_hal_right_enable(bool enabled)
{
    gpio_put(BIBA_PIN_RIGHT_REN_GPIO, enabled ? 1u : 0u);
    gpio_put(BIBA_PIN_RIGHT_LEN_GPIO, enabled ? 1u : 0u);
}
```

**Planner guidance:** Reuse the existing per-side helpers. Do not add raw GPIO twiddling in the mode loop if the HAL already owns the enable pins.

---

### `biba-controller/motors/driver.py` (utility, request-response)

**Analog:** `biba-controller/motors/driver.py`

**Imports and driver ownership pattern** (`biba-controller/motors/driver.py:5-14`):
```python
import logging
import time

import pigpio

import config
from motors.ramping import SpeedRamp

LOGGER = logging.getLogger("biba-controller")
```

**BTS7960 init pattern** (`biba-controller/motors/driver.py:57-86`):
```python
class BTS7960MotorDriver:
    ...
    def __init__(...):
        ...
        for pin in self._unique_pins(self.ren_pin, self.len_pin):
            self.pi.set_mode(pin, pigpio.OUTPUT)

        for pin in self._unique_pins(self.ren_pin, self.len_pin):
            self.pi.write(pin, 1)

        if self._pwm_mode == "SOFTWARE":
            self._setup_software_pwm()
        else:
            self._setup_hardware_pwm()
```

**Directional PWM pattern** (`biba-controller/motors/driver.py:131-157`):
```python
def set_speed(self, value: float) -> None:
    clamped = max(-1.0, min(1.0, value))
    if self.inverted:
        clamped *= -1.0

    duty_range = self._HW_PWM_RANGE if self._pwm_mode == "HARDWARE" else self._software_pwm_range
    duty = int(abs(clamped) * duty_range)
    if clamped > 0.0:
        ...
    elif clamped < 0.0:
        ...
    else:
        self.stop()
```

**Motor factory pattern** (`biba-controller/main.py:636-654`):
```python
if config.MOTOR_DRIVER_TYPE == "BTS7960":
    left_motor = BTS7960MotorDriver(...)
    right_motor = BTS7960MotorDriver(...)
    return left_motor, right_motor
```

**Planner guidance:** For any Pi-side mirrored Phase 3 work, keep the reset primitive on the driver class and let `main.py` call it on arm. Preserve the `_unique_pins()` shared-enable behavior.

---

### `tests/test_motors.py` (test, request-response)

**Analog:** `tests/test_motors.py`

**Fake GPIO owner pattern** (`tests/test_motors.py:10-39`):
```python
class FakePi:
    def __init__(self) -> None:
        self.mode_calls: list[tuple[int, int]] = []
        self.frequency_calls: list[tuple[int, int]] = []
        self.hardware_pwm_calls: list[tuple[int, int, int]] = []
        self.write_calls: list[tuple[int, int]] = []
        self.duty_calls: list[tuple[int, int]] = []
```

**Enable-line init assertions** (`tests/test_motors.py:85-94`):
```python
BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=24, pwm_mode="HARDWARE")

assert pi.mode_calls == [(23, 1), (24, 1)]
assert pi.hardware_pwm_calls == [(18, 20000, 0), (13, 20000, 0)]
assert pi.write_calls == [(23, 1), (24, 1)]
```

**Shared-enable regression pattern** (`tests/test_motors.py:133-139`):
```python
BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=23, pwm_mode="HARDWARE")

assert pi.mode_calls == [(23, 1)]
assert pi.write_calls == [(23, 1)]
```

**Planner guidance:** Add thermal-reset tests here first for the Python driver path: LOW pulse duration call, PWM forced to zero during reset, and shared-enable-pin behavior.

---

### `biba-controller/motors/current_control.py` (utility, transform)

**Analog:** `biba-controller/motors/current_control.py`

**Data model pattern** (`biba-controller/motors/current_control.py:8-35`):
```python
@dataclass(frozen=True)
class MotorCurrentSample:
    current_a: float | None
    valid: bool = True
    voltage_v: float | None = None
    raw_adc: int | None = None
    channel: int | None = None
```

**Throttle-back rule** (`biba-controller/motors/current_control.py:42-63`):
```python
if config.current_limit_a > 0.0 and current_a > config.current_limit_a:
    scale = min(scale, config.current_limit_a / current_a)

if config.power_limit_w > 0.0 and config.supply_voltage_v > 0.0:
    power_w = config.supply_voltage_v * current_a
    if power_w > config.power_limit_w:
        scale = min(scale, config.power_limit_w / power_w)
```

**Planner guidance:** Reuse this scale-down model for THERM-01. Do not introduce a hard-stop thermal path where the repo already uses proportional throttle-back.

---

### `biba-controller/main.py` (controller, event-driven)

**Analog:** `biba-controller/main.py`

**Current-limit adapter pattern** (`biba-controller/main.py:957-981`):
```python
if not config.MOTOR_CURRENT_LIMITING_ENABLED:
    return MotorLimitResult(...requested values...)

supply_voltage_v = _get_motor_supply_voltage(battery_state)
return apply_motor_limits(
    requested_left=requested_left,
    requested_right=requested_right,
    left_sample=left_sample,
    right_sample=right_sample,
    left_config=MotorLimitConfig(...),
    right_config=MotorLimitConfig(...),
)
```

**Trace activity gate pattern** (`biba-controller/main.py:990-1040`):
```python
if abs(raw_throttle) > config.MOTOR_DEADBAND or abs(steering) > config.MOTOR_DEADBAND:
    return True
if abs(left_duty) > 1e-6 or abs(right_duty) > 1e-6:
    return True
if _telemetry_motor_current_a(left_sample) > 0.0 or _telemetry_motor_current_a(right_sample) > 0.0:
    return True
...
if now_s - last_activity_at_s <= config.MOTOR_CURRENT_TRACE_POST_ROLL_S:
    return True, last_activity_at_s
```

**JSONL trace record pattern** (`biba-controller/main.py:1043-1124`):
```python
return {
    "session_id": session_id,
    "sample_index": sample_index,
    "monotonic_s": now_s,
    "wall_time_iso": wall_time_iso,
    "armed": armed,
    ...
    "bms_sample_monotonic_s": bms_sample_monotonic_s,
    "bms_age_s": bms_age_s,
    "mute_active": mute_active,
    "beacon_active": beacon_active,
    "trim_mode_active": trim_mode_active,
    "trace_reason": trace_reason,
}
```

**Arm/disarm transition pattern** (`biba-controller/main.py:1459-1484`):
```python
requested_armed = _is_armed(channels)
if requested_armed != armed:
    armed = requested_armed
    if armed:
        disarm_sound_after_s = None
        arm_sound_hold_until_s = loop_started_at + _ARM_SOUND_HOLD_S
        LOGGER.info("Platform armed")
        ...
    else:
        arm_sound_hold_until_s = None
        disarm_sound_after_s = loop_started_at + _DISARM_SOUND_SETTLE_S
        LOGGER.info("Platform disarmed")
```

**Planner guidance:** Any arm-edge recovery on the Python path should hook here, but keep the GPIO reset details inside `BTS7960MotorDriver`. This file is already the owner of the arm transition contract and trace windowing.

---

### `tests/test_current_control.py` and `tests/test_main.py` (tests, transform/event-driven)

**Analog:** `tests/test_current_control.py`

**Limiter test style** (`tests/test_current_control.py:8-83`):
```python
def test_apply_motor_limits_scales_each_motor_independently_for_current_limit() -> None:
    result = apply_motor_limits(...)
    assert result.left_output == pytest.approx(0.4)
    assert result.right_output == pytest.approx(0.7)
    assert result.left_limited is True
    assert result.right_limited is False
```

**Trace logging regression style** (`tests/test_main.py:3076-3105`):
```python
def test_send_battery_telemetry_emits_trace_logs_when_enabled(...):
    monkeypatch.setattr(main.config, "BMS_TELEMETRY_TRACE_ENABLED", True, raising=False)
    ...
    assert "Battery telemetry trace stage=consume t=10.000000" in caplog.text
    assert "Battery telemetry trace stage=send t=10.250000" in caplog.text
```

**Planner guidance:** Mirror this focused, narrow-test style for Phase 3. Add single-behavior tests instead of one large end-to-end thermal test.

---

### `docs/variants.md` (new, inferred; documentation, batch)

**Composite analogs:** `README.md`, `docs/system_architecture.md`, `docs/deployment.md`, `docs/wiring.md`, `firmware/targets/*/target.md`

**Top-level matrix style** (`README.md:14-21`):
```markdown
| Composition | SBC | MCU add-on | Who listens to CRSF | Compose / firmware |
| --- | --- | --- | --- | --- |
| A. Pi-only | yes | no | Pi | docker/legacy-pi/docker-compose.yml |
| B. STM32-only | no | STM32F103 | STM32 | firmware env standalone |
| C. Pi + STM32 | yes | STM32F103 | STM32 | firmware env companion + docker/ros2 |
| D. RP2040-only | no | RP2040 | RP2040 | firmware env rpico_rp2040_standalone |
```

**Canonical ownership style** (`docs/system_architecture.md:15-27`):
```markdown
The project supports multiple hardware compositions at once.
Where STM32 exists, CRSF UART terminates there.
Pi-only reads CRSF itself.
```

**Reproducibility-link style** (`docs/deployment.md:11-13`, `docs/deployment.md:67-86`):
```markdown
Working stack: docker/legacy-pi/docker-compose.yml
Operational path: bbupdate / bbstart / bbstop / bblogs
```

**Low-level pin/source-of-truth style** (`docs/wiring.md:3-27`):
```markdown
## Raspberry Pi Zero 2W pinout
... RPWM / LPWM / REN / LEN table ...
... BTS7960_PWM_MODE=SOFTWARE note for current wiring ...
```

**Per-target implementation-card style** (`firmware/targets/RPICO_RP2040/target.md:39-89`, `firmware/targets/BLUEPILL_F103C8/target.md:19-40`, `firmware/targets/BIBA_F103_REV_A/target.md:36-66`):
```markdown
- target card owns board-specific pin map
- target card owns build env names
- target card owns variant-specific electrical notes
```

**Planner guidance:** Make `docs/variants.md` the only status matrix. Other docs should link to it rather than duplicate statuses. Fill each row from existing truth sources: `README.md` for composition names, `docs/system_architecture.md` for control ownership, `docs/deployment.md` for Pi reproducibility, and `firmware/targets/*/target.md` for firmware variants.

---

### `docs/field-validation.md` and artifact areas (new/inferred; documentation + artifact, batch/file-I/O)

**Composite analogs:** `docs/plans/2026-03-30-current-sense-calibration-trace-design.md`, `biba-controller/main.py`, `scripts/vcp_capture.py`, `docs/telemetry-investigation-2026-03-28.md`, `artifacts/current-trace/`, `artifacts/telemetry-captures/`

**Trace gate and JSONL format** (`docs/plans/2026-03-30-current-sense-calibration-trace-design.md:35-56`, `docs/plans/2026-03-30-current-sense-calibration-trace-design.md:105-148`):
```markdown
- gate logging on armed + motor activity or post-roll
- write one JSON object per line
- record BMS freshness explicitly
- keep post-roll to catch delayed BMS decay
```

**Implemented trace writer** (`biba-controller/main.py:1008-1124`):
```python
trace_enabled, last_activity_at_s = _update_motor_current_trace_window(...)
record = _build_motor_current_trace_record(...)
_append_jsonl_record(config.MOTOR_CURRENT_TRACE_PATH, record)
```

**VCP capture naming pattern** (`scripts/vcp_capture.py:18-23`, `scripts/vcp_capture.py:27-50`):
```python
def default_output_path(...) -> Path:
    return Path("artifacts/telemetry-captures") / f"vcp-{moment.strftime('%Y%m%d-%H%M%S')}.log"

output.write(format_log_line(payload, moment, epoch_fn()))
```

**Evidence interpretation pattern** (`docs/telemetry-investigation-2026-03-28.md:43-72`):
```markdown
- compare transmitter-visible and robot-visible plateaus
- normalize timestamps first
- match plateau shapes, not individual sparse samples
- avoid exact latency claims from coarse robot logs
```

**Existing artifact examples:**
- `artifacts/current-trace/robot-stand-tremor-2026-04-06.log`
- `artifacts/telemetry-captures/vcp-20260328-214454.log`
- `artifacts/telemetry-captures/vcp-20260328-215311.log`

**Planner guidance:** The Phase 3 field-validation package should follow the same split: machine-readable captures in artifact directories, then one human-readable report that references those files and states the acceptance result.

---

### `tests/test_vcp_capture.py` (test, streaming)

**Analog:** `tests/test_vcp_capture.py`

**Timestamped-stream test pattern** (`tests/test_vcp_capture.py:21-77`):
```python
def test_format_log_line_prefixes_wall_time_and_epoch() -> None:
    ...

def test_capture_stream_writes_timestamped_lines() -> None:
    ...

def test_default_output_path_targets_telemetry_capture_dir() -> None:
    ...
```

**Planner guidance:** Reuse this style for any new capture helper or field-validation evidence utility: deterministic clocks, in-memory fake readers, path assertions.

## Shared Patterns

### Driver/HAL Owns Enable Pins
**Sources:** `firmware/src/drivers/bts7960.c:6-14`, `firmware/src/hal/biba_hal_rp2040.c:102-118`, `biba-controller/motors/driver.py:77-86`
**Apply to:** All BTS7960 thermal-reset implementation slices

```text
Higher-level control code decides when recovery happens.
Driver/HAL code owns how enable pins and PWM are manipulated.
```

### Zero-PWM While Disabled
**Sources:** `firmware/src/drivers/bts7960.c:10-12`, `firmware/src/modes/mode_standalone.c:371-410`
**Apply to:** Thermal reset, disarm, and failed recovery handling

```text
Whenever enable goes LOW, force PWM to zero first or in the same primitive.
Do not allow stale duty to survive the reset pulse.
```

### Throttle-Back, Not Hard Stop
**Sources:** `biba-controller/motors/current_control.py:42-63`, `biba-controller/main.py:957-981`, `firmware/src/modes/mode_standalone.c:377-404`
**Apply to:** THERM-01 planning and validation

```text
Scale requested outputs proportionally when current/power thresholds are exceeded.
Keep per-motor limiting independent.
```

### Fail-Open Invalid Current Samples
**Sources:** `biba-controller/motors/current_control.py:46-47`, `tests/test_current_control.py:76-83`
**Apply to:** Current limiting and evidence collection

```text
If a current sample is invalid or missing, preserve requested output and mark it un-limited rather than inventing a value.
```

### Documentation Ownership Split
**Sources:** `docs/wiring.md:3-27`, `README.md:14-23`, `docs/system_architecture.md:15-27`, `docs/deployment.md:11-13`, `firmware/targets/*/target.md`
**Apply to:** Variant matrix and hardware ownership docs

```text
- wiring.md and target.md own pin truth
- README.md owns high-level composition summary
- system_architecture.md owns control-owner semantics
- deployment.md owns reproducible run/build links
- variants.md should aggregate and backlink, not fork the truth
```

### Evidence Artifacts Are Split Into Raw Capture + Report
**Sources:** `biba-controller/main.py:1043-1124`, `scripts/vcp_capture.py:18-50`, `docs/telemetry-investigation-2026-03-28.md:43-72`
**Apply to:** Field validation and thermal evidence collection

```text
- raw JSONL/current traces in artifact directories
- raw VCP logs in artifacts/telemetry-captures/
- human summary report in docs/
```

## No Exact Analog Found

Files or artifacts the planner should treat as composition work rather than copy-paste from one existing file:

| File | Role | Data Flow | Reason |
| --- | --- | --- | --- |
| `docs/variants.md` | documentation | batch | The repo has matrix inputs spread across `README.md`, `docs/system_architecture.md`, `docs/deployment.md`, and `firmware/targets/*/target.md`, but no single canonical status matrix yet. |
| `docs/field-validation.md` | documentation | batch | The repo has raw evidence patterns and one historical investigation report, but no canonical Phase 3 field-validation checklist/report template yet. |

## Metadata

**Analog search scope:** `biba-controller/`, `firmware/`, `docs/`, `scripts/`, `tests/`, `artifacts/`
**Files scanned:** 21
**Pattern extraction date:** 2026-05-16
