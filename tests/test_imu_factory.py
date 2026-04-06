from __future__ import annotations

import pytest

from imu.bmi160 import BMI160Reader
from imu.lsm6ds3 import LSM6DS3Reader
from imu.factory import detect_imu_kind, open_imu_reader


class FakeBus:
    def __init__(self, *, bmi_chip_id: int = 0x00, who_am_i: int = 0x00) -> None:
        self.bmi_chip_id = bmi_chip_id
        self.who_am_i = who_am_i
        self.write_byte_data_calls: list[tuple[int, int, int]] = []
        self.read_byte_data_calls: list[tuple[int, int]] = []
        self.closed = False

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        self.write_byte_data_calls.append((address, register, value))

    def read_byte_data(self, address: int, register: int) -> int:
        self.read_byte_data_calls.append((address, register))
        if register == 0x00:
            return self.bmi_chip_id
        if register == 0x0F:
            return self.who_am_i
        raise AssertionError(f"Unexpected register read: {register:#x}")

    def close(self) -> None:
        self.closed = True


class FailingWriteBus(FakeBus):
    def write_byte_data(self, address: int, register: int, value: int) -> None:
        del address, register, value
        raise OSError("i2c write failed")


def test_detect_imu_kind_identifies_bmi160_chip_id() -> None:
    bus = FakeBus(bmi_chip_id=0xD1, who_am_i=0x00)

    kind = detect_imu_kind(bus=bus, address=0x68, expected_bmi_chip_id=0xD1)

    assert kind == "bmi160"


def test_detect_imu_kind_identifies_lsm6ds3_who_am_i() -> None:
    bus = FakeBus(bmi_chip_id=0x00, who_am_i=0x69)

    kind = detect_imu_kind(bus=bus, address=0x6A, expected_bmi_chip_id=0xD1)

    assert kind == "lsm6ds3"


def test_detect_imu_kind_prefers_lsm6ds3_identity_over_bmi_like_register_zero() -> None:
    bus = FakeBus(bmi_chip_id=0xD1, who_am_i=0x69)

    kind = detect_imu_kind(bus=bus, address=0x6A, expected_bmi_chip_id=0xD1)

    assert kind == "lsm6ds3"


def test_detect_imu_kind_rejects_unknown_imu() -> None:
    bus = FakeBus(bmi_chip_id=0x00, who_am_i=0x00)

    with pytest.raises(ValueError, match="Unsupported IMU"):
        detect_imu_kind(bus=bus, address=0x6A, expected_bmi_chip_id=0xD1)


def test_open_imu_reader_returns_lsm6ds3_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bus = FakeBus(bmi_chip_id=0x00, who_am_i=0x69)
    import imu.factory as factory

    monkeypatch.setattr(factory, "SMBus", lambda bus_index: fake_bus)

    reader = open_imu_reader(
        bus_index=1,
        address=0x6A,
        expected_bmi_chip_id=0xD1,
        sample_rate_hz=100.0,
        gyro_z_sign=1.0,
    )

    assert isinstance(reader, LSM6DS3Reader)
    assert fake_bus.closed is False


def test_open_imu_reader_returns_bmi160_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bus = FakeBus(bmi_chip_id=0xD1, who_am_i=0x00)
    import imu.factory as factory

    monkeypatch.setattr(factory, "SMBus", lambda bus_index: fake_bus)

    reader = open_imu_reader(
        bus_index=1,
        address=0x68,
        expected_bmi_chip_id=0xD1,
        sample_rate_hz=100.0,
        gyro_z_sign=1.0,
    )

    assert isinstance(reader, BMI160Reader)
    assert fake_bus.closed is False


def test_open_imu_reader_closes_bus_when_reader_initialization_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bus = FailingWriteBus(bmi_chip_id=0x00, who_am_i=0x69)
    import imu.factory as factory

    monkeypatch.setattr(factory, "SMBus", lambda bus_index: fake_bus)

    with pytest.raises(OSError, match="i2c write failed"):
        open_imu_reader(
            bus_index=1,
            address=0x6A,
            expected_bmi_chip_id=0xD1,
            sample_rate_hz=100.0,
            gyro_z_sign=1.0,
        )

    assert fake_bus.closed is True