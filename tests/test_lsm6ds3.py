from __future__ import annotations

import pytest

from imu.lsm6ds3 import LSM6DS3Reader


def _le16(value: int) -> list[int]:
    if value < 0:
        value = (1 << 16) + value
    return [value & 0xFF, (value >> 8) & 0xFF]


class FakeBus:
    def __init__(self, who_am_i: int = 0x69, sample_bytes: list[int] | None = None) -> None:
        self.who_am_i = who_am_i
        self.sample_bytes = sample_bytes or ([0] * 12)
        self.write_byte_data_calls: list[tuple[int, int, int]] = []
        self.read_byte_data_calls: list[tuple[int, int]] = []
        self.read_i2c_block_data_calls: list[tuple[int, int, int]] = []

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        self.write_byte_data_calls.append((address, register, value))

    def read_byte_data(self, address: int, register: int) -> int:
        self.read_byte_data_calls.append((address, register))
        if register == 0x0F:
            return self.who_am_i
        raise AssertionError(f"Unexpected register read: {register:#x}")

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        self.read_i2c_block_data_calls.append((address, register, length))
        if register == 0x22 and length == 12:
            return self.sample_bytes
        raise AssertionError(f"Unexpected block read: register={register:#x} length={length}")


def test_lsm6ds3_reader_initializes_sensor_and_validates_who_am_i() -> None:
    bus = FakeBus()

    reader = LSM6DS3Reader(bus=bus, address=0x6A, sample_rate_hz=100.0)
    reader.initialize()

    assert bus.read_byte_data_calls == [(0x6A, 0x0F)]
    assert (0x6A, 0x12, 0x44) in bus.write_byte_data_calls
    assert (0x6A, 0x10, 0x40) in bus.write_byte_data_calls
    assert (0x6A, 0x11, 0x40) in bus.write_byte_data_calls


def test_lsm6ds3_reader_rejects_unexpected_who_am_i() -> None:
    bus = FakeBus(who_am_i=0x00)
    reader = LSM6DS3Reader(bus=bus, address=0x6A, sample_rate_hz=100.0)

    with pytest.raises(ValueError, match="WHO_AM_I"):
        reader.initialize()


def test_lsm6ds3_reader_converts_raw_sensor_bytes() -> None:
    sample_bytes = (
        _le16(0)
        + _le16(0)
        + _le16(2286)
        + _le16(0)
        + _le16(0)
        + _le16(16393)
    )
    bus = FakeBus(sample_bytes=sample_bytes)
    reader = LSM6DS3Reader(bus=bus, address=0x6A, sample_rate_hz=100.0)
    reader.initialize()

    sample = reader.read(timestamp_monotonic_s=12.5)

    assert sample.valid is True
    assert sample.timestamp_monotonic_s == pytest.approx(12.5)
    assert sample.gyro_z_dps == pytest.approx(20.0, abs=0.05)
    assert sample.accel_z_g == pytest.approx(1.0, abs=0.005)