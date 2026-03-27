from __future__ import annotations

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


def test_ads1115_motor_current_reader_converts_channel_voltage_to_current() -> None:
    bus = FakeSMBus(responses=[[0x40, 0x00], [0x20, 0x00]])
    reader = ADS1115MotorCurrentReader(
        bus=bus,
        address=0x48,
        left_channel=0,
        right_channel=1,
        gain="1",
        sample_rate_sps=128,
        left_calibration=MotorCurrentCalibration(zero_offset_v=0.5, amps_per_volt=10.0),
        right_calibration=MotorCurrentCalibration(zero_offset_v=0.25, amps_per_volt=8.0),
    )

    left_sample, right_sample = reader.read_currents()

    assert left_sample.valid is True
    assert right_sample.valid is True
    assert left_sample.current_a == 15.48
    assert right_sample.current_a == 6.192
    assert bus.write_calls[0][0:2] == (0x48, 0x01)
    assert bus.read_calls == [(0x48, 0x00, 2), (0x48, 0x00, 2)]


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
        left_channel=0,
        right_channel=1,
        gain="1",
        sample_rate_sps=128,
        left_calibration=MotorCurrentCalibration(),
        right_calibration=MotorCurrentCalibration(),
    )

    left_sample, right_sample = reader.read_currents()

    assert left_sample.valid is False
    assert right_sample.valid is False