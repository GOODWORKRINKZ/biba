"""Motor driver and differential drive helpers."""

from __future__ import annotations

import time

import pigpio

import config
from motors.ramping import SpeedRamp


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


class BTS7960MotorDriver:
    """Control one motor through BTS7960 RPWM/LPWM and enable pins."""

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

        for pin in self._unique_pins(self.rpwm_pin, self.lpwm_pin, self.ren_pin, self.len_pin):
            self.pi.set_mode(pin, pigpio.OUTPUT)

        for pin in self._unique_pins(self.ren_pin, self.len_pin):
            self.pi.write(pin, 1)

        self.pi.set_PWM_frequency(self.rpwm_pin, config.PWM_FREQUENCY_HZ)
        self.pi.set_PWM_frequency(self.lpwm_pin, config.PWM_FREQUENCY_HZ)
        self.pi.set_PWM_dutycycle(self.rpwm_pin, 0)
        self.pi.set_PWM_dutycycle(self.lpwm_pin, 0)

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

        duty_cycle = int(abs(clamped) * 255)
        if clamped > 0.0:
            self.pi.set_PWM_dutycycle(self.rpwm_pin, duty_cycle)
            self.pi.set_PWM_dutycycle(self.lpwm_pin, 0)
        elif clamped < 0.0:
            self.pi.set_PWM_dutycycle(self.rpwm_pin, 0)
            self.pi.set_PWM_dutycycle(self.lpwm_pin, duty_cycle)
        else:
            self.stop()

    def stop(self) -> None:
        """Stop the motor immediately."""
        self.pi.set_PWM_dutycycle(self.rpwm_pin, 0)
        self.pi.set_PWM_dutycycle(self.lpwm_pin, 0)


class DifferentialDrive:
    """Apply arcade mixing for a two-wheel robot."""

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
            deadband=config.MOTOR_DEADBAND,
        )
        self._right_ramp = SpeedRamp(
            accel_rate=config.RAMP_ACCEL_RATE,
            decel_rate=config.RAMP_DECEL_RATE,
            deadband=config.MOTOR_DEADBAND,
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))

    def drive(self, throttle: float, steering: float, dt: float = 0.02) -> None:
        """Apply throttle and steering to the left and right motor outputs."""
        left = self._clamp(throttle + steering)
        right = self._clamp(throttle - steering)
        if self.left_enabled:
            self.left_motor.set_speed(self._left_ramp.update(left, dt))
        else:
            self._left_ramp.reset()

        if self.right_enabled:
            self.right_motor.set_speed(self._right_ramp.update(right, dt))
        else:
            self._right_ramp.reset()

    def emergency_stop(self) -> None:
        """Bypass ramp and stop motors immediately (shutdown only)."""
        self._left_ramp.reset()
        self._right_ramp.reset()
        self.left_motor.stop()
        self.right_motor.stop()

    def stop(self) -> None:
        """Stop both drive motors immediately (legacy, no ramp)."""
        self.left_motor.stop()
        self.right_motor.stop()

    def check_failsafe(self, last_frame_time: float) -> bool:
        """Flag failsafe when no fresh CRSF frame arrives in time."""
        if time.monotonic() - last_frame_time > config.FAILSAFE_TIMEOUT_S:
            return True
        return False
