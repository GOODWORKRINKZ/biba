from __future__ import annotations

import logging

import pytest

from motors.driver import BTS7960MotorDriver, DifferentialDrive, MotorDriver


class FakePi:
    def __init__(self) -> None:
        self.mode_calls: list[tuple[int, int]] = []
        self.frequency_calls: list[tuple[int, int]] = []
        self.hardware_pwm_calls: list[tuple[int, int, int]] = []
        self.write_calls: list[tuple[int, int]] = []
        self.duty_calls: list[tuple[int, int]] = []
        self.range_calls: list[tuple[int, int]] = []
        self._real_range = 255

    def set_mode(self, pin: int, mode: int) -> None:
        self.mode_calls.append((pin, mode))

    def set_PWM_frequency(self, pin: int, frequency: int) -> None:
        self.frequency_calls.append((pin, frequency))

    def hardware_PWM(self, pin: int, frequency: int, duty_cycle: int) -> None:
        self.hardware_pwm_calls.append((pin, frequency, duty_cycle))

    def write(self, pin: int, value: int) -> None:
        self.write_calls.append((pin, value))

    def set_PWM_dutycycle(self, pin: int, duty_cycle: int) -> None:
        self.duty_calls.append((pin, duty_cycle))

    def get_PWM_real_range(self, pin: int) -> int:
        return self._real_range

    def set_PWM_range(self, pin: int, range_val: int) -> None:
        self.range_calls.append((pin, range_val))


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


def test_bts7960_motor_driver_initializes_pwm_and_enable_pins() -> None:
    pi = FakePi()

    BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=24)

    assert pi.mode_calls == [(23, 1), (24, 1)]
    assert pi.frequency_calls == []
    assert pi.hardware_pwm_calls == [(18, 20000, 0), (13, 20000, 0)]
    assert pi.write_calls == [(23, 1), (24, 1)]
    assert pi.duty_calls == []


def test_bts7960_motor_driver_uses_rpwm_for_forward_motion() -> None:
    pi = FakePi()
    driver = BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=24)

    driver.set_speed(0.5)

    assert pi.hardware_pwm_calls[-2:] == [(18, 20000, 500000), (13, 20000, 0)]


def test_bts7960_motor_driver_uses_lpwm_for_reverse_motion() -> None:
    pi = FakePi()
    driver = BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=24)

    driver.set_speed(-0.5)

    assert pi.hardware_pwm_calls[-2:] == [(18, 20000, 0), (13, 20000, 500000)]


def test_bts7960_motor_driver_can_invert_direction_logic() -> None:
    pi = FakePi()
    driver = BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=24, inverted=True)

    driver.set_speed(0.5)

    assert pi.hardware_pwm_calls[-2:] == [(18, 20000, 0), (13, 20000, 500000)]


def test_bts7960_motor_driver_stop_disables_both_pwm_channels() -> None:
    pi = FakePi()
    driver = BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=24)

    driver.stop()

    assert pi.hardware_pwm_calls[-2:] == [(18, 20000, 0), (13, 20000, 0)]


def test_bts7960_motor_driver_supports_shared_enable_pin() -> None:
    pi = FakePi()

    BTS7960MotorDriver(pi, rpwm_pin=18, lpwm_pin=13, ren_pin=23, len_pin=23)

    assert pi.mode_calls == [(23, 1)]
    assert pi.write_calls == [(23, 1)]


def test_differential_drive_mixes_throttle_and_steering() -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor)

    # With default ramp (accel_rate=2.0, dt=0.02): max_step=0.04
    # target left=1.0, target right=0.25
    drive.drive(0.75, 0.5)

    # Both outputs are ramped from 0 — capped at accel step
    assert len(left_motor.speed_calls) == 1
    assert len(right_motor.speed_calls) == 1
    assert left_motor.speed_calls[0] == pytest.approx(0.04)
    assert right_motor.speed_calls[0] == pytest.approx(0.04)


def test_differential_drive_can_disable_right_motor() -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor, right_enabled=False)

    drive.drive(0.75, 0.5)

    assert len(left_motor.speed_calls) == 1
    assert left_motor.speed_calls[0] == pytest.approx(0.04)
    assert right_motor.speed_calls == []
    assert right_motor.stop_calls == 0


def test_differential_drive_can_disable_left_motor() -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor, left_enabled=False)

    drive.drive(0.75, 0.5)

    assert left_motor.speed_calls == []
    assert left_motor.stop_calls == 0
    assert len(right_motor.speed_calls) == 1
    assert right_motor.speed_calls[0] == pytest.approx(0.04)


def test_differential_drive_logs_large_output_jump(caplog: pytest.LogCaptureFixture) -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor)

    drive.drive(1.0, 0.0, dt=0.02)

    with caplog.at_level(logging.WARNING, logger="biba-controller"):
        drive.drive(1.0, 0.0, dt=0.30)

    assert "Large PWM jump" in caplog.text
    assert "motor=left" in caplog.text
    assert "previous=0.040" in caplog.text
    assert "current=0.640" in caplog.text


def test_check_failsafe_stops_platform_when_frame_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    left_motor = FakeMotor()
    right_motor = FakeMotor()
    drive = DifferentialDrive(left_motor, right_motor)

    monkeypatch.setattr("motors.driver.time.monotonic", lambda: 10.0)

    # check_failsafe now only returns True, does not call stop()
    assert drive.check_failsafe(8.0) is True
    assert left_motor.stop_calls == 0
    assert right_motor.stop_calls == 0
