from __future__ import annotations

import pytest

from motors.driver import DifferentialDrive, MotorDriver


class FakePi:
    def __init__(self) -> None:
        self.mode_calls: list[tuple[int, int]] = []
        self.frequency_calls: list[tuple[int, int]] = []
        self.write_calls: list[tuple[int, int]] = []
        self.duty_calls: list[tuple[int, int]] = []

    def set_mode(self, pin: int, mode: int) -> None:
        self.mode_calls.append((pin, mode))

    def set_PWM_frequency(self, pin: int, frequency: int) -> None:
        self.frequency_calls.append((pin, frequency))

    def write(self, pin: int, value: int) -> None:
        self.write_calls.append((pin, value))

    def set_PWM_dutycycle(self, pin: int, duty_cycle: int) -> None:
        self.duty_calls.append((pin, duty_cycle))


class FakeMotor:
    def __init__(self) -> None:
        self.speed_calls: list[float] = []
        self.stop_calls = 0

    def set_speed(self, value: float) -> None:
        self.speed_calls.append(value)

    def stop(self) -> None:
        self.stop_calls += 1


def test_motor_driver_initializes_pins_and_pwm() -> None:
    pi = FakePi()

    MotorDriver(pi, pwm_pin=18, dir_pin=23)

    assert pi.mode_calls == [(18, 1), (23, 1)]
    assert pi.frequency_calls == [(18, 20000)]
    assert pi.write_calls == [(23, 0)]
    assert pi.duty_calls == [(18, 0)]


def test_motor_driver_sets_direction_and_duty_cycle() -> None:
    pi = FakePi()
    driver = MotorDriver(pi, pwm_pin=18, dir_pin=23)

    driver.set_speed(-0.5)

    assert pi.write_calls[-1] == (23, 1)
    assert pi.duty_calls[-1] == (18, 127)


def test_motor_driver_can_invert_direction_logic() -> None:
    pi = FakePi()
    driver = MotorDriver(pi, pwm_pin=18, dir_pin=23, inverted=True)

    driver.set_speed(-0.5)

    assert pi.write_calls[-1] == (23, 0)
    assert pi.duty_calls[-1] == (18, 127)


def test_differential_drive_mixes_throttle_and_steering() -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor)

    drive.drive(0.75, 0.5)

    assert left_motor.speed_calls == [1.0]
    assert right_motor.speed_calls == [0.25]


def test_check_failsafe_stops_platform_when_frame_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor)

    monkeypatch.setattr("motors.driver.time.monotonic", lambda: 10.0)

    assert drive.check_failsafe(8.0) is True
    assert left_motor.stop_calls == 1
    assert right_motor.stop_calls == 1
