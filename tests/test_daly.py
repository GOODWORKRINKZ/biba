from __future__ import annotations

import pytest

from bms.daly import DalyBMS


class FakeSerial:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.written: list[bytes] = []
        self.reset_calls = 0
        self.is_open = True

    def reset_input_buffer(self) -> None:
        self.reset_calls += 1

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def read(self, _: int) -> bytes:
        if self.responses:
            return self.responses.pop(0)
        return b""

    def close(self) -> None:
        self.is_open = False


def build_response(command: int, data: bytes) -> bytes:
    frame = bytes([0xA5, 0x01, command, 0x08]) + data
    return frame + bytes([sum(frame) & 0xFF])


def test_send_command_returns_valid_response_and_writes_request() -> None:
    response = build_response(0x90, bytes(8))
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms.serial_port = FakeSerial([response])

    result = bms._send_command(0x90)

    assert result == response
    assert bms.serial_port.reset_calls == 1
    assert bms.serial_port.written[0][:4] == bytes([0xA5, 0x40, 0x90, 0x08])


def test_get_soc_parses_voltage_current_and_soc() -> None:
    data = bytes.fromhex("00fc0000755d030f")
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms._send_command = lambda command: build_response(command, data)

    result = bms.get_soc()

    assert result == {"voltage": 25.2, "current": 4.5, "soc": 78.3}


def test_get_cell_voltages_collects_multiple_frames() -> None:
    first = build_response(0x95, bytes.fromhex("0dac0db600000000"))
    second = build_response(0x95, bytes.fromhex("0dc00dca0dd40000"))
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms.serial_port = FakeSerial([first, second, b""])

    result = bms.get_cell_voltages()

    assert result == [3.5, 3.51, 3.52, 3.53, 3.54]


def test_get_temperatures_applies_offset() -> None:
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms._send_command = lambda command: build_response(command, bytes([0, 45, 50, 0, 0, 0, 0, 0]))

    assert bms.get_temperatures() == [5.0, 10.0]


def test_read_state_aggregates_all_measurements() -> None:
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms.get_soc = lambda: {"voltage": 25.2, "current": 4.5, "soc": 78.3}
    bms.get_cell_voltages = lambda: [3.5, 3.52, 3.54]
    bms.get_temperatures = lambda: [22.0, 24.0]

    state = bms.read_state()

    assert state is not None
    assert state.voltage == 25.2
    assert state.current == 4.5
    assert state.soc == 78.3
    assert state.cells == [3.5, 3.52, 3.54]
    assert state.temperatures == [22.0, 24.0]
    assert state.min_cell == 3.5
    assert state.max_cell == 3.54
    assert state.delta == pytest.approx(0.04)


def test_send_command_returns_none_on_timeout() -> None:
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms.serial_port = FakeSerial([b""])

    result = bms._send_command(0x90)

    assert result is None


def test_send_command_returns_none_on_partial_response() -> None:
    partial = bytes([0xA5, 0x01, 0x90, 0x08, 0x00])
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms.serial_port = FakeSerial([partial])

    result = bms._send_command(0x90)

    assert result is None


def test_get_cell_voltages_returns_empty_on_no_data() -> None:
    bms = DalyBMS("/dev/ttyUSB0", 9600)
    bms.serial_port = FakeSerial([b""])

    result = bms.get_cell_voltages()

    assert result == []