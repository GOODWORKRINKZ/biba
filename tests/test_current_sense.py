from __future__ import annotations

import importlib

from motors.current_sense import ADS1115MotorCurrentReader, MotorCurrentCalibration, NullMotorCurrentReader


class FakeSMBus:
    def __init__(self, responses: list[list[int]]) -> None:
        self.responses = responses
        self.write_calls: list[tuple[int, int, list[int]]] = []
        self.read_calls: list[tuple[int, int, int]] = []

    def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None:
        self.write_calls.append((address, register, data))

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        self.read_calls.append((address, register, length))
        return self.responses.pop(0)

    def close(self) -> None:
        pass


def test_null_motor_current_reader_returns_invalid_samples() -> None:
    reader = NullMotorCurrentReader()

    left_sample, right_sample = reader.read_currents()

    assert left_sample.valid is False
    assert right_sample.valid is False
    assert left_sample.current_a is None
    assert right_sample.current_a is None
    assert left_sample.voltage_v is None
    assert right_sample.voltage_v is None
    assert left_sample.raw_adc is None
    assert right_sample.raw_adc is None
    assert left_sample.channel is None
    assert right_sample.channel is None


def test_ads1115_motor_current_reader_uses_forward_channels_for_positive_duty() -> None:
    bus = FakeSMBus(responses=[[0x40, 0x00], [0x20, 0x00]])
    reader = ADS1115MotorCurrentReader(
        bus=bus,
        address=0x48,
        left_forward_channel=2,
        left_reverse_channel=3,
        right_forward_channel=0,
        right_reverse_channel=1,
        gain="1",
        sample_rate_sps=128,
        left_calibration=MotorCurrentCalibration(zero_offset_v=0.5, amps_per_volt=10.0),
        right_calibration=MotorCurrentCalibration(zero_offset_v=0.25, amps_per_volt=8.0),
    )

    left_sample, right_sample = reader.read_currents(left_duty=0.7, right_duty=0.2)

    assert left_sample.valid is True
    assert right_sample.valid is True
    assert left_sample.current_a == 15.48
    assert right_sample.current_a == 6.192
    assert left_sample.voltage_v == 2.048
    assert right_sample.voltage_v == 1.024
    assert left_sample.raw_adc == 16384
    assert right_sample.raw_adc == 8192
    assert left_sample.channel == 2
    assert right_sample.channel == 0
    assert bus.write_calls[0][0:2] == (0x48, 0x01)
    assert bus.write_calls[0][2] == [0xE3, 0x83]
    assert bus.write_calls[1][2] == [0xC3, 0x83]
    assert bus.read_calls == [(0x48, 0x00, 2), (0x48, 0x00, 2)]


def test_ads1115_motor_current_reader_uses_reverse_channels_for_negative_duty() -> None:
    bus = FakeSMBus(responses=[[0x10, 0x00], [0x08, 0x00]])
    reader = ADS1115MotorCurrentReader(
        bus=bus,
        address=0x48,
        left_forward_channel=2,
        left_reverse_channel=3,
        right_forward_channel=0,
        right_reverse_channel=1,
        gain="1",
        sample_rate_sps=128,
        left_calibration=MotorCurrentCalibration(zero_offset_v=0.0, amps_per_volt=10.0),
        right_calibration=MotorCurrentCalibration(zero_offset_v=0.0, amps_per_volt=10.0),
    )

    left_sample, right_sample = reader.read_currents(left_duty=-0.4, right_duty=-0.9)

    assert left_sample.channel == 3
    assert right_sample.channel == 1
    assert left_sample.current_a == 5.12
    assert right_sample.current_a == 2.56
    assert bus.write_calls[0][2] == [0xF3, 0x83]
    assert bus.write_calls[1][2] == [0xD3, 0x83]


def test_ads1115_motor_current_reader_returns_invalid_samples_on_bus_error() -> None:
    class BrokenSMBus:
        def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None:
            del address, register, data

        def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
            del address, register, length
            raise OSError("i2c read failed")

    reader = ADS1115MotorCurrentReader(
        bus=BrokenSMBus(),
        address=0x48,
        left_forward_channel=2,
        left_reverse_channel=3,
        right_forward_channel=0,
        right_reverse_channel=1,
        gain="1",
        sample_rate_sps=128,
        left_calibration=MotorCurrentCalibration(),
        right_calibration=MotorCurrentCalibration(),
    )

    left_sample, right_sample = reader.read_currents()

    assert left_sample.valid is False
    assert right_sample.valid is False
    assert left_sample.voltage_v is None
    assert right_sample.voltage_v is None
    assert left_sample.raw_adc is None
    assert right_sample.raw_adc is None
    assert left_sample.channel is None
    assert right_sample.channel is None


def test_default_configured_ads1115_sample_rate_is_supported(monkeypatch) -> None:
    monkeypatch.delenv("MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ", raising=False)
    config = importlib.import_module("config")
    config = importlib.reload(config)

    assert int(round(config.MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ)) in ADS1115MotorCurrentReader._DR_BY_SPS