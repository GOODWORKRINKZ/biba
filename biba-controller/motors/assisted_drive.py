"""IMU-assisted drive helpers for manual and stabilized modes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from imu import IMUSample


class DriveMode(str, Enum):
    MANUAL = "manual"
    STABILIZED = "stabilized"


@dataclass(frozen=True)
class AssistedDriveConfig:
    throttle_deadband: float = 0.05
    stabilization_min_throttle: float = 0.1
    steering_deadband: float = 0.05
    steering_limit: float = 1.0
    neutral_stabilization_steering_limit: float = 0.12
    neutral_stabilization_max_throttle: float = 0.25
    yaw_rate_max_dps: float = 90.0
    yaw_rate_kp: float = 0.02
    yaw_rate_ki: float = 0.0
    yaw_rate_kd: float = 0.0
    yaw_rate_deadband_dps: float = 4.0
    yaw_rate_filter_hz: float = 5.0
    stale_timeout_s: float = 0.2
    gyro_bias_calibration_s: float = 1.0
    gyro_bias_settle_s: float = 0.5
    gyro_bias_stability_band_dps: float = 1.0
    accel_stationary_tolerance_g: float = 0.15


@dataclass(frozen=True)
class AssistedDriveResult:
    throttle: float
    steering: float
    mode: DriveMode
    imu_healthy: bool
    desired_yaw_rate_dps: float
    measured_yaw_rate_dps: float
    steering_correction: float
    gyro_bias_dps: float
    heading_error_deg: float = 0.0
    heading_reference_deg: float | None = None


def _clamp(value: float, limit: float = 1.0) -> float:
    return max(-limit, min(limit, value))


def _accel_magnitude_g(imu_sample: IMUSample) -> float | None:
    if imu_sample.accel_x_g is None or imu_sample.accel_y_g is None or imu_sample.accel_z_g is None:
        return None
    return math.sqrt(
        imu_sample.accel_x_g * imu_sample.accel_x_g
        + imu_sample.accel_y_g * imu_sample.accel_y_g
        + imu_sample.accel_z_g * imu_sample.accel_z_g
    )


class AssistedDriveController:
    def __init__(self, config: AssistedDriveConfig) -> None:
        self._config = config
        self._last_mode = DriveMode.MANUAL
        self._last_armed: bool | None = None
        self._yaw_rate_integral = 0.0
        self._last_yaw_rate_error: float | None = None
        self._gyro_bias_dps = 0.0
        self._bias_ready_at: float | None = None
        self._bias_started_at: float | None = None
        self._bias_sum = 0.0
        self._bias_count = 0
        self._bias_window_complete = False
        self._filtered_yaw_rate_dps = 0.0

    def reset(self) -> None:
        self._yaw_rate_integral = 0.0
        self._last_yaw_rate_error = None
        self._filtered_yaw_rate_dps = 0.0

    def _sample_is_healthy(self, imu_sample: IMUSample, now_monotonic_s: float) -> bool:
        if not imu_sample.valid or imu_sample.gyro_z_dps is None or imu_sample.timestamp_monotonic_s is None:
            return False
        return now_monotonic_s - imu_sample.timestamp_monotonic_s <= self._config.stale_timeout_s

    def _sample_is_stationary(self, imu_sample: IMUSample) -> bool:
        accel_magnitude_g = _accel_magnitude_g(imu_sample)
        if accel_magnitude_g is None:
            return False
        return abs(accel_magnitude_g - 1.0) <= self._config.accel_stationary_tolerance_g

    def _reset_yaw_rate_controller(self) -> None:
        self._yaw_rate_integral = 0.0
        self._last_yaw_rate_error = None

    def _has_steering_intent(self, steering_intent: float) -> bool:
        return abs(steering_intent) >= self._config.steering_deadband

    def _inputs_are_idle_neutral(self, throttle: float, steering_intent: float) -> bool:
        return abs(throttle) < self._config.throttle_deadband and not self._has_steering_intent(steering_intent)

    def _should_skip_neutral_stabilization(self, throttle: float, steering_intent: float) -> bool:
        return not self._has_steering_intent(steering_intent) and abs(throttle) < self._config.stabilization_min_throttle

    def _preserve_steering_intent(
        self,
        requested_steering: float,
        steering_output: float,
        steering_intent: float,
    ) -> float:
        if not self._has_steering_intent(steering_intent):
            return steering_output
        if steering_output * requested_steering <= 0.0 or abs(steering_output) < abs(requested_steering):
            return requested_steering
        return steering_output

    def _limit_neutral_stabilization_output(self, steering_output: float) -> float:
        return _clamp(steering_output, self._config.neutral_stabilization_steering_limit)

    def _should_limit_neutral_stabilization_output(self, throttle: float, steering_intent: float) -> bool:
        return not self._has_steering_intent(steering_intent) and abs(throttle) <= self._config.neutral_stabilization_max_throttle

    def _prepare_bias_window(self, now_monotonic_s: float, *, settle_s: float) -> None:
        self._bias_ready_at = now_monotonic_s + max(settle_s, 0.0)
        self._bias_started_at = None
        self._bias_sum = 0.0
        self._bias_count = 0
        self._bias_window_complete = False

    def _restart_bias_window(self, now_monotonic_s: float, gyro_z_dps: float) -> None:
        self._bias_started_at = now_monotonic_s
        self._bias_sum = gyro_z_dps
        self._bias_count = 1
        self._bias_window_complete = False

    def _calibrate_bias(self, imu_sample: IMUSample, now_monotonic_s: float) -> None:
        if self._bias_window_complete or not imu_sample.valid or imu_sample.gyro_z_dps is None:
            return
        if self._bias_ready_at is not None and now_monotonic_s < self._bias_ready_at:
            return
        if not self._sample_is_stationary(imu_sample):
            return

        if self._bias_started_at is None or self._bias_count <= 0:
            self._restart_bias_window(now_monotonic_s, imu_sample.gyro_z_dps)
            return

        current_mean = self._bias_sum / self._bias_count
        if abs(imu_sample.gyro_z_dps - current_mean) > self._config.gyro_bias_stability_band_dps:
            self._restart_bias_window(now_monotonic_s, imu_sample.gyro_z_dps)
            return

        self._bias_sum += imu_sample.gyro_z_dps
        self._bias_count += 1
        if now_monotonic_s - self._bias_started_at >= self._config.gyro_bias_calibration_s and self._bias_count > 0:
            self._gyro_bias_dps = self._bias_sum / self._bias_count
            self._bias_window_complete = True

    def _filter_yaw_rate(self, measured_yaw_rate_dps: float, dt: float) -> float:
        if self._config.yaw_rate_filter_hz <= 0.0 or dt <= 0.0:
            self._filtered_yaw_rate_dps = measured_yaw_rate_dps
            return measured_yaw_rate_dps

        tau_s = 1.0 / (2.0 * math.pi * self._config.yaw_rate_filter_hz)
        alpha = dt / (tau_s + dt)
        self._filtered_yaw_rate_dps += alpha * (measured_yaw_rate_dps - self._filtered_yaw_rate_dps)
        return self._filtered_yaw_rate_dps

    def _apply_yaw_rate_deadband(self, measured_yaw_rate_dps: float) -> float:
        if abs(measured_yaw_rate_dps) < self._config.yaw_rate_deadband_dps:
            return 0.0
        return measured_yaw_rate_dps

    def _yaw_rate_to_steering(self, desired_yaw_rate_dps: float, measured_yaw_rate_dps: float, dt: float) -> float:
        error = desired_yaw_rate_dps - measured_yaw_rate_dps
        if dt > 0.0:
            self._yaw_rate_integral += error * dt
        derivative = 0.0
        if self._last_yaw_rate_error is not None and dt > 0.0:
            derivative = (error - self._last_yaw_rate_error) / dt
        self._last_yaw_rate_error = error
        steering = (
            self._config.yaw_rate_kp * error
            + self._config.yaw_rate_ki * self._yaw_rate_integral
            + self._config.yaw_rate_kd * derivative
        )
        return _clamp(steering, self._config.steering_limit)

    def update(
        self,
        *,
        throttle: float,
        steering: float,
        steering_intent: float | None = None,
        mode: DriveMode | str,
        imu_sample: IMUSample,
        dt: float,
        armed: bool,
        now_monotonic_s: float,
    ) -> AssistedDriveResult:
        if steering_intent is None:
            steering_intent = steering
        if not isinstance(mode, DriveMode):
            mode = DriveMode(mode)

        if mode != self._last_mode:
            self.reset()
            self._last_mode = mode

        if armed != self._last_armed:
            self.reset()
            if not armed:
                settle_s = 0.0 if self._last_armed is None else self._config.gyro_bias_settle_s
                self._prepare_bias_window(now_monotonic_s, settle_s=settle_s)
            else:
                self._bias_ready_at = None
            self._last_armed = armed

        if not armed:
            self._calibrate_bias(imu_sample, now_monotonic_s)
            return AssistedDriveResult(
                throttle=throttle,
                steering=steering,
                mode=mode,
                imu_healthy=self._sample_is_healthy(imu_sample, now_monotonic_s),
                desired_yaw_rate_dps=0.0,
                measured_yaw_rate_dps=0.0,
                steering_correction=steering,
                gyro_bias_dps=self._gyro_bias_dps,
            )

        imu_healthy = self._sample_is_healthy(imu_sample, now_monotonic_s)
        if mode == DriveMode.MANUAL or not imu_healthy:
            if not imu_healthy:
                self.reset()
            return AssistedDriveResult(
                throttle=throttle,
                steering=steering,
                mode=mode,
                imu_healthy=imu_healthy,
                desired_yaw_rate_dps=0.0,
                measured_yaw_rate_dps=0.0,
                steering_correction=steering,
                gyro_bias_dps=self._gyro_bias_dps,
            )

        measured_yaw_rate_dps = (imu_sample.gyro_z_dps or 0.0) - self._gyro_bias_dps
        measured_yaw_rate_dps = self._filter_yaw_rate(measured_yaw_rate_dps, dt)
        measured_yaw_rate_dps = self._apply_yaw_rate_deadband(measured_yaw_rate_dps)

        if self._inputs_are_idle_neutral(throttle, steering_intent):
            self._reset_yaw_rate_controller()
            return AssistedDriveResult(
                throttle=throttle,
                steering=0.0,
                mode=mode,
                imu_healthy=True,
                desired_yaw_rate_dps=0.0,
                measured_yaw_rate_dps=measured_yaw_rate_dps,
                steering_correction=0.0,
                gyro_bias_dps=self._gyro_bias_dps,
            )

        if self._should_skip_neutral_stabilization(throttle, steering_intent):
            self._reset_yaw_rate_controller()
            return AssistedDriveResult(
                throttle=throttle,
                steering=steering,
                mode=mode,
                imu_healthy=True,
                desired_yaw_rate_dps=0.0,
                measured_yaw_rate_dps=measured_yaw_rate_dps,
                steering_correction=steering,
                gyro_bias_dps=self._gyro_bias_dps,
            )

        desired_yaw_rate_dps = 0.0 if not self._has_steering_intent(steering_intent) else steering * self._config.yaw_rate_max_dps
        steering_output = self._yaw_rate_to_steering(desired_yaw_rate_dps, measured_yaw_rate_dps, dt)
        if self._should_limit_neutral_stabilization_output(throttle, steering_intent):
            steering_output = self._limit_neutral_stabilization_output(steering_output)
        steering_output = self._preserve_steering_intent(steering, steering_output, steering_intent)

        return AssistedDriveResult(
            throttle=throttle,
            steering=steering_output,
            mode=mode,
            imu_healthy=True,
            desired_yaw_rate_dps=desired_yaw_rate_dps,
            measured_yaw_rate_dps=measured_yaw_rate_dps,
            steering_correction=steering_output,
            gyro_bias_dps=self._gyro_bias_dps,
        )