"""BMI160 I2C IMU backend."""

from __future__ import annotations

import time

from imu import IMUReader, IMUSample


class BMI160Reader(IMUReader):
    _REG_CHIP_ID = 0x00
    _REG_GYRO_DATA = 0x0C
    _REG_CMD = 0x7E
    _REG_ACC_CONF = 0x40
    _REG_ACC_RANGE = 0x41
    _REG_GYR_CONF = 0x42
    _REG_GYR_RANGE = 0x43
    _CMD_ACC_NORMAL = 0x11
    _CMD_GYR_NORMAL = 0x15
    _ACC_RANGE_2G = 0x03
    _GYR_RANGE_250_DPS = 0x03
    _ACC_LSB_PER_G = 16384.0
    _GYR_LSB_PER_DPS = 131.2
    _ODR_BY_RATE = {
        25.0: 0x06,
        50.0: 0x07,
        100.0: 0x08,
        200.0: 0x09,
        400.0: 0x0A,
        800.0: 0x0B,
        1600.0: 0x0C,
    }

    def __init__(
        self,
        *,
        bus,
        address: int,
        expected_chip_id: int,
        sample_rate_hz: float,
        gyro_z_sign: float = 1.0,
    ) -> None:
        self._bus = bus
        self._address = address
        self._expected_chip_id = expected_chip_id
        self._sample_rate_hz = sample_rate_hz
        self._gyro_z_sign = gyro_z_sign

    def initialize(self) -> None:
        chip_id = self._bus.read_byte_data(self._address, self._REG_CHIP_ID)
        if chip_id != self._expected_chip_id:
            raise ValueError(f"Unexpected BMI160 chip id {chip_id:#x}")

        odr = self._ODR_BY_RATE.get(float(self._sample_rate_hz), self._ODR_BY_RATE[100.0])
        self._bus.write_byte_data(self._address, self._REG_CMD, self._CMD_ACC_NORMAL)
        self._bus.write_byte_data(self._address, self._REG_CMD, self._CMD_GYR_NORMAL)
        self._bus.write_byte_data(self._address, self._REG_ACC_CONF, odr)
        self._bus.write_byte_data(self._address, self._REG_ACC_RANGE, self._ACC_RANGE_2G)
        self._bus.write_byte_data(self._address, self._REG_GYR_CONF, odr)
        self._bus.write_byte_data(self._address, self._REG_GYR_RANGE, self._GYR_RANGE_250_DPS)

    @staticmethod
    def _decode_axis_pair(lsb: int, msb: int) -> int:
        raw = (msb << 8) | lsb
        if raw & 0x8000:
            raw -= 0x10000
        return raw

    def read(self, timestamp_monotonic_s: float | None = None) -> IMUSample:
        if timestamp_monotonic_s is None:
            timestamp_monotonic_s = time.monotonic()

        raw = self._bus.read_i2c_block_data(self._address, self._REG_GYRO_DATA, 12)
        gyr_x = self._decode_axis_pair(raw[0], raw[1]) / self._GYR_LSB_PER_DPS
        gyr_y = self._decode_axis_pair(raw[2], raw[3]) / self._GYR_LSB_PER_DPS
        gyr_z = (self._decode_axis_pair(raw[4], raw[5]) / self._GYR_LSB_PER_DPS) * self._gyro_z_sign
        acc_x = self._decode_axis_pair(raw[6], raw[7]) / self._ACC_LSB_PER_G
        acc_y = self._decode_axis_pair(raw[8], raw[9]) / self._ACC_LSB_PER_G
        acc_z = self._decode_axis_pair(raw[10], raw[11]) / self._ACC_LSB_PER_G
        return IMUSample(
            accel_x_g=acc_x,
            accel_y_g=acc_y,
            accel_z_g=acc_z,
            gyro_x_dps=gyr_x,
            gyro_y_dps=gyr_y,
            gyro_z_dps=gyr_z,
            temperature_c=None,
            timestamp_monotonic_s=timestamp_monotonic_s,
            valid=True,
        )

    def close(self) -> None:
        close_fn = getattr(self._bus, "close", None)
        if callable(close_fn):
            close_fn()


def open_bmi160_reader(
    *,
    bus_index: int,
    address: int,
    expected_chip_id: int,
    sample_rate_hz: float,
    gyro_z_sign: float = 1.0,
) -> BMI160Reader:
    from smbus2 import SMBus

    reader = BMI160Reader(
        bus=SMBus(bus_index),
        address=address,
        expected_chip_id=expected_chip_id,
        sample_rate_hz=sample_rate_hz,
        gyro_z_sign=gyro_z_sign,
    )
    reader.initialize()
    return reader