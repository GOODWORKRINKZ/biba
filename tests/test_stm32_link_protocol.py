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
    assert int(Command.SET_CONFIG) == 0x30
    assert int(Command.SET_MOTOR_AUDIO) == 0x40
    assert int(TelemetryId.SNAPSHOT) == 0x82


def test_build_motor_audio_matches_firmware_layout():
    """Payload layout mirrors biba_proto_motor_audio_t in biba_proto.h:

        uint16_t freq_hz[4];   // little-endian
        uint8_t  duty_q8[4];
        uint8_t  flags;
    """
    from stm32_link.protocol import (
        build_motor_audio,
        MOTOR_AUDIO_FLAG_AUDIO_MODE,
        MOTOR_AUDIO_FLAG_OUTPUTS_ENABLE,
    )

    raw = build_motor_audio(
        seq=42,
        freq_hz=(440, 554, 659, 880),
        duty_q8=(64, 96, 128, 200),
        flags=MOTOR_AUDIO_FLAG_AUDIO_MODE | MOTOR_AUDIO_FLAG_OUTPUTS_ENABLE,
    )
    parsed = parse_frame(raw)
    assert parsed.cmd == int(Command.SET_MOTOR_AUDIO)
    assert parsed.seq == 42
    freqs = struct.unpack("<HHHH", parsed.payload[:8])
    duties = struct.unpack("<BBBB", parsed.payload[8:12])
    flags = parsed.payload[12]
    assert freqs == (440, 554, 659, 880)
    assert duties == (64, 96, 128, 200)
    assert flags == 0b11


def test_build_motor_audio_silences_channel_with_zero_freq():
    from stm32_link.protocol import build_motor_audio

    raw = build_motor_audio(
        seq=1,
        freq_hz=(0, 0, 0, 0),
        duty_q8=(0, 0, 0, 0),
    )
    parsed = parse_frame(raw)
    assert parsed.payload[:8] == b"\x00" * 8
    assert parsed.payload[8:12] == b"\x00" * 4


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(seq=0, freq_hz=(0, 0, 0), duty_q8=(0, 0, 0, 0)),   # wrong length
        dict(seq=0, freq_hz=(0, 0, 0, 0), duty_q8=(0, 0, 0)),   # wrong length
        dict(seq=0, freq_hz=(0x10000, 0, 0, 0), duty_q8=(0, 0, 0, 0)),  # OOR freq
        dict(seq=0, freq_hz=(0, 0, 0, 0), duty_q8=(256, 0, 0, 0)),      # OOR duty
        dict(seq=0, freq_hz=(0, 0, 0, 0), duty_q8=(0, 0, 0, 0), flags=256),
    ],
)
def test_build_motor_audio_rejects_invalid_args(kwargs):
    from stm32_link.protocol import build_motor_audio

    with pytest.raises(ValueError):
        build_motor_audio(**kwargs)


# ---------------------------------------------------------------------------
# Phase 05: Telemetry struct — ibat, temperature, humidity round-trip
# ---------------------------------------------------------------------------

def test_telemetry_ibat_temperature_humidity_roundtrip() -> None:
    """New fields ibat_a, temperature_c, humidity_pct survive a to_bytes → from_bytes cycle."""
    tlm = Telemetry(
        vbat_v=24.0,
        ibat_a=12.345,
        temperature_c=27.5,
        humidity_pct=62.0,
    )
    frame = TelemetryFrame(seq=1, flags=0, telemetry=tlm)
    raw = frame.to_bytes()
    rt = TelemetryFrame.from_bytes(raw)

    assert rt.telemetry.ibat_a == pytest.approx(12.345, abs=1e-3)
    assert rt.telemetry.temperature_c == pytest.approx(27.5, abs=0.01)
    assert rt.telemetry.humidity_pct == pytest.approx(62.0, abs=0.5)


def test_telemetry_zero_new_fields_produce_zero_outputs() -> None:
    """Default Telemetry() (all zeros) → new fields decode as zero."""
    frame = TelemetryFrame(seq=0, flags=0, telemetry=Telemetry())
    rt = TelemetryFrame.from_bytes(frame.to_bytes())
    assert rt.telemetry.ibat_a == 0.0
    assert rt.telemetry.temperature_c == 0.0
    assert rt.telemetry.humidity_pct == 0.0


def test_telemetry_existing_fields_unaffected_by_new_fields() -> None:
    """Adding new fields does not shift or corrupt the original layout."""
    tlm = Telemetry(
        setpoint_left=0.5,
        current_left_a=5.0,
        vbat_v=25.2,
        gyro_z_dps=90.0,
        crsf_rssi=200,
        uptime_ms=999_000,
        ibat_a=3.0,
        temperature_c=25.0,
        humidity_pct=45.0,
    )
    rt = TelemetryFrame.from_bytes(TelemetryFrame(seq=2, flags=0, telemetry=tlm).to_bytes()).telemetry

    assert rt.setpoint_left == pytest.approx(0.5, abs=1e-4)
    assert rt.current_left_a == pytest.approx(5.0, abs=1e-3)
    assert rt.vbat_v == pytest.approx(25.2, abs=1e-3)
    assert rt.gyro_z_dps == pytest.approx(90.0, abs=0.01)
    assert rt.crsf_rssi == 200
    assert rt.uptime_ms == 999_000
    assert rt.ibat_a == pytest.approx(3.0, abs=1e-3)
    assert rt.temperature_c == pytest.approx(25.0, abs=0.01)
    assert rt.humidity_pct == pytest.approx(45.0, abs=0.5)


def test_telemetry_struct_is_still_48_bytes() -> None:
    """Total packed struct size must remain 48 bytes (backward-compatible)."""
    import struct as _struct
    from stm32_link.protocol import TELEMETRY_STRUCT, TELEMETRY_SIZE
    assert TELEMETRY_SIZE == 48
    assert _struct.calcsize(TELEMETRY_STRUCT) == 48


# ---------------------------------------------------------------------------
# Phase 07: wheel_rpm telemetry (IS-RPM ZC frequency carved from reserved[11])
# ---------------------------------------------------------------------------

def test_telemetry_size_still_48() -> None:
    """Phase 07: adding wheel_rpm fields must not drift struct size."""
    from stm32_link.protocol import TELEMETRY_SIZE
    assert TELEMETRY_SIZE == 48


def test_wheel_rpm_decode_300hz() -> None:
    """fields[20]=3000, fields[21]=1500 must decode to 300.0 / 150.0 Hz."""
    tlm = Telemetry(wheel_rpm_left_hz=300.0, wheel_rpm_right_hz=150.0)
    raw = TelemetryFrame(seq=11, flags=0, telemetry=tlm).to_bytes()
    rt = TelemetryFrame.from_bytes(raw)
    assert rt.telemetry.wheel_rpm_left_hz == pytest.approx(300.0, abs=0.05)
    assert rt.telemetry.wheel_rpm_right_hz == pytest.approx(150.0, abs=0.05)


def test_wheel_rpm_decode_zero() -> None:
    """Default zeros decode to 0.0 Hz (invalid / stopped sentinel)."""
    raw = TelemetryFrame(seq=0, flags=0, telemetry=Telemetry()).to_bytes()
    rt = TelemetryFrame.from_bytes(raw)
    assert rt.telemetry.wheel_rpm_left_hz == 0.0
    assert rt.telemetry.wheel_rpm_right_hz == 0.0


def test_wheel_rpm_encode_roundtrip() -> None:
    """Non-integer Hz values survive a to_bytes -> from_bytes cycle within 0.1 Hz."""
    tlm = Telemetry(wheel_rpm_left_hz=432.7, wheel_rpm_right_hz=428.1)
    rt = TelemetryFrame.from_bytes(
        TelemetryFrame(seq=3, flags=0, telemetry=tlm).to_bytes()
    )
    assert rt.telemetry.wheel_rpm_left_hz == pytest.approx(432.7, abs=0.1)
    assert rt.telemetry.wheel_rpm_right_hz == pytest.approx(428.1, abs=0.1)


def test_wheel_rpm_zero_invalid_encodes_zero_bytes() -> None:
    """Telemetry(wheel_rpm_left_hz=0.0) must place 0x0000 at the wheel_rpm slot.

    Layout inside packed payload "<hhhhHHhhhhhhBBbBIhhBHH7s":
      36 bytes precede the humidity_q8 byte; wheel_rpm_left_hz10 lives at
      payload offset 37, wheel_rpm_right_hz10 at 39. Frame header is 6 bytes
      (sync0, sync1, version, cmd, seq, flags), so absolute offsets are 43/45.
    """
    raw = TelemetryFrame(seq=0, flags=0, telemetry=Telemetry()).to_bytes()
    left_hz10 = struct.unpack("<H", raw[6 + 37 : 6 + 39])[0]
    right_hz10 = struct.unpack("<H", raw[6 + 39 : 6 + 41])[0]
    assert left_hz10 == 0
    assert right_hz10 == 0

