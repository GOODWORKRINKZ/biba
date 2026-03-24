"""Motor driver and differential drive helpers."""

from __future__ import annotations

import time

import pigpio

import config


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
        self.pi.write(self.dir_pin, 0)
        self.pi.set_PWM_dutycycle(self.pwm_pin, 0)

    def set_speed(self, value: float) -> None:
        """Set motor speed in the range -1.0..1.0."""
        clamped = max(-1.0, min(1.0, value))
        direction = 1 if clamped < 0 else 0
        if self.inverted:
            direction = 1 - direction
        duty_cycle = int(abs(clamped) * 255)
        self.pi.write(self.dir_pin, direction)
        self.pi.set_PWM_dutycycle(self.pwm_pin, duty_cycle)

    def stop(self) -> None:
        """Stop the motor immediately."""
        self.pi.set_PWM_dutycycle(self.pwm_pin, 0)


class DifferentialDrive:
    """Apply arcade mixing for a two-wheel robot."""

    def __init__(self, left_motor: MotorDriver, right_motor: MotorDriver) -> None:
        self.left_motor = left_motor
        self.right_motor = right_motor

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))

    def drive(self, throttle: float, steering: float) -> None:
        """Apply throttle and steering to the left and right motor outputs."""
        left = self._clamp(throttle + steering)
        right = self._clamp(throttle - steering)
        self.left_motor.set_speed(left)
        self.right_motor.set_speed(right)

    def stop(self) -> None:
        """Stop both drive motors."""
        self.left_motor.stop()
        self.right_motor.stop()

    def check_failsafe(self, last_frame_time: float) -> bool:
        """Stop the platform when no fresh CRSF frame arrives in time."""
        if time.monotonic() - last_frame_time > config.FAILSAFE_TIMEOUT_S:
            self.stop()
            return True
        return False
