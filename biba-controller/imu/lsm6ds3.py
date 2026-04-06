"""ST LSM6DS3/LSM6DS33-class I2C IMU backend."""

from __future__ import annotations

import time

from imu import IMUReader, IMUSample


class LSM6DS3Reader(IMUReader):
    _REG_WHO_AM_I = 0x0F
    _REG_CTRL1_XL = 0x10
    _REG_CTRL2_G = 0x11
    _REG_CTRL3_C = 0x12
    _REG_GYRO_DATA = 0x22
    _WHO_AM_I = 0x69
    _CTRL3_C_BDU_IF_INC = 0x44
    _CTRL_ACCEL_2G = 0x00
    _CTRL_GYRO_245_DPS = 0x00
    _ACCEL_G_PER_LSB = 0.000061
    _GYRO_DPS_PER_LSB = 0.00875
    _ODR_BY_RATE = {
        12.5: 0x10,
        26.0: 0x20,
        52.0: 0x30,
        100.0: 0x40,
        104.0: 0x40,
        200.0: 0x50,
        208.0: 0x50,
        400.0: 0x60,
        416.0: 0x60,
        800.0: 0x70,
        833.0: 0x70,
        1600.0: 0x80,
        1660.0: 0x80,
    }

    def __init__(
        self,
        *,
        bus,
        address: int,
        sample_rate_hz: float,
        gyro_z_sign: float = 1.0,
        expected_who_am_i: int = _WHO_AM_I,
    ) -> None:
        self._bus = bus
        self._address = address
        self._sample_rate_hz = sample_rate_hz
        self._gyro_z_sign = gyro_z_sign
        self._expected_who_am_i = expected_who_am_i

    def initialize(self) -> None:
        who_am_i = self._bus.read_byte_data(self._address, self._REG_WHO_AM_I)
        if who_am_i != self._expected_who_am_i:
            raise ValueError(f"Unexpected LSM6DS3 WHO_AM_I {who_am_i:#x}")

        odr = self._ODR_BY_RATE.get(float(self._sample_rate_hz), self._ODR_BY_RATE[100.0])
        self._bus.write_byte_data(self._address, self._REG_CTRL3_C, self._CTRL3_C_BDU_IF_INC)
        self._bus.write_byte_data(self._address, self._REG_CTRL1_XL, odr | self._CTRL_ACCEL_2G)
        self._bus.write_byte_data(self._address, self._REG_CTRL2_G, odr | self._CTRL_GYRO_245_DPS)

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
        gyr_x = self._decode_axis_pair(raw[0], raw[1]) * self._GYRO_DPS_PER_LSB
        gyr_y = self._decode_axis_pair(raw[2], raw[3]) * self._GYRO_DPS_PER_LSB
        gyr_z = self._decode_axis_pair(raw[4], raw[5]) * self._GYRO_DPS_PER_LSB * self._gyro_z_sign
        acc_x = self._decode_axis_pair(raw[6], raw[7]) * self._ACCEL_G_PER_LSB
        acc_y = self._decode_axis_pair(raw[8], raw[9]) * self._ACCEL_G_PER_LSB
        acc_z = self._decode_axis_pair(raw[10], raw[11]) * self._ACCEL_G_PER_LSB
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