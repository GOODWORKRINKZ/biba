from __future__ import annotations

from crsf.protocol import FRAME_TYPE_BATTERY_SENSOR, FRAME_TYPE_GPS, parse_frame
from crsf.telemetry import CRSFTelemetry


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