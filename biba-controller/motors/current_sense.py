"""Motor current-sense readers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from motors.current_control import MotorCurrentSample


LOGGER = logging.getLogger("biba-controller")


class MotorCurrentReader:
    """Interface for left/right motor current readers."""

    def read_currents(self, left_duty: float = 0.0, right_duty: float = 0.0) -> tuple[MotorCurrentSample, MotorCurrentSample]:
        del left_duty, right_duty
        raise NotImplementedError

    def close(self) -> None:
        pass


class NullMotorCurrentReader(MotorCurrentReader):
    """Disabled or unavailable current-sense backend."""

    def read_currents(self, left_duty: float = 0.0, right_duty: float = 0.0) -> tuple[MotorCurrentSample, MotorCurrentSample]:
        del left_duty, right_duty
        invalid = MotorCurrentSample(current_a=None, valid=False)
        return invalid, invalid


@dataclass(frozen=True)
class MotorCurrentCalibration:
    """Linear calibration parameters for one motor current-sense input."""

    zero_offset_v: float = 0.0
    amps_per_volt: float = 1.0


class ADS1115MotorCurrentReader(MotorCurrentReader):
    """Read left and right motor current via directional ADS1115 single-ended channels."""

    _REG_CONVERSION = 0x00
    _REG_CONFIG = 0x01
    _OS_SINGLE = 0x8000
    _MUX_BY_CHANNEL = {
        0: 0x4000,
        1: 0x5000,
        2: 0x6000,
        3: 0x7000,
    }
    _PGA_BY_GAIN = {
        "2/3": (0x0000, 6.144),
        "1": (0x0200, 4.096),
        "2": (0x0400, 2.048),
        "4": (0x0600, 1.024),
        "8": (0x0800, 0.512),
        "16": (0x0A00, 0.256),
    }
    _DR_BY_SPS = {
        8: 0x0000,
        16: 0x0020,
        32: 0x0040,
        64: 0x0060,
        128: 0x0080,
        250: 0x00A0,
        475: 0x00C0,
        860: 0x00E0,
    }

    def __init__(
        self,
        bus,
        address: int,
        left_forward_channel: int,
        left_reverse_channel: int,
        right_forward_channel: int,
        right_reverse_channel: int,
        gain: str,
        sample_rate_sps: int,
        left_calibration: MotorCurrentCalibration,
        right_calibration: MotorCurrentCalibration,
    ) -> None:
        channels = (
            left_forward_channel,
            left_reverse_channel,
            right_forward_channel,
            right_reverse_channel,
        )
        if any(channel not in self._MUX_BY_CHANNEL for channel in channels):
            raise ValueError("ADS1115 channels must be in the range 0..3")
        if gain not in self._PGA_BY_GAIN:
            raise ValueError(f"Unsupported ADS1115 gain: {gain}")
        if sample_rate_sps not in self._DR_BY_SPS:
            raise ValueError(f"Unsupported ADS1115 sample rate: {sample_rate_sps}")

        self._bus = bus
        self._address = address
        self._left_forward_channel = left_forward_channel
        self._left_reverse_channel = left_reverse_channel
        self._right_forward_channel = right_forward_channel
        self._right_reverse_channel = right_reverse_channel
        self._pga_config, self._full_scale_v = self._PGA_BY_GAIN[gain]
        self._sample_rate_config = self._DR_BY_SPS[sample_rate_sps]
        self._left_calibration = left_calibration
        self._right_calibration = right_calibration

    def _read_channel_sample(self, channel: int) -> tuple[int, float]:
        config_value = (
            self._OS_SINGLE
            | self._MUX_BY_CHANNEL[channel]
            | self._pga_config
            | 0x0100
            | self._sample_rate_config
            | 0x0003
        )
        self._bus.write_i2c_block_data(
            self._address,
            self._REG_CONFIG,
            [(config_value >> 8) & 0xFF, config_value & 0xFF],
        )
        raw_bytes = self._bus.read_i2c_block_data(self._address, self._REG_CONVERSION, 2)
        raw = int.from_bytes(bytes(raw_bytes), byteorder="big", signed=True)
        voltage_v = (raw / 32768.0) * self._full_scale_v
        return raw, voltage_v

    @staticmethod
    def _select_channel(forward_channel: int, reverse_channel: int, duty: float) -> int:
        return forward_channel if duty >= 0.0 else reverse_channel

    @staticmethod
    def _sample_from_voltage(
        voltage_v: float,
        raw_adc: int,
        channel: int,
        calibration: MotorCurrentCalibration,
    ) -> MotorCurrentSample:
        current_a = max(0.0, (voltage_v - calibration.zero_offset_v) * calibration.amps_per_volt)
        return MotorCurrentSample(current_a=current_a, valid=True, voltage_v=voltage_v, raw_adc=raw_adc, channel=channel)

    def read_currents(self, left_duty: float = 0.0, right_duty: float = 0.0) -> tuple[MotorCurrentSample, MotorCurrentSample]:
        left_channel = self._select_channel(self._left_forward_channel, self._left_reverse_channel, left_duty)
        right_channel = self._select_channel(self._right_forward_channel, self._right_reverse_channel, right_duty)
        try:
            left_raw_adc, left_voltage_v = self._read_channel_sample(left_channel)
            right_raw_adc, right_voltage_v = self._read_channel_sample(right_channel)
        except Exception as exc:
            LOGGER.warning("Failed to read ADS1115 motor currents: %s", exc)
            invalid = MotorCurrentSample(current_a=None, valid=False)
            return invalid, invalid

        return (
            self._sample_from_voltage(left_voltage_v, left_raw_adc, left_channel, self._left_calibration),
            self._sample_from_voltage(right_voltage_v, right_raw_adc, right_channel, self._right_calibration),
        )

    def close(self) -> None:
        close_fn = getattr(self._bus, "close", None)
        if callable(close_fn):
            close_fn()


def open_ads1115_current_reader(
    *,
    address: int,
    left_forward_channel: int,
    left_reverse_channel: int,
    right_forward_channel: int,
    right_reverse_channel: int,
    gain: str,
    sample_rate_sps: int,
    left_calibration: MotorCurrentCalibration,
    right_calibration: MotorCurrentCalibration,
) -> ADS1115MotorCurrentReader:
    """Create an ADS1115 current reader using the system I2C bus."""

    from smbus2 import SMBus

    return ADS1115MotorCurrentReader(
        bus=SMBus(1),
        address=address,
        left_forward_channel=left_forward_channel,
        left_reverse_channel=left_reverse_channel,
        right_forward_channel=right_forward_channel,
        right_reverse_channel=right_reverse_channel,
        gain=gain,
        sample_rate_sps=sample_rate_sps,
        left_calibration=left_calibration,
        right_calibration=right_calibration,
    )