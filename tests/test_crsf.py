from __future__ import annotations

import pytest

from crsf.protocol import CRSF_MAX_FRAME_SIZE, FRAME_TYPE_RC_CHANNELS_PACKED, build_frame, parse_frame, pop_frame_from_buffer
from crsf.receiver import CRSFReceiver


def pack_channels(channels: list[int]) -> bytes:
    packed = 0
    for index, value in enumerate(channels):
        packed |= (value & 0x7FF) << (index * 11)
    return packed.to_bytes(22, byteorder="little")


def test_build_frame_round_trips_through_parser() -> None:
    payload = b"\x01\x02\x03\x04"

    frame = build_frame(FRAME_TYPE_RC_CHANNELS_PACKED, payload)

    assert frame[0] == 0xC8
    assert frame[1] == len(payload) + 2
    assert parse_frame(frame) == (FRAME_TYPE_RC_CHANNELS_PACKED, payload)


def test_parse_frame_rejects_crc_mismatch() -> None:
    frame = bytearray(build_frame(FRAME_TYPE_RC_CHANNELS_PACKED, b"\x10\x20"))
    frame[-1] ^= 0xFF

    assert parse_frame(bytes(frame)) is None


def test_pop_frame_from_buffer_skips_noise_and_oversized_frames() -> None:
    valid_frame = build_frame(FRAME_TYPE_RC_CHANNELS_PACKED, b"\xAA\xBB")
    buffer = bytearray(b"\x00\x01")
    buffer.extend([0xC8, CRSF_MAX_FRAME_SIZE])
    buffer.extend(valid_frame)

    assert pop_frame_from_buffer(buffer) is None
    assert pop_frame_from_buffer(buffer) == valid_frame
    assert buffer == bytearray()


def test_parse_channels_unpacks_16_values() -> None:
    raw_channels = [172, 300, 600, 900, 992, 1200, 1400, 1600, 1811, 500, 700, 800, 1000, 1100, 1300, 1500]

    parsed = CRSFReceiver.parse_channels(pack_channels(raw_channels))

    assert parsed == raw_channels


def test_parse_channels_rejects_short_payload() -> None:
    with pytest.raises(ValueError, match="at least 22 bytes"):
        CRSFReceiver.parse_channels(b"\x00" * 21)


def test_get_channels_normalizes_channel_values() -> None:
    receiver = CRSFReceiver("/dev/null", 420000)
    raw_channels = [172, 992, 1811] + [992] * 13
    receiver.read_frame = lambda: (FRAME_TYPE_RC_CHANNELS_PACKED, pack_channels(raw_channels))

    channels = receiver.get_channels()

    assert channels is not None
    assert channels[0] == pytest.approx(-1.0)
    assert channels[1] == pytest.approx(0.0, abs=0.001)
    assert channels[2] == pytest.approx(1.0)
