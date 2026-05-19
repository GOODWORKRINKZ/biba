from __future__ import annotations

from crsf.protocol import FRAME_TYPE_BATTERY_SENSOR, FRAME_TYPE_GPS, parse_frame
from crsf.telemetry import BIBASystemMetrics, CRSFTelemetry, build_biba_system_metrics


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)


def test_send_battery_emits_valid_crsf_battery_frame() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_battery(voltage_v=25.2, current_a=4.5, capacity_mah=1234, remaining_pct=78)

    frame = serial_port.writes[-1]
    parsed = parse_frame(frame)

    assert parsed is not None
    frame_type, payload = parsed
    assert frame_type == FRAME_TYPE_BATTERY_SENSOR
    assert payload == bytes.fromhex("00fc002d0004d24e")


def test_send_battery_clamps_negative_and_out_of_range_values() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_battery(voltage_v=-1.0, current_a=-2.0, capacity_mah=0xFFFFFF + 100, remaining_pct=250)

    parsed = parse_frame(serial_port.writes[-1])

    assert parsed is not None
    _, payload = parsed
    assert payload == bytes.fromhex("00000000ffffff64")


def test_send_battery_preserves_status_bitmask_in_capacity_field() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_battery(voltage_v=25.2, current_a=4.5, capacity_mah=0b11110, remaining_pct=78)

    parsed = parse_frame(serial_port.writes[-1])

    assert parsed is not None
    _, payload = parsed
    assert payload == bytes.fromhex("00fc002d00001e4e")


def test_send_system_stats_emits_valid_crsf_gps_frame() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_system_stats(cpu_pct=45.0, mem_pct=67.0)

    frame = serial_port.writes[-1]
    parsed = parse_frame(frame)

    assert parsed is not None
    frame_type, payload = parsed
    assert frame_type == FRAME_TYPE_GPS
    assert len(payload) == 15
    # latitude = 1 at payload[0:4], longitude = 1 at payload[4:8]
    assert payload[0:4] == b'\x00\x00\x00\x01'
    assert payload[4:8] == b'\x00\x00\x00\x01'
    # groundspeed = 45 * 10 = 450 = 0x01C2 at payload[8:10]
    assert payload[8] == 0x01
    assert payload[9] == 0xC2
    # altitude = 1000 = 0x03E8 at payload[12:14]
    assert payload[12] == 0x03
    assert payload[13] == 0xE8
    # satellites = 67 at payload[14]
    assert payload[14] == 67


def test_send_system_stats_clamps_values() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_system_stats(cpu_pct=200.0, mem_pct=-5.0)

    parsed = parse_frame(serial_port.writes[-1])
    assert parsed is not None
    _, payload = parsed
    # cpu clamped: groundspeed = min(65535, 2000) = 2000 = 0x07D0
    assert payload[8] == 0x07
    assert payload[9] == 0xD0
    # mem clamped: satellites = max(0, -5) = 0
    assert payload[14] == 0


def test_send_system_stats_encodes_motor_currents_in_heading_and_altitude() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_system_stats(
        cpu_pct=12.0,
        mem_pct=34.0,
        left_motor_current_a=5.6,
        right_motor_current_a=7.8,
    )

    parsed = parse_frame(serial_port.writes[-1])

    assert parsed is not None
    frame_type, payload = parsed
    assert frame_type == FRAME_TYPE_GPS
    # heading = left current in deci-amps = 56 = 0x0038
    assert payload[10] == 0x00
    assert payload[11] == 0x38
    # altitude = 1000 offset + right current in deci-amps = 1000 + 78 = 1078 = 0x0436
    assert payload[12] == 0x04
    assert payload[13] == 0x36


def test_build_biba_system_metrics_uses_symmetric_wheel_current_ma() -> None:
    metrics = build_biba_system_metrics(
        cpu_pct=11.2,
        mem_pct=22.8,
        left_motor_current_a=1.234,
        right_motor_current_a=1.234,
    )

    assert metrics == BIBASystemMetrics(
        cpu_pct=11,
        mem_pct=23,
        left_wheel_current_ma=1234,
        right_wheel_current_ma=1234,
    )


def test_build_biba_system_metrics_clamps_negative_wheel_current_to_zero() -> None:
    metrics = build_biba_system_metrics(
        cpu_pct=12.0,
        mem_pct=34.0,
        left_motor_current_a=-0.5,
        right_motor_current_a=0.0,
    )

    assert metrics.left_wheel_current_ma == 0
    assert metrics.right_wheel_current_ma == 0


def test_send_system_stats_accepts_canonical_metrics_and_applies_transport_offset_only_in_payload() -> None:
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)
    metrics = BIBASystemMetrics(
        cpu_pct=30,
        mem_pct=40,
        left_wheel_current_ma=1500,
        right_wheel_current_ma=2700,
    )

    telemetry.send_system_stats(metrics=metrics)

    parsed = parse_frame(serial_port.writes[-1])
    assert parsed is not None
    _, payload = parsed

    assert payload[8:10] == bytes.fromhex("012c")
    assert payload[10:12] == bytes.fromhex("000f")
    assert payload[12:14] == bytes.fromhex("0403")
    assert metrics.right_wheel_current_ma == 2700


# ---------------------------------------------------------------------------
# Phase 05: battery current passed through send_battery()
# ---------------------------------------------------------------------------

def test_send_battery_encodes_ibat_correctly() -> None:
    """ibat_a is passed as current_a; verify it encodes correctly at 0.1 A units."""
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    # 18.0 A → CRSF current = 180 deci-amps = 0x00B4
    telemetry.send_battery(voltage_v=24.0, current_a=18.0, capacity_mah=0, remaining_pct=80)

    parsed = parse_frame(serial_port.writes[-1])
    assert parsed is not None
    _, payload = parsed
    # voltage (2 bytes) + current (2 bytes): current = 180 = 0x00B4
    assert payload[2:4] == bytes([0x00, 0xB4])


def test_send_battery_encodes_vbat_correctly() -> None:
    """vbat at 25.6 V → CRSF voltage = 256 deci-volts = 0x0100."""
    serial_port = FakeSerial()
    telemetry = CRSFTelemetry(serial_port)

    telemetry.send_battery(voltage_v=25.6, current_a=0.0, capacity_mah=0, remaining_pct=0)

    parsed = parse_frame(serial_port.writes[-1])
    assert parsed is not None
    _, payload = parsed
    # voltage = 256 = 0x0100
    assert payload[0:2] == bytes([0x01, 0x00])
