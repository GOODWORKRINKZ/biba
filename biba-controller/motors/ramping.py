"""Slew rate limiter for motor speed commands."""

from __future__ import annotations

import math


class ScalarKalmanFilter:
    """Filter a single control signal with a lightweight Kalman estimator."""

    def __init__(
        self,
        process_noise: float,
        measurement_noise: float,
        initial_estimate: float = 0.0,
        initial_covariance: float = 1.0,
    ) -> None:
        self.process_noise = max(process_noise, 1e-9)
        self.measurement_noise = max(measurement_noise, 1e-9)
        self._initial_covariance = max(initial_covariance, 1e-9)
        self._current = initial_estimate
        self._covariance = self._initial_covariance

    @property
    def current(self) -> float:
        return self._current

    def reset(self, value: float = 0.0) -> None:
        self._current = value
        self._covariance = self._initial_covariance

    def update(self, measurement: float) -> float:
        predicted_covariance = self._covariance + self.process_noise
        kalman_gain = predicted_covariance / (predicted_covariance + self.measurement_noise)
        self._current += kalman_gain * (measurement - self._current)
        self._covariance = (1.0 - kalman_gain) * predicted_covariance
        self._current = max(-1.0, min(1.0, self._current))
        return self._current


class SpeedRamp:
    """Limit the rate of change of a motor speed signal.

    Enforces separate acceleration and deceleration rates and guarantees
    that the output passes through zero before reversing direction.
    """

    def __init__(
        self,
        accel_rate: float,
        decel_rate: float,
        reverse_decel_rate: float | None = None,
        deadband: float = 0.0,
    ) -> None:
        self.accel_rate = accel_rate
        self.decel_rate = decel_rate
        self.reverse_decel_rate = decel_rate if reverse_decel_rate is None else reverse_decel_rate
        self.deadband = deadband
        self._current: float = 0.0

    @property
    def current(self) -> float:
        return self._current

    def reset(self) -> None:
        """Hard-reset to zero (emergency stop)."""
        self._current = 0.0

    def update(self, target: float, dt: float) -> float:
        """Compute the next ramped speed value.

        Args:
            target: Desired speed in -1.0..1.0.
            dt: Time since last call in seconds.

        Returns:
            Ramped speed clamped to -1.0..1.0.
        """
        if dt <= 0.0:
            return self._current

        # Apply deadband
        if abs(target) < self.deadband and not math.isclose(
            abs(target),
            self.deadband,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            target = 0.0

        # Clamp target
        target = max(-1.0, min(1.0, target))

        # Direction change: decel toward zero first, do NOT cross zero
        if self._current > 0.0 and target < 0.0:
            return self._decel_toward_zero(dt)
        if self._current < 0.0 and target > 0.0:
            return self._decel_toward_zero(dt)

        # Same sign (or zero→nonzero): accel or decel
        diff = target - self._current
        if abs(diff) < 1e-9:
            return self._current

        # Determine if accelerating or decelerating
        accelerating = abs(target) > abs(self._current)
        rate = self.accel_rate if accelerating else self.decel_rate
        max_step = rate * dt

        if abs(diff) <= max_step:
            self._current = target
        else:
            self._current += max_step if diff > 0 else -max_step

        self._current = max(-1.0, min(1.0, self._current))
        return self._current

    def _decel_toward_zero(self, dt: float) -> float:
        """Decelerate toward zero without crossing it."""
        max_step = self.reverse_decel_rate * dt
        if abs(self._current) <= max_step:
            self._current = 0.0
        elif self._current > 0.0:
            self._current -= max_step
        else:
            self._current += max_step
        return self._current
