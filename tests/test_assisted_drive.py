from __future__ import annotations

import pytest

from imu import IMUSample
from motors.assisted_drive import AssistedDriveConfig, AssistedDriveController, DriveMode


def _sample(
    gyro_z_dps: float,
    *,
    valid: bool = True,
    timestamp_monotonic_s: float = 0.0,
) -> IMUSample:
    return IMUSample(
        accel_x_g=0.0,
        accel_y_g=0.0,
        accel_z_g=1.0,
        gyro_x_dps=0.0,
        gyro_y_dps=0.0,
        gyro_z_dps=gyro_z_dps,
        temperature_c=None,
        timestamp_monotonic_s=timestamp_monotonic_s,
        valid=valid,
    )


def test_manual_mode_passes_inputs_through() -> None:
    controller = AssistedDriveController(AssistedDriveConfig())

    result = controller.update(
        throttle=0.6,
        steering=0.4,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=12.0),
        dt=0.1,
        armed=True,
        now_monotonic_s=0.1,
    )

    assert result.throttle == pytest.approx(0.6)
    assert result.steering == pytest.approx(0.4)
    assert result.mode == DriveMode.MANUAL


def test_stabilized_mode_counters_uncommanded_yaw() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            yaw_rate_max_dps=90.0,
            yaw_rate_kp=0.02,
            yaw_rate_ki=0.0,
            yaw_rate_kd=0.0,
            yaw_rate_deadband_dps=0.0,
            yaw_rate_filter_hz=0.0,
        )
    )

    result = controller.update(
        throttle=0.5,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=20.0),
        dt=0.1,
        armed=True,
        now_monotonic_s=0.1,
    )

    assert result.throttle == pytest.approx(0.5)
    assert result.steering == pytest.approx(-0.4)
    assert result.imu_healthy is True
    assert result.measured_yaw_rate_dps == pytest.approx(20.0)
    assert result.desired_yaw_rate_dps == pytest.approx(0.0)


def test_stabilized_mode_ignores_small_neutral_yaw_noise() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            yaw_rate_kp=0.02,
            yaw_rate_deadband_dps=4.0,
            yaw_rate_filter_hz=0.0,
        )
    )

    result = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=3.5, timestamp_monotonic_s=0.1),
        dt=0.1,
        armed=True,
        now_monotonic_s=0.1,
    )

    assert result.measured_yaw_rate_dps == pytest.approx(0.0)
    assert result.steering == pytest.approx(0.0)


def test_stabilized_mode_filters_short_yaw_spike_but_keeps_sustained_correction() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            yaw_rate_kp=0.02,
            yaw_rate_deadband_dps=0.0,
            yaw_rate_filter_hz=5.0,
        )
    )

    first = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=20.0, timestamp_monotonic_s=0.02),
        dt=0.02,
        armed=True,
        now_monotonic_s=0.02,
    )

    sustained = first
    for step in range(2, 11):
        sustained = controller.update(
            throttle=0.0,
            steering=0.0,
            mode=DriveMode.STABILIZED,
            imu_sample=_sample(gyro_z_dps=20.0, timestamp_monotonic_s=0.02 * step),
            dt=0.02,
            armed=True,
            now_monotonic_s=0.02 * step,
        )

    assert abs(first.steering) < 0.2
    assert first.measured_yaw_rate_dps < 20.0
    assert sustained.steering < -0.35


def test_heading_hold_latches_reference_and_pushes_back_against_drift() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            yaw_rate_kp=0.02,
            heading_hold_kp=2.0,
            heading_hold_ki=0.0,
            heading_hold_kd=0.0,
            heading_hold_max_rate_dps=45.0,
            yaw_rate_deadband_dps=0.0,
            yaw_rate_filter_hz=0.0,
        )
    )

    first = controller.update(
        throttle=0.5,
        steering=0.0,
        mode=DriveMode.HEADING_HOLD,
        imu_sample=_sample(gyro_z_dps=0.0, timestamp_monotonic_s=0.0),
        dt=0.1,
        armed=True,
        now_monotonic_s=0.1,
    )
    second = controller.update(
        throttle=0.5,
        steering=0.0,
        mode=DriveMode.HEADING_HOLD,
        imu_sample=_sample(gyro_z_dps=10.0, timestamp_monotonic_s=1.1),
        dt=1.0,
        armed=True,
        now_monotonic_s=1.1,
    )

    assert first.steering == pytest.approx(0.0)
    assert second.steering < 0.0
    assert second.heading_error_deg < 0.0
    assert second.mode == DriveMode.HEADING_HOLD


def test_heading_hold_resets_state_when_rearmed() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            yaw_rate_kp=0.02,
            heading_hold_kp=2.0,
            heading_hold_ki=0.0,
            heading_hold_kd=0.0,
            heading_hold_max_rate_dps=45.0,
            yaw_rate_deadband_dps=0.0,
            yaw_rate_filter_hz=0.0,
        )
    )

    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.HEADING_HOLD,
        imu_sample=_sample(gyro_z_dps=0.0, timestamp_monotonic_s=0.1),
        dt=0.1,
        armed=True,
        now_monotonic_s=0.1,
    )
    drifted = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.HEADING_HOLD,
        imu_sample=_sample(gyro_z_dps=10.0, timestamp_monotonic_s=1.1),
        dt=1.0,
        armed=True,
        now_monotonic_s=1.1,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.HEADING_HOLD,
        imu_sample=_sample(gyro_z_dps=0.0, timestamp_monotonic_s=1.2),
        dt=0.1,
        armed=False,
        now_monotonic_s=1.2,
    )
    rearmed = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.HEADING_HOLD,
        imu_sample=_sample(gyro_z_dps=0.0, timestamp_monotonic_s=2.0),
        dt=0.1,
        armed=True,
        now_monotonic_s=2.0,
    )

    assert drifted.steering < 0.0
    assert rearmed.steering == pytest.approx(0.0)
    assert rearmed.heading_error_deg == pytest.approx(0.0)


def test_stale_imu_sample_falls_back_to_manual_semantics() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            stale_timeout_s=0.2,
            yaw_rate_kp=0.02,
        )
    )

    result = controller.update(
        throttle=0.2,
        steering=0.1,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=15.0, timestamp_monotonic_s=0.0),
        dt=0.1,
        armed=True,
        now_monotonic_s=1.0,
    )

    assert result.throttle == pytest.approx(0.2)
    assert result.steering == pytest.approx(0.1)
    assert result.imu_healthy is False
    assert result.mode == DriveMode.STABILIZED


def test_bias_calibration_restarts_on_new_disarm_window() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            gyro_bias_calibration_s=1.0,
            yaw_rate_kp=0.02,
        )
    )

    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=0.0),
        dt=0.1,
        armed=False,
        now_monotonic_s=0.0,
    )
    first_window = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=1.0),
        dt=1.0,
        armed=False,
        now_monotonic_s=1.0,
    )
    assert first_window.gyro_bias_dps == pytest.approx(2.0)

    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=1.1),
        dt=0.1,
        armed=True,
        now_monotonic_s=1.1,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=20.0, timestamp_monotonic_s=2.0),
        dt=0.1,
        armed=False,
        now_monotonic_s=2.0,
    )
    second_window = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=20.0, timestamp_monotonic_s=3.0),
        dt=1.0,
        armed=False,
        now_monotonic_s=3.0,
    )
    second_window = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.MANUAL,
        imu_sample=_sample(gyro_z_dps=20.0, timestamp_monotonic_s=4.0),
        dt=1.0,
        armed=False,
        now_monotonic_s=4.0,
    )

    assert second_window.gyro_bias_dps == pytest.approx(20.0)


def test_rearm_after_disarm_motion_recalibrates_from_settled_idle() -> None:
    controller = AssistedDriveController(
        AssistedDriveConfig(
            gyro_bias_calibration_s=1.0,
            yaw_rate_kp=0.02,
            yaw_rate_ki=0.0,
            yaw_rate_kd=0.0,
            yaw_rate_deadband_dps=0.0,
            yaw_rate_filter_hz=0.0,
        )
    )

    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=0.0),
        dt=0.1,
        armed=False,
        now_monotonic_s=0.0,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=1.0),
        dt=1.0,
        armed=False,
        now_monotonic_s=1.0,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=1.1),
        dt=0.1,
        armed=True,
        now_monotonic_s=1.1,
    )

    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=20.0, timestamp_monotonic_s=2.0),
        dt=0.1,
        armed=False,
        now_monotonic_s=2.0,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=18.0, timestamp_monotonic_s=2.2),
        dt=0.2,
        armed=False,
        now_monotonic_s=2.2,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=2.6),
        dt=0.4,
        armed=False,
        now_monotonic_s=2.6,
    )
    controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=2.1, timestamp_monotonic_s=3.1),
        dt=0.5,
        armed=False,
        now_monotonic_s=3.1,
    )
    settled = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=1.9, timestamp_monotonic_s=3.6),
        dt=0.5,
        armed=False,
        now_monotonic_s=3.6,
    )
    rearmed = controller.update(
        throttle=0.0,
        steering=0.0,
        mode=DriveMode.STABILIZED,
        imu_sample=_sample(gyro_z_dps=2.0, timestamp_monotonic_s=3.7),
        dt=0.1,
        armed=True,
        now_monotonic_s=3.7,
    )

    assert settled.gyro_bias_dps == pytest.approx(2.0, abs=0.1)
    assert rearmed.measured_yaw_rate_dps == pytest.approx(0.0, abs=0.1)
    assert rearmed.steering == pytest.approx(0.0, abs=0.01)