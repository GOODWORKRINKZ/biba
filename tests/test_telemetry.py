from __future__ import annotations

from crsf.protocol import FRAME_TYPE_BATTERY_SENSOR, parse_frame
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