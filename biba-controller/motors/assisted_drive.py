"""IMU-assisted drive helpers for stabilized and heading-hold modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from imu import IMUSample


class DriveMode(str, Enum):
    MANUAL = "manual"
    STABILIZED = "stabilized"
    HEADING_HOLD = "heading_hold"


@dataclass(frozen=True)
class AssistedDriveConfig:
    steering_deadband: float = 0.05
    steering_limit: float = 1.0
    yaw_rate_max_dps: float = 90.0
    yaw_rate_kp: float = 0.02
    yaw_rate_ki: float = 0.0
    yaw_rate_kd: float = 0.0
    heading_hold_kp: float = 2.0
    heading_hold_ki: float = 0.0
    heading_hold_kd: float = 0.0
    heading_hold_max_rate_dps: float = 45.0
    stale_timeout_s: float = 0.2
    gyro_bias_calibration_s: float = 1.0


@dataclass(frozen=True)
class AssistedDriveResult:
    throttle: float
    steering: float
    mode: DriveMode
    imu_healthy: bool
    desired_yaw_rate_dps: float
    measured_yaw_rate_dps: float
    heading_error_deg: float
    heading_reference_deg: float | None
    steering_correction: float
    gyro_bias_dps: float


def _clamp(value: float, limit: float = 1.0) -> float:
    return max(-limit, min(limit, value))


def _normalize_angle_deg(value: float) -> float:
    while value <= -180.0:
        value += 360.0
    while value > 180.0:
        value -= 360.0
    return value


class AssistedDriveController:
    def __init__(self, config: AssistedDriveConfig) -> None:
        self._config = config
        self._last_mode = DriveMode.MANUAL
        self._last_armed: bool | None = None
        self._yaw_rate_integral = 0.0
        self._last_yaw_rate_error: float | None = None
        self._heading_integral = 0.0
        self._last_heading_error: float | None = None
        self._heading_deg = 0.0
        self._heading_reference_deg: float | None = None
        self._gyro_bias_dps = 0.0
        self._bias_started_at: float | None = None
        self._bias_sum = 0.0
        self._bias_count = 0
        self._bias_window_complete = False

    def reset(self) -> None:
        self._yaw_rate_integral = 0.0
        self._last_yaw_rate_error = None
        self._heading_integral = 0.0
        self._last_heading_error = None
        self._heading_deg = 0.0
        self._heading_reference_deg = None

    def _sample_is_healthy(self, imu_sample: IMUSample, now_monotonic_s: float) -> bool:
        if not imu_sample.valid or imu_sample.gyro_z_dps is None or imu_sample.timestamp_monotonic_s is None:
            return False
        return now_monotonic_s - imu_sample.timestamp_monotonic_s <= self._config.stale_timeout_s

    def _begin_bias_window(self, now_monotonic_s: float) -> None:
        self._bias_started_at = now_monotonic_s
        self._bias_sum = 0.0
        self._bias_count = 0
        self._bias_window_complete = False

    def _calibrate_bias(self, imu_sample: IMUSample, now_monotonic_s: float) -> None:
        if self._bias_window_complete or not imu_sample.valid or imu_sample.gyro_z_dps is None:
            return
        if self._bias_started_at is None:
            self._begin_bias_window(now_monotonic_s)
        self._bias_sum += imu_sample.gyro_z_dps
        self._bias_count += 1
        if now_monotonic_s - self._bias_started_at >= self._config.gyro_bias_calibration_s and self._bias_count > 0:
            self._gyro_bias_dps = self._bias_sum / self._bias_count
            self._bias_window_complete = True

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

    def _heading_hold_rate(self, dt: float) -> tuple[float, float]:
        if self._heading_reference_deg is None:
            self._heading_reference_deg = self._heading_deg
        error = _normalize_angle_deg(self._heading_reference_deg - self._heading_deg)
        if dt > 0.0:
            self._heading_integral += error * dt
        derivative = 0.0
        if self._last_heading_error is not None and dt > 0.0:
            derivative = (error - self._last_heading_error) / dt
        self._last_heading_error = error
        desired_rate = (
            self._config.heading_hold_kp * error
            + self._config.heading_hold_ki * self._heading_integral
            + self._config.heading_hold_kd * derivative
        )
        desired_rate = max(
            -self._config.heading_hold_max_rate_dps,
            min(self._config.heading_hold_max_rate_dps, desired_rate),
        )
        return desired_rate, error

    def update(
        self,
        *,
        throttle: float,
        steering: float,
        mode: DriveMode | str,
        imu_sample: IMUSample,
        dt: float,
        armed: bool,
        now_monotonic_s: float,
    ) -> AssistedDriveResult:
        if not isinstance(mode, DriveMode):
            mode = DriveMode(mode)

        if mode != self._last_mode:
            self.reset()
            self._last_mode = mode

        if armed != self._last_armed:
            if not armed:
                self._begin_bias_window(now_monotonic_s)
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
                heading_error_deg=0.0,
                heading_reference_deg=self._heading_reference_deg,
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
                heading_error_deg=0.0,
                heading_reference_deg=self._heading_reference_deg,
                steering_correction=steering,
                gyro_bias_dps=self._gyro_bias_dps,
            )

        measured_yaw_rate_dps = (imu_sample.gyro_z_dps or 0.0) - self._gyro_bias_dps
        self._heading_deg = _normalize_angle_deg(self._heading_deg + measured_yaw_rate_dps * max(dt, 0.0))
        heading_error_deg = 0.0

        if mode == DriveMode.STABILIZED:
            desired_yaw_rate_dps = 0.0 if abs(steering) < self._config.steering_deadband else steering * self._config.yaw_rate_max_dps
            steering_output = self._yaw_rate_to_steering(desired_yaw_rate_dps, measured_yaw_rate_dps, dt)
            self._heading_reference_deg = None
            self._heading_integral = 0.0
            self._last_heading_error = None
        else:
            if abs(steering) >= self._config.steering_deadband:
                desired_yaw_rate_dps = steering * self._config.yaw_rate_max_dps
                self._heading_reference_deg = self._heading_deg
                self._heading_integral = 0.0
                self._last_heading_error = None
            else:
                desired_yaw_rate_dps, heading_error_deg = self._heading_hold_rate(dt)
            steering_output = self._yaw_rate_to_steering(desired_yaw_rate_dps, measured_yaw_rate_dps, dt)

        return AssistedDriveResult(
            throttle=throttle,
            steering=steering_output,
            mode=mode,
            imu_healthy=True,
            desired_yaw_rate_dps=desired_yaw_rate_dps,
            measured_yaw_rate_dps=measured_yaw_rate_dps,
            heading_error_deg=heading_error_deg,
            heading_reference_deg=self._heading_reference_deg,
            steering_correction=steering_output,
            gyro_bias_dps=self._gyro_bias_dps,
        )