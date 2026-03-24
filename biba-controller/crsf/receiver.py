"""CRSF serial receiver for ExpressLRS remote control channels."""

from __future__ import annotations

from typing import Optional

import serial

from crsf.protocol import FRAME_TYPE_RC_CHANNELS_PACKED, parse_frame, pop_frame_from_buffer


class CRSFReceiver:
    """Read and decode CRSF frames from a serial port."""

    def __init__(self, port: str, baudrate: int, timeout: float = 0.02) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_port: Optional[serial.Serial] = None
        self._buffer = bytearray()

    def open(self) -> None:
        """Open the configured serial port."""
        self.serial_port = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        """Close the serial port if it is open."""
        if self.serial_port is not None and self.serial_port.is_open:
            self.serial_port.close()
        self.serial_port = None

    def read_frame(self) -> Optional[tuple[int, bytes]]:
        """Return the next valid CRSF frame if available."""
        if self.serial_port is None:
            raise RuntimeError("CRSFReceiver serial port is not open")

        pending = self.serial_port.in_waiting or 1
        self._buffer.extend(self.serial_port.read(pending))

        while True:
            raw_frame = pop_frame_from_buffer(self._buffer)
            if raw_frame is None:
                return None
            parsed = parse_frame(raw_frame)
            if parsed is not None:
                return parsed

    @staticmethod
    def parse_channels(payload: bytes) -> list[int]:
        """Unpack 16 CRSF RC channels from the packed 11-bit payload."""
        if len(payload) < 22:
            raise ValueError("Packed CRSF channel payload must be at least 22 bytes")

        packed = int.from_bytes(payload[:22], byteorder="little")
        return [(packed >> (index * 11)) & 0x7FF for index in range(16)]

    @staticmethod
    def _normalize_channel(raw_value: int) -> float:
        minimum = 172
        maximum = 1811
        center = (minimum + maximum) / 2
        half_range = (maximum - minimum) / 2
        normalized = (raw_value - center) / half_range
        return max(-1.0, min(1.0, normalized))

    def get_channels(self) -> Optional[list[float]]:
        """Return normalized RC channels when a packed channel frame is available."""
        frame = self.read_frame()
        if frame is None:
            return None

        frame_type, payload = frame
        if frame_type != FRAME_TYPE_RC_CHANNELS_PACKED:
            return None

        return [self._normalize_channel(value) for value in self.parse_channels(payload)]
