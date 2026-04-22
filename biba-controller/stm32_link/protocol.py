"""Pure-Python implementation of the biba_proto SPI wire format.

Keep this module in lock-step with
``firmware/src/proto/biba_proto.h``. The bundled unit tests
check CRC vectors and telemetry round-trips against fixed byte sequences
so that a change on one side without a matching change on the other
trips CI immediately.
"""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass, field
from typing import Tuple


PROTOCOL_VERSION = 0x01

FRAME_SIZE = 64
HEADER_SIZE = 8
CRC_SIZE = 2
PAYLOAD_MAX = FRAME_SIZE - HEADER_SIZE - CRC_SIZE  # 54

_SYNC_0 = 0xBA
_SYNC_1 = 0xBB


class Flag(enum.IntFlag):
    """Bit flags used in both request and telemetry frames."""

    NONE = 0
    FAILSAFE = 1 << 0
    ARMED = 1 << 1
    CRSF_ALIVE = 1 << 2
    CURRENT_LIMIT = 1 << 3
    POWER_LIMIT = 1 << 4


class Command(enum.IntEnum):
    """Request codes recognised by the STM32 firmware."""

    PING = 0x01
    SET_SETPOINT = 0x10
    GET_TELEMETRY = 0x11
    ARM = 0x20
    DISARM = 0x21
    SET_CONFIG = 0x30
    PLAY_TONE = 0x40


class TelemetryId(enum.IntEnum):
    PONG = 0x81
    SNAPSHOT = 0x82
    ERROR = 0x8F


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, xorout 0."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class ProtocolError(ValueError):
    """Raised when a frame fails structural or CRC validation."""


@dataclass
class Frame:
    version: int = PROTOCOL_VERSION
    cmd: int = 0
    seq: int = 0
    flags: int = 0
    payload: bytes = b""

    def __post_init__(self) -> None:
        if len(self.payload) > PAYLOAD_MAX:
            raise ProtocolError(
                f"payload length {len(self.payload)} exceeds {PAYLOAD_MAX}"
            )


def build_frame(
    cmd: int,
    seq: int = 0,
    flags: int = 0,
    payload: bytes = b"",
    *,
    version: int = PROTOCOL_VERSION,
) -> bytes:
    """Serialise a frame into the fixed FRAME_SIZE byte layout."""
    if len(payload) > PAYLOAD_MAX:
        raise ProtocolError(
            f"payload length {len(payload)} exceeds {PAYLOAD_MAX}"
        )
    buffer = bytearray(FRAME_SIZE)
    buffer[0] = _SYNC_0
    buffer[1] = _SYNC_1
    buffer[2] = version & 0xFF
    buffer[3] = cmd & 0xFF
    buffer[4] = seq & 0xFF
    buffer[5] = flags & 0xFF
    buffer[6] = len(payload)
    buffer[7] = 0  # reserved
    buffer[HEADER_SIZE : HEADER_SIZE + len(payload)] = payload
    crc = crc16_ccitt(bytes(buffer[: FRAME_SIZE - CRC_SIZE]))
    buffer[FRAME_SIZE - 2] = crc & 0xFF
    buffer[FRAME_SIZE - 1] = (crc >> 8) & 0xFF
    return bytes(buffer)


def parse_frame(buffer: bytes) -> Frame:
    """Validate and decode a FRAME_SIZE byte buffer coming off MISO."""
    if len(buffer) != FRAME_SIZE:
        raise ProtocolError(f"expected {FRAME_SIZE} bytes, got {len(buffer)}")
    if buffer[0] != _SYNC_0 or buffer[1] != _SYNC_1:
        raise ProtocolError("sync mismatch")
    if buffer[2] != PROTOCOL_VERSION:
        raise ProtocolError(
            f"protocol version mismatch: firmware={buffer[2]:#x}, expected={PROTOCOL_VERSION:#x}"
        )
    payload_len = buffer[6]
    if payload_len > PAYLOAD_MAX:
        raise ProtocolError(f"payload length {payload_len} exceeds {PAYLOAD_MAX}")
    crc = crc16_ccitt(bytes(buffer[: FRAME_SIZE - CRC_SIZE]))
    have = buffer[FRAME_SIZE - 2] | (buffer[FRAME_SIZE - 1] << 8)
    if crc != have:
        raise ProtocolError(f"CRC mismatch: want {crc:#06x}, got {have:#06x}")
    payload = bytes(buffer[HEADER_SIZE : HEADER_SIZE + payload_len])
    return Frame(
        version=buffer[2],
        cmd=buffer[3],
        seq=buffer[4],
        flags=buffer[5],
        payload=payload,
    )


# --- Telemetry payload --------------------------------------------------

# Matches biba_proto_telemetry_t packed layout byte-for-byte.
# "<" = little-endian, no padding because of __attribute__((packed)).
TELEMETRY_STRUCT = "<hhhhHHhhhhhhBBbBI16s"
TELEMETRY_SIZE = struct.calcsize(TELEMETRY_STRUCT)
assert TELEMETRY_SIZE == 48, f"telemetry size drifted: {TELEMETRY_SIZE}"


@dataclass
class Telemetry:
    setpoint_left: float = 0.0      # -1..+1
    setpoint_right: float = 0.0
    current_left_a: float = 0.0
    current_right_a: float = 0.0
    vbat_v: float = 0.0
    rail_12v_v: float = 0.0
    gyro_x_dps: float = 0.0
    gyro_y_dps: float = 0.0
    gyro_z_dps: float = 0.0
    accel_x_g: float = 0.0
    accel_y_g: float = 0.0
    accel_z_g: float = 0.0
    crsf_rssi: int = 0
    crsf_link_quality: int = 0
    crsf_snr_db: int = 0
    error_flags: int = 0
    uptime_ms: int = 0


def _to_q15(value: float) -> int:
    return max(-32768, min(32767, int(round(value * 32767.0))))


@dataclass
class TelemetryFrame:
    seq: int
    flags: int
    telemetry: Telemetry = field(default_factory=Telemetry)

    @classmethod
    def from_bytes(cls, buffer: bytes) -> "TelemetryFrame":
        frame = parse_frame(buffer)
        if frame.cmd not in (TelemetryId.SNAPSHOT, TelemetryId.PONG, TelemetryId.ERROR):
            raise ProtocolError(f"unexpected telemetry cmd {frame.cmd:#x}")
        if len(frame.payload) < TELEMETRY_SIZE:
            raise ProtocolError(
                f"telemetry payload too short: {len(frame.payload)} < {TELEMETRY_SIZE}"
            )
        payload = frame.payload[:TELEMETRY_SIZE]
        fields: Tuple = struct.unpack(TELEMETRY_STRUCT, payload)
        tlm = Telemetry(
            setpoint_left=fields[0] / 32767.0,
            setpoint_right=fields[1] / 32767.0,
            current_left_a=fields[2] / 1000.0,
            current_right_a=fields[3] / 1000.0,
            vbat_v=fields[4] / 1000.0,
            rail_12v_v=fields[5] / 1000.0,
            gyro_x_dps=fields[6] / 100.0,
            gyro_y_dps=fields[7] / 100.0,
            gyro_z_dps=fields[8] / 100.0,
            accel_x_g=fields[9] / 1000.0,
            accel_y_g=fields[10] / 1000.0,
            accel_z_g=fields[11] / 1000.0,
            crsf_rssi=fields[12],
            crsf_link_quality=fields[13],
            crsf_snr_db=fields[14],
            error_flags=fields[15],
            uptime_ms=fields[16],
        )
        return cls(seq=frame.seq, flags=frame.flags, telemetry=tlm)

    def to_bytes(self) -> bytes:
        t = self.telemetry
        payload = struct.pack(
            TELEMETRY_STRUCT,
            _to_q15(t.setpoint_left),
            _to_q15(t.setpoint_right),
            max(-32768, min(32767, int(round(t.current_left_a * 1000)))),
            max(-32768, min(32767, int(round(t.current_right_a * 1000)))),
            max(0, min(0xFFFF, int(round(t.vbat_v * 1000)))),
            max(0, min(0xFFFF, int(round(t.rail_12v_v * 1000)))),
            max(-32768, min(32767, int(round(t.gyro_x_dps * 100)))),
            max(-32768, min(32767, int(round(t.gyro_y_dps * 100)))),
            max(-32768, min(32767, int(round(t.gyro_z_dps * 100)))),
            max(-32768, min(32767, int(round(t.accel_x_g * 1000)))),
            max(-32768, min(32767, int(round(t.accel_y_g * 1000)))),
            max(-32768, min(32767, int(round(t.accel_z_g * 1000)))),
            t.crsf_rssi & 0xFF,
            t.crsf_link_quality & 0xFF,
            max(-128, min(127, t.crsf_snr_db)),
            t.error_flags & 0xFF,
            t.uptime_ms & 0xFFFFFFFF,
            b"\x00" * 16,
        )
        return build_frame(TelemetryId.SNAPSHOT, self.seq, self.flags, payload)


# --- Command helpers ----------------------------------------------------


def build_setpoint(seq: int, left: float, right: float, flags: int = 0) -> bytes:
    payload = struct.pack("<hh", _to_q15(left), _to_q15(right))
    return build_frame(Command.SET_SETPOINT, seq, flags, payload)


def build_ping(seq: int) -> bytes:
    return build_frame(Command.PING, seq)


def build_arm(seq: int, armed: bool) -> bytes:
    cmd = Command.ARM if armed else Command.DISARM
    return build_frame(cmd, seq)
