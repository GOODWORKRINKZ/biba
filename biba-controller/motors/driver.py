"""Motor driver and differential drive helpers."""

from __future__ import annotations

import logging
import time

import pigpio

import config
from motors.ramping import SpeedRamp


LOGGER = logging.getLogger("biba-controller")


class MotorDriver:
    """Control one motor through a PWM pin and a direction pin."""

    def __init__(self, pi: pigpio.pi, pwm_pin: int, dir_pin: int, inverted: bool = False) -> None:
        self.pi = pi
        self.pwm_pin = pwm_pin
        self.dir_pin = dir_pin
        self.inverted = inverted
        self.pi.set_mode(self.pwm_pin, pigpio.OUTPUT)
        self.pi.set_mode(self.dir_pin, pigpio.OUTPUT)
        self.pi.set_PWM_frequency(self.pwm_pin, config.PWM_FREQUENCY_HZ)
        self._pwm_range = self.pi.get_PWM_real_range(self.pwm_pin)
        self.pi.set_PWM_range(self.pwm_pin, self._pwm_range)
        self.pi.write(self.dir_pin, 0)
        self.pi.set_PWM_dutycycle(self.pwm_pin, 0)

    def set_speed(self, value: float) -> None:
        """Set motor speed in the range -1.0..1.0."""
        clamped = max(-1.0, min(1.0, value))
        direction = 1 if clamped < 0 else 0
        if self.inverted:
            direction = 1 - direction
        duty_cycle = int(abs(clamped) * self._pwm_range)
        self.pi.write(self.dir_pin, direction)
        self.pi.set_PWM_dutycycle(self.pwm_pin, duty_cycle)

    def stop(self) -> None:
        """Stop the motor immediately."""
        self.pi.set_PWM_dutycycle(self.pwm_pin, 0)


class BTS7960MotorDriver:
    """Control one motor through BTS7960 RPWM/LPWM and enable pins.

    Uses hardware PWM for precise frequency control (20 kHz, inaudible)
    and fine duty-cycle resolution (1 000 000 steps).
    """

    _HW_PWM_RANGE = 1_000_000  # hardware_PWM duty range 0..1 000 000

    def __init__(
        self,
        pi: pigpio.pi,
        rpwm_pin: int,
        lpwm_pin: int,
        ren_pin: int,
        len_pin: int,
        inverted: bool = False,
    ) -> None:
        self.pi = pi
        self.rpwm_pin = rpwm_pin
        self.lpwm_pin = lpwm_pin
        self.ren_pin = ren_pin
        self.len_pin = len_pin
        self.inverted = inverted
        self._frequency = config.PWM_FREQUENCY_HZ

        for pin in self._unique_pins(self.ren_pin, self.len_pin):
            self.pi.set_mode(pin, pigpio.OUTPUT)

        for pin in self._unique_pins(self.ren_pin, self.len_pin):
            self.pi.write(pin, 1)

        self.pi.hardware_PWM(self.rpwm_pin, self._frequency, 0)
        self.pi.hardware_PWM(self.lpwm_pin, self._frequency, 0)

    @staticmethod
    def _unique_pins(*pins: int) -> list[int]:
        seen: set[int] = set()
        unique: list[int] = []
        for pin in pins:
            if pin not in seen:
                seen.add(pin)
                unique.append(pin)
        return unique

    def set_speed(self, value: float) -> None:
        """Set motor speed in the range -1.0..1.0."""
        clamped = max(-1.0, min(1.0, value))
        if self.inverted:
            clamped *= -1.0

        duty = int(abs(clamped) * self._HW_PWM_RANGE)
        if clamped > 0.0:
            self.pi.hardware_PWM(self.rpwm_pin, self._frequency, duty)
            self.pi.hardware_PWM(self.lpwm_pin, self._frequency, 0)
        elif clamped < 0.0:
            self.pi.hardware_PWM(self.rpwm_pin, self._frequency, 0)
            self.pi.hardware_PWM(self.lpwm_pin, self._frequency, duty)
        else:
            self.stop()

    def stop(self) -> None:
        """Stop the motor immediately."""
        self.pi.hardware_PWM(self.rpwm_pin, self._frequency, 0)
        self.pi.hardware_PWM(self.lpwm_pin, self._frequency, 0)


class DifferentialDrive:
    """Apply arcade mixing for a two-wheel robot."""

    _PWM_JUMP_WARN_THRESHOLD = 0.10

    def __init__(
        self,
        left_motor: MotorDriver,
        right_motor: MotorDriver,
        left_enabled: bool | None = None,
        right_enabled: bool | None = None,
    ) -> None:
        self.left_motor = left_motor
        self.right_motor = right_motor
        self.left_enabled = config.LEFT_MOTOR_ENABLED if left_enabled is None else left_enabled
        self.right_enabled = config.RIGHT_MOTOR_ENABLED if right_enabled is None else right_enabled
        self._left_ramp = SpeedRamp(
            accel_rate=config.RAMP_ACCEL_RATE,
            decel_rate=config.RAMP_DECEL_RATE,
            reverse_decel_rate=config.RAMP_REVERSE_DECEL_RATE,
            deadband=config.MOTOR_DEADBAND,
            zero_hold_s=config.RAMP_ZERO_HOLD_S,
        )
        self._right_ramp = SpeedRamp(
            accel_rate=config.RAMP_ACCEL_RATE,
            decel_rate=config.RAMP_DECEL_RATE,
            reverse_decel_rate=config.RAMP_REVERSE_DECEL_RATE,
            deadband=config.MOTOR_DEADBAND,
            zero_hold_s=config.RAMP_ZERO_HOLD_S,
        )
        self._last_left_duty: float | None = None
        self._last_right_duty: float | None = None

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))

    def _log_large_jump(
        self,
        motor: str,
        previous: float | None,
        current: float,
        target: float,
        throttle: float,
        steering: float,
        dt: float,
    ) -> None:
        if previous is None:
            return
        if abs(current - previous) < self._PWM_JUMP_WARN_THRESHOLD:
            return
        LOGGER.warning(
            "Large PWM jump motor=%s previous=%.3f current=%.3f target=%.3f throttle=%.3f steering=%.3f dt=%.3f",
            motor,
            previous,
            current,
            target,
            throttle,
            steering,
            dt,
        )

    def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
        """Apply throttle and steering to the left and right motor outputs.

        Returns (left_duty, right_duty) after ramping.
        """
        left = self._clamp(throttle + steering)
        right = self._clamp(throttle - steering)
        if self.left_enabled:
            left_duty = self._left_ramp.update(left, dt)
            self._log_large_jump("left", self._last_left_duty, left_duty, left, throttle, steering, dt)
            self.left_motor.set_speed(left_duty)
            self._last_left_duty = left_duty
        else:
            self._left_ramp.reset()
            left_duty = 0.0
            self._last_left_duty = 0.0

        if self.right_enabled:
            right_duty = self._right_ramp.update(right, dt)
            self._log_large_jump("right", self._last_right_duty, right_duty, right, throttle, steering, dt)
            self.right_motor.set_speed(right_duty)
            self._last_right_duty = right_duty
        else:
            self._right_ramp.reset()
            right_duty = 0.0
            self._last_right_duty = 0.0
        return left_duty, right_duty

    def emergency_stop(self) -> None:
        """Bypass ramp and stop motors immediately (shutdown only)."""
        self._left_ramp.reset()
        self._right_ramp.reset()
        self._last_left_duty = 0.0
        self._last_right_duty = 0.0
        self.left_motor.stop()
        self.right_motor.stop()

    def stop(self) -> None:
        """Stop both drive motors immediately (legacy, no ramp)."""
        self._last_left_duty = 0.0
        self._last_right_duty = 0.0
        self.left_motor.stop()
        self.right_motor.stop()

    def check_failsafe(self, last_frame_time: float) -> bool:
        """Flag failsafe when no fresh CRSF frame arrives in time."""
        if time.monotonic() - last_frame_time > config.FAILSAFE_TIMEOUT_S:
            return True
        return False
