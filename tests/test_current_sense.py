from __future__ import annotations

import importlib

from motors.current_sense import ADS1115MotorCurrentReader, MotorCurrentCalibration, NullMotorCurrentReader


class FakeSMBus:
    def __init__(self, conversion_responses: list[list[int]], config_responses: list[list[int]] | None = None) -> None:
        self.conversion_responses = conversion_responses
        self.config_responses = config_responses or []
        self.write_calls: list[tuple[int, int, list[int]]] = []
        self.read_calls: list[tuple[int, int, int]] = []

    def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None:
        self.write_calls.append((address, register, data))

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        self.read_calls.append((address, register, length))
        if register == 0x01:
            if self.config_responses:
                return self.config_responses.pop(0)
            return [0x80, 0x00]
        return self.conversion_responses.pop(0)

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
    bus = FakeSMBus(conversion_responses=[[0x40, 0x00], [0x20, 0x00]])
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
    assert bus.read_calls == [(0x48, 0x01, 2), (0x48, 0x00, 2), (0x48, 0x01, 2), (0x48, 0x00, 2)]


def test_ads1115_motor_current_reader_uses_reverse_channels_for_negative_duty() -> None:
    bus = FakeSMBus(conversion_responses=[[0x10, 0x00], [0x08, 0x00]])
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


def test_ads1115_motor_current_reader_waits_for_conversion_ready_bit() -> None:
    bus = FakeSMBus(
        conversion_responses=[[0x40, 0x00], [0x20, 0x00]],
        config_responses=[[0x00, 0x00], [0x80, 0x00], [0x00, 0x00], [0x80, 0x00]],
    )
    reader = ADS1115MotorCurrentReader(
        bus=bus,
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

    reader.read_currents(left_duty=0.5, right_duty=0.5)

    assert bus.read_calls == [
        (0x48, 0x01, 2),
        (0x48, 0x01, 2),
        (0x48, 0x00, 2),
        (0x48, 0x01, 2),
        (0x48, 0x01, 2),
        (0x48, 0x00, 2),
    ]


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


# ---------------------------------------------------------------------------
# Firmware channel-assignment alignment tests
# ---------------------------------------------------------------------------
# The firmware (target.h) hard-wires:
#   BIBA_ADS1115_CHAN_IS_L_FWD = 0   (AIN0)
#   BIBA_ADS1115_CHAN_IS_L_REV = 1   (AIN1)
#   BIBA_ADS1115_CHAN_IS_R_FWD = 2   (AIN2)
#   BIBA_ADS1115_CHAN_IS_R_REV = 3   (AIN3)
# The Pi-side reader must be configured with the same mapping.
# These tests guard against channel inversion regressions.

FIRMWARE_CHANNELS = dict(
    left_forward=0,
    left_reverse=1,
    right_forward=2,
    right_reverse=3,
)


def _make_reader_with_firmware_channels(
    bus: "FakeSMBus",
    left_calibration: MotorCurrentCalibration | None = None,
    right_calibration: MotorCurrentCalibration | None = None,
) -> ADS1115MotorCurrentReader:
    return ADS1115MotorCurrentReader(
        bus=bus,
        address=0x48,
        left_forward_channel=FIRMWARE_CHANNELS["left_forward"],
        left_reverse_channel=FIRMWARE_CHANNELS["left_reverse"],
        right_forward_channel=FIRMWARE_CHANNELS["right_forward"],
        right_reverse_channel=FIRMWARE_CHANNELS["right_reverse"],
        gain="1",
        sample_rate_sps=128,
        left_calibration=left_calibration or MotorCurrentCalibration(),
        right_calibration=right_calibration or MotorCurrentCalibration(),
    )


def test_firmware_channel_assignment_left_fwd_reads_ain0() -> None:
    """Forward left torque → ADS1115 AIN0 (channel 0) per firmware target.h."""
    bus = FakeSMBus(conversion_responses=[[0x40, 0x00], [0x00, 0x00]])
    reader = _make_reader_with_firmware_channels(bus)
    reader.read_currents(left_duty=1.0, right_duty=0.0)
    # First write should target channel 0 (MUX=100b = bits 14:12 of config word)
    first_cfg_msb = bus.write_calls[0][2][0]  # MSB of 2-byte config data
    mux = (first_cfg_msb >> 4) & 0x7
    assert mux == 4, f"expected MUX=100b (4) for channel 0, got {mux}"


def test_firmware_channel_assignment_left_rev_reads_ain1() -> None:
    """Reverse left torque → ADS1115 AIN1 (channel 1) per firmware target.h."""
    bus = FakeSMBus(conversion_responses=[[0x40, 0x00], [0x00, 0x00]])
    reader = _make_reader_with_firmware_channels(bus)
    reader.read_currents(left_duty=-1.0, right_duty=0.0)
    first_cfg_msb = bus.write_calls[0][2][0]
    mux = (first_cfg_msb >> 4) & 0x7
    assert mux == 5, f"expected MUX=101b (5) for channel 1, got {mux}"


def test_firmware_channel_assignment_right_fwd_reads_ain2() -> None:
    """Forward right torque → ADS1115 AIN2 (channel 2) per firmware target.h."""
    bus = FakeSMBus(conversion_responses=[[0x00, 0x00], [0x40, 0x00]])
    reader = _make_reader_with_firmware_channels(bus)
    reader.read_currents(left_duty=0.0, right_duty=1.0)
    # Right motor is the second conversion — check write_calls[1]
    second_cfg_msb = bus.write_calls[1][2][0]
    mux = (second_cfg_msb >> 4) & 0x7
    assert mux == 6, f"expected MUX=110b (6) for channel 2, got {mux}"


def test_firmware_channel_assignment_right_rev_reads_ain3() -> None:
    """Reverse right torque → ADS1115 AIN3 (channel 3) per firmware target.h."""
    bus = FakeSMBus(conversion_responses=[[0x00, 0x00], [0x40, 0x00]])
    reader = _make_reader_with_firmware_channels(bus)
    reader.read_currents(left_duty=0.0, right_duty=-1.0)
    second_cfg_msb = bus.write_calls[1][2][0]
    mux = (second_cfg_msb >> 4) & 0x7
    assert mux == 7, f"expected MUX=111b (7) for channel 3, got {mux}"


def test_firmware_calibration_8p5_amps_per_volt_fwd_2p5v() -> None:
    """IS_L_fwd=2.5 V, IS_L_rev=0 V → left current ≈ 2.5 × 8.5 = 21.25 A."""
    # 2.5 V at FSR ±4.096 V → raw = 2.5 / (4.096/32768) ≈ 20000
    lsb = 4.096 / 32768.0
    raw_fwd = int(round(2.5 / lsb))
    raw_bytes_fwd = [(raw_fwd >> 8) & 0xFF, raw_fwd & 0xFF]
    raw_bytes_zero = [0x00, 0x00]
    bus = FakeSMBus(conversion_responses=[raw_bytes_fwd, raw_bytes_zero])
    cal = MotorCurrentCalibration(zero_offset_v=0.0, amps_per_volt=8.5)
    reader = _make_reader_with_firmware_channels(bus, left_calibration=cal)
    left_sample, _ = reader.read_currents(left_duty=1.0, right_duty=0.0)
    assert left_sample.valid is True
    assert abs(left_sample.current_a - 21.25) < 0.1, (
        f"expected ~21.25 A, got {left_sample.current_a}"
    )


def test_firmware_calibration_8p5_amps_per_volt_rev_2p0v() -> None:
    """IS_L_rev=2.0 V, IS_L_fwd=0 V → left current ≈ 2.0 × 8.5 = 17.0 A (reverse)."""
    lsb = 4.096 / 32768.0
    raw_rev = int(round(2.0 / lsb))
    raw_bytes_rev = [(raw_rev >> 8) & 0xFF, raw_rev & 0xFF]
    raw_bytes_zero = [0x00, 0x00]
    bus = FakeSMBus(conversion_responses=[raw_bytes_rev, raw_bytes_zero])
    cal = MotorCurrentCalibration(zero_offset_v=0.0, amps_per_volt=8.5)
    reader = _make_reader_with_firmware_channels(bus, left_calibration=cal)
    left_sample, _ = reader.read_currents(left_duty=-1.0, right_duty=0.0)
    assert left_sample.valid is True
    assert abs(left_sample.current_a - 17.0) < 0.1, (
        f"expected ~17.0 A, got {left_sample.current_a}"
    )
