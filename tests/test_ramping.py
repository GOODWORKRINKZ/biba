"""Tests for motor command ramping and signal filtering."""

from __future__ import annotations

import pytest

from motors.ramping import ScalarKalmanFilter, SpeedRamp


DT = 0.02  # 50 Hz control loop tick


class TestDeadband:
    def test_small_target_zeroed(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.05)
        result = ramp.update(0.03, DT)
        assert result == 0.0

    def test_negative_small_target_zeroed(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.05)
        result = ramp.update(-0.04, DT)
        assert result == 0.0

    def test_above_deadband_not_zeroed(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.05)
        result = ramp.update(0.1, DT)
        assert result > 0.0

    def test_value_effectively_on_deadband_boundary_is_not_zeroed(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.05)
        target = 0.25 - 0.20  # float result may be 0.04999999999999999
        result = ramp.update(target, DT)
        assert result > 0.0


class TestAcceleration:
    def test_ramps_up_from_zero(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)
        result = ramp.update(1.0, DT)
        # max accel step = 2.0 * 0.02 = 0.04
        assert result == pytest.approx(0.04)

    def test_reaches_target_and_stays(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=100.0, deadband=0.0)
        result = ramp.update(0.5, DT)
        # 100.0 * 0.02 = 2.0 step, target is 0.5 — clamp to target
        assert result == pytest.approx(0.5)
        # Calling again stays at target
        result2 = ramp.update(0.5, DT)
        assert result2 == pytest.approx(0.5)

    def test_negative_acceleration(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)
        result = ramp.update(-1.0, DT)
        assert result == pytest.approx(-0.04)

    def test_multiple_steps_accumulate(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)
        for _ in range(5):
            result = ramp.update(1.0, DT)
        # 5 * 0.04 = 0.20
        assert result == pytest.approx(0.20)


class TestDeceleration:
    def test_decelerates_toward_lower_target(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=3.0, deadband=0.0)
        # Jump to 1.0
        ramp.update(1.0, DT)
        # Now decel toward 0.0
        result = ramp.update(0.0, DT)
        # max decel step = 3.0 * 0.02 = 0.06
        assert result == pytest.approx(1.0 - 0.06)

    def test_decelerates_negative_toward_zero(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=3.0, deadband=0.0)
        ramp.update(-1.0, DT)
        result = ramp.update(0.0, DT)
        assert result == pytest.approx(-1.0 + 0.06)

    def test_does_not_overshoot_target_on_decel(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=100.0, deadband=0.0)
        ramp.update(0.5, DT)
        # Huge decel rate, target is 0.3 — should not go below 0.3
        result = ramp.update(0.3, DT)
        assert result == pytest.approx(0.3)


class TestDirectionChange:
    def test_forces_decel_to_zero_before_reversing(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=3.0, reverse_decel_rate=1.0, deadband=0.0)
        ramp.update(1.0, DT)  # Now at 1.0
        # Request reverse: must decel toward 0 first
        result = ramp.update(-1.0, DT)
        # Should decel by reverse rate 0.02, not the normal 0.06
        assert result == pytest.approx(1.0 - 0.02)
        assert result > 0.0  # Still positive, haven't crossed zero

    def test_reaches_zero_then_accelerates_in_new_direction(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=100.0, deadband=0.0)
        ramp.update(0.1, 1.0)  # Jump to 0.1 (accel step = 2.0)
        # Huge decel rate, will reach 0 immediately
        result = ramp.update(-1.0, DT)
        # Decel to 0, then accel in negative: 0 - 0.04 = -0.04
        # Actually: at 0.1, decel_step = 100*0.02 = 2.0, clamps to 0
        # Then from 0, accel_step = 2.0*0.02 = 0.04 in negative dir
        # But the algorithm should decel to 0 in one step and NOT start accel
        # in the same step — zero is the gate between directions
        assert result == 0.0

    def test_full_reversal_through_zero(self) -> None:
        ramp = SpeedRamp(accel_rate=5.0, decel_rate=5.0, deadband=0.0)
        # Accelerate to 0.5 (5 * 0.02 = 0.1 per step, 5 steps)
        for _ in range(5):
            ramp.update(1.0, DT)

        # Now at 0.5, request -1.0
        values = []
        for _ in range(20):
            v = ramp.update(-1.0, DT)
            values.append(v)

        # Must pass through zero
        signs = [v > 0 for v in values if v != 0.0]
        assert True in signs and False in signs  # Had positive and negative

        # Verify zero was hit
        assert any(v == 0.0 for v in values)

    def test_negative_to_positive_direction_change(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=3.0, reverse_decel_rate=1.0, deadband=0.0)
        ramp.update(-1.0, DT)  # Now at -1.0
        result = ramp.update(1.0, DT)
        # Must decel toward 0 (increase toward 0 from negative)
        assert result == pytest.approx(-1.0 + 0.02)
        assert result < 0.0  # Still negative

    def test_direction_change_uses_normal_decel_when_reverse_rate_not_set(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=3.0, deadband=0.0)
        ramp.update(1.0, DT)

        result = ramp.update(-1.0, DT)

        assert result == pytest.approx(1.0 - 0.06)


class TestReset:
    def test_reset_sets_current_to_zero(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=100.0, deadband=0.0)
        ramp.update(1.0, DT)
        ramp.reset()
        assert ramp.current == 0.0

    def test_after_reset_ramps_from_zero(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)
        ramp.update(1.0, DT)  # at 0.04
        ramp.reset()
        result = ramp.update(1.0, DT)
        assert result == pytest.approx(0.04)  # starts from zero again


class TestEdgeCases:
    def test_zero_dt_returns_current(self) -> None:
        ramp = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)
        ramp.update(1.0, DT)  # at 0.04
        result = ramp.update(1.0, 0.0)
        assert result == pytest.approx(0.04)  # no change

    def test_output_clamped_to_minus_one_to_one(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=100.0, deadband=0.0)
        result = ramp.update(5.0, 1.0)
        assert result == pytest.approx(1.0)
        result = ramp.update(-5.0, 1.0)
        # From 1.0 to -5.0: decel to 0 first
        # decel step = 100 * 1.0 = 100, clamps to 0
        assert result == 0.0

    def test_dt_independence_same_total_change(self) -> None:
        """Two ramps with different dt but same total time reach same value."""
        ramp_fast = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)
        ramp_slow = SpeedRamp(accel_rate=2.0, decel_rate=3.0, deadband=0.0)

        # 10 ticks at 0.02s = 0.2s total
        for _ in range(10):
            ramp_fast.update(1.0, 0.02)

        # 20 ticks at 0.01s = 0.2s total
        for _ in range(20):
            ramp_slow.update(1.0, 0.01)

        assert ramp_fast.current == pytest.approx(ramp_slow.current, abs=1e-9)

    def test_already_at_target_no_change(self) -> None:
        ramp = SpeedRamp(accel_rate=100.0, decel_rate=100.0, deadband=0.0)
        ramp.update(0.5, DT)
        result = ramp.update(0.5, DT)
        assert result == pytest.approx(0.5)


class TestScalarKalmanFilter:
    def test_smooths_single_reverse_spike_after_forward_motion(self) -> None:
        filt = ScalarKalmanFilter(process_noise=0.02, measurement_noise=0.5)

        for _ in range(3):
            filt.update(1.0)

        result = filt.update(-1.0)

        assert result > 0.0

    def test_converges_to_new_direction_over_multiple_updates(self) -> None:
        filt = ScalarKalmanFilter(process_noise=0.02, measurement_noise=0.5)

        for _ in range(5):
            filt.update(1.0)

        for _ in range(20):
            result = filt.update(-1.0)

        assert result < -0.9

    def test_reset_clears_estimate_and_covariance(self) -> None:
        filt = ScalarKalmanFilter(process_noise=0.02, measurement_noise=0.5)
        filt.update(1.0)

        filt.reset()

        assert filt.current == 0.0
        assert filt.update(0.0) == pytest.approx(0.0)
