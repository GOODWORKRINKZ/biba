"""Tests for the Python side of the biba_proto SPI wire format.

The firmware has a matching C test-suite under
``firmware/test/test_biba_proto``; any divergence in either
implementation will break both this file and ``pio test -e native_test``.
"""

from __future__ import annotations

import struct

import pytest

from stm32_link import (
    Command,
    Flag,
    PROTOCOL_VERSION,
    FRAME_SIZE,
    PAYLOAD_MAX,
    TelemetryFrame,
    Telemetry,
    build_frame,
    crc16_ccitt,
    parse_frame,
)
from stm32_link.protocol import (
    ProtocolError,
    TelemetryId,
    build_ping,
    build_setpoint,
    build_arm,
)


def test_crc16_matches_classic_ccitt_vector():
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_frame_size_is_64_and_header_is_known_offset():
    frame = build_frame(Command.PING, seq=7)
    assert len(frame) == FRAME_SIZE
    assert frame[0] == 0xBA
    assert frame[1] == 0xBB
    assert frame[2] == PROTOCOL_VERSION
    assert frame[3] == int(Command.PING)
    assert frame[4] == 7


def test_build_frame_rejects_oversized_payload():
    with pytest.raises(ProtocolError):
        build_frame(Command.SET_CONFIG, payload=b"\x00" * (PAYLOAD_MAX + 1))


def test_parse_frame_round_trips():
    raw = build_frame(
        Command.SET_SETPOINT,
        seq=42,
        flags=int(Flag.ARMED | Flag.CRSF_ALIVE),
        payload=b"\x10\x11\x12\x13\x14\x15",
    )
    parsed = parse_frame(raw)
    assert parsed.version == PROTOCOL_VERSION
    assert parsed.cmd == int(Command.SET_SETPOINT)
    assert parsed.seq == 42
    assert parsed.flags == int(Flag.ARMED | Flag.CRSF_ALIVE)
    assert parsed.payload == b"\x10\x11\x12\x13\x14\x15"


@pytest.mark.parametrize(
    "mutate,expected_error",
    [
        (lambda b: bytes([b[0] ^ 0xFF]) + b[1:], "sync"),
        (lambda b: b[:2] + bytes([0xEE]) + b[3:], "version"),
        (lambda b: b[:-1] + bytes([b[-1] ^ 0xAA]), "CRC"),
    ],
)
def test_parse_frame_rejects_corrupted_bytes(mutate, expected_error):
    raw = build_frame(Command.PING, seq=1)
    with pytest.raises(ProtocolError) as excinfo:
        parse_frame(mutate(raw))
    assert expected_error.lower() in str(excinfo.value).lower()


def test_parse_frame_rejects_wrong_size():
    with pytest.raises(ProtocolError):
        parse_frame(b"\x00" * (FRAME_SIZE - 1))


def test_build_setpoint_encodes_two_little_endian_q15():
    raw = build_setpoint(seq=3, left=0.5, right=-0.25)
    parsed = parse_frame(raw)
    assert parsed.cmd == int(Command.SET_SETPOINT)
    left, right = struct.unpack("<hh", parsed.payload[:4])
    assert left == pytest.approx(int(round(0.5 * 32767)))
    assert right == pytest.approx(int(round(-0.25 * 32767)))


def test_build_ping_and_arm_helpers():
    assert parse_frame(build_ping(1)).cmd == int(Command.PING)
    assert parse_frame(build_arm(1, True)).cmd == int(Command.ARM)
    assert parse_frame(build_arm(1, False)).cmd == int(Command.DISARM)


def test_telemetry_frame_roundtrip():
    tlm = Telemetry(
        setpoint_left=0.25,
        setpoint_right=-0.5,
        current_left_a=3.2,
        current_right_a=-0.45,
        vbat_v=24.8,
        rail_12v_v=11.95,
        gyro_z_dps=-45.0,
        crsf_rssi=185,
        crsf_link_quality=99,
        crsf_snr_db=12,
        error_flags=int(Flag.CRSF_ALIVE | Flag.ARMED),
        uptime_ms=1_234_567,
    )
    frame = TelemetryFrame(seq=7, flags=int(Flag.ARMED), telemetry=tlm)
    raw = frame.to_bytes()
    assert len(raw) == FRAME_SIZE

    round_tripped = TelemetryFrame.from_bytes(raw)
    assert round_tripped.seq == 7
    assert round_tripped.flags == int(Flag.ARMED)
    out = round_tripped.telemetry
    assert out.setpoint_left == pytest.approx(0.25, abs=1e-4)
    assert out.setpoint_right == pytest.approx(-0.5, abs=1e-4)
    assert out.current_left_a == pytest.approx(3.2, abs=1e-3)
    assert out.current_right_a == pytest.approx(-0.45, abs=1e-3)
    assert out.vbat_v == pytest.approx(24.8, abs=1e-3)
    assert out.gyro_z_dps == pytest.approx(-45.0, abs=1e-2)
    assert out.crsf_rssi == 185
    assert out.crsf_link_quality == 99
    assert out.crsf_snr_db == 12
    assert out.uptime_ms == 1_234_567


def test_telemetry_rejects_non_snapshot_command():
    # Craft a frame with an unexpected command code but otherwise valid layout.
    raw = build_frame(Command.PING, seq=0, payload=b"\x00" * 48)
    with pytest.raises(ProtocolError):
        TelemetryFrame.from_bytes(raw)


def test_flag_values_match_firmware_bits():
    # Ensure we haven't drifted from biba_proto.h.
    assert int(Flag.FAILSAFE) == 1 << 0
    assert int(Flag.ARMED) == 1 << 1
    assert int(Flag.CRSF_ALIVE) == 1 << 2
    assert int(Flag.CURRENT_LIMIT) == 1 << 3
    assert int(Flag.POWER_LIMIT) == 1 << 4


def test_command_values_match_firmware():
    assert int(Command.PING) == 0x01
    assert int(Command.SET_SETPOINT) == 0x10
    assert int(Command.GET_TELEMETRY) == 0x11
    assert int(Command.ARM) == 0x20
    assert int(Command.DISARM) == 0x21
    assert int(TelemetryId.SNAPSHOT) == 0x82
