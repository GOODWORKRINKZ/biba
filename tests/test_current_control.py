from __future__ import annotations

import pytest

from motors.current_control import MotorCurrentSample, MotorLimitConfig, apply_motor_limits


def test_apply_motor_limits_preserves_requested_output_when_below_limits() -> None:
    config = MotorLimitConfig(
        current_limit_a=20.0,
        power_limit_w=240.0,
        supply_voltage_v=24.0,
    )

    result = apply_motor_limits(
        requested_left=0.6,
        requested_right=-0.4,
        left_sample=MotorCurrentSample(current_a=5.0),
        right_sample=MotorCurrentSample(current_a=4.0),
        left_config=config,
        right_config=config,
    )

    assert result.left_output == pytest.approx(0.6)
    assert result.right_output == pytest.approx(-0.4)
    assert result.left_limited is False
    assert result.right_limited is False


def test_apply_motor_limits_scales_each_motor_independently_for_current_limit() -> None:
    result = apply_motor_limits(
        requested_left=0.8,
        requested_right=0.7,
        left_sample=MotorCurrentSample(current_a=24.0),
        right_sample=MotorCurrentSample(current_a=10.0),
        left_config=MotorLimitConfig(current_limit_a=12.0, power_limit_w=400.0, supply_voltage_v=24.0),
        right_config=MotorLimitConfig(current_limit_a=12.0, power_limit_w=400.0, supply_voltage_v=24.0),
    )

    assert result.left_output == pytest.approx(0.4)
    assert result.right_output == pytest.approx(0.7)
    assert result.left_limited is True
    assert result.right_limited is False


def test_apply_motor_limits_scales_by_power_using_measured_supply_voltage() -> None:
    result = apply_motor_limits(
        requested_left=-0.9,
        requested_right=0.2,
        left_sample=MotorCurrentSample(current_a=10.0),
        right_sample=MotorCurrentSample(current_a=3.0),
        left_config=MotorLimitConfig(current_limit_a=30.0, power_limit_w=120.0, supply_voltage_v=30.0),
        right_config=MotorLimitConfig(current_limit_a=30.0, power_limit_w=120.0, supply_voltage_v=30.0),
    )

    assert result.left_output == pytest.approx(-0.36)
    assert result.right_output == pytest.approx(0.2)
    assert result.left_limited is True
    assert result.right_limited is False


def test_apply_motor_limits_uses_fallback_voltage_when_sample_has_no_voltage() -> None:
    result = apply_motor_limits(
        requested_left=0.5,
        requested_right=0.0,
        left_sample=MotorCurrentSample(current_a=8.0),
        right_sample=MotorCurrentSample(current_a=0.0),
        left_config=MotorLimitConfig(current_limit_a=20.0, power_limit_w=80.0, supply_voltage_v=20.0),
        right_config=MotorLimitConfig(current_limit_a=20.0, power_limit_w=80.0, supply_voltage_v=20.0),
    )

    assert result.left_output == pytest.approx(0.25)
    assert result.left_limited is True


def test_apply_motor_limits_fails_open_for_invalid_samples() -> None:
    result = apply_motor_limits(
        requested_left=0.9,
        requested_right=-0.9,
        left_sample=MotorCurrentSample(current_a=None, valid=False),
        right_sample=MotorCurrentSample(current_a=None, valid=False),
        left_config=MotorLimitConfig(current_limit_a=5.0, power_limit_w=50.0, supply_voltage_v=24.0),
        right_config=MotorLimitConfig(current_limit_a=5.0, power_limit_w=50.0, supply_voltage_v=24.0),
    )

    assert result.left_output == pytest.approx(0.9)
    assert result.right_output == pytest.approx(-0.9)
    assert result.left_limited is False
    assert result.right_limited is False