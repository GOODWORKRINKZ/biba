"""Current-limit helpers for per-motor protection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotorCurrentSample:
    """Latest current reading for one motor."""

    current_a: float | None
    valid: bool = True
    voltage_v: float | None = None
    raw_adc: int | None = None
    channel: int | None = None


@dataclass(frozen=True)
class MotorLimitConfig:
    """Protection thresholds for one motor."""

    current_limit_a: float
    power_limit_w: float
    supply_voltage_v: float


@dataclass(frozen=True)
class MotorLimitResult:
    """Limiter outputs for both motors."""

    left_output: float
    right_output: float
    left_limited: bool
    right_limited: bool


def _clamp_output(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _limit_motor_output(requested: float, sample: MotorCurrentSample, config: MotorLimitConfig) -> tuple[float, bool]:
    output = _clamp_output(requested)
    if output == 0.0:
        return 0.0, False
    if not sample.valid or sample.current_a is None:
        return output, False

    current_a = max(0.0, sample.current_a)
    scale = 1.0

    if config.current_limit_a > 0.0 and current_a > config.current_limit_a:
        scale = min(scale, config.current_limit_a / current_a)

    if config.power_limit_w > 0.0 and config.supply_voltage_v > 0.0:
        power_w = config.supply_voltage_v * current_a
        if power_w > config.power_limit_w:
            scale = min(scale, config.power_limit_w / power_w)

    if scale >= 1.0:
        return output, False

    return _clamp_output(output * scale), True


def apply_motor_limits(
    requested_left: float,
    requested_right: float,
    left_sample: MotorCurrentSample,
    right_sample: MotorCurrentSample,
    left_config: MotorLimitConfig,
    right_config: MotorLimitConfig,
) -> MotorLimitResult:
    """Apply independent current and power limits to each motor command."""

    left_output, left_limited = _limit_motor_output(requested_left, left_sample, left_config)
    right_output, right_limited = _limit_motor_output(requested_right, right_sample, right_config)
    return MotorLimitResult(
        left_output=left_output,
        right_output=right_output,
        left_limited=left_limited,
        right_limited=right_limited,
    )