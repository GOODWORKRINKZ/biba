"""CRSF frame helpers used by the BiBa controller."""

from __future__ import annotations

from typing import Optional

CRSF_SYNC = 0xC8
CRSF_MAX_FRAME_SIZE = 64

FRAME_TYPE_GPS = 0x02
FRAME_TYPE_BATTERY_SENSOR = 0x08
FRAME_TYPE_LINK_STATISTICS = 0x14
FRAME_TYPE_RC_CHANNELS_PACKED = 0x16


def crc8_dvb_s2(data: bytes) -> int:
    """Calculate CRSF CRC8 using the DVB-S2 polynomial."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0xD5) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_frame(frame_type: int, payload: bytes) -> bytes:
    """Build a CRSF frame including sync, length, type, payload, and CRC."""
    body = bytes([frame_type]) + payload
    length = len(body) + 1
    crc = crc8_dvb_s2(body)
    return bytes([CRSF_SYNC, length]) + body + bytes([crc])


def parse_frame(frame: bytes) -> Optional[tuple[int, bytes]]:
    """Validate and unpack a CRSF frame.

    Returns None when the frame is malformed or the CRC check fails.
    """
    if len(frame) < 5:
        return None
    if frame[0] != CRSF_SYNC:
        return None

    expected_length = frame[1]
    if expected_length < 2:
        return None
    if len(frame) != expected_length + 2:
        return None

    body = frame[2:-1]
    if crc8_dvb_s2(body) != frame[-1]:
        return None

    frame_type = body[0]
    payload = body[1:]
    return frame_type, payload


def pop_frame_from_buffer(buffer: bytearray) -> Optional[bytes]:
    """Extract one CRSF frame from a byte buffer if a complete frame is present."""
    while buffer and buffer[0] != CRSF_SYNC:
        buffer.pop(0)

    if len(buffer) < 2:
        return None

    frame_length = buffer[1] + 2
    if frame_length > CRSF_MAX_FRAME_SIZE:
        buffer.pop(0)
        return None
    if len(buffer) < frame_length:
        return None

    raw = bytes(buffer[:frame_length])
    del buffer[:frame_length]
    return raw
