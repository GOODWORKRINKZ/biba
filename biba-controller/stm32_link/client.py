"""Thin SPI-master client for the BiBa STM32F103 firmware.

This module is intentionally conservative: it only imports :mod:`spidev`
when :class:`STM32Link` is actually instantiated so unit tests on
developer laptops keep working. The existing GPIO-based runtime is never
touched unless ``STM32_LINK_ENABLED=1`` is set in the environment.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from . import protocol

log = logging.getLogger(__name__)


@dataclass
class STM32LinkConfig:
    bus: int = 0
    device: int = 0
    max_speed_hz: int = 8_000_000
    mode: int = 0  # CPOL=0, CPHA=0 to match firmware SPI_POLARITY_LOW / PHASE_1EDGE


class STM32Link:
    """Full-duplex SPI master that exchanges biba_proto frames with the STM32."""

    def __init__(
        self,
        config: Optional[STM32LinkConfig] = None,
        *,
        spi: Optional[object] = None,
    ) -> None:
        self._config = config or STM32LinkConfig()
        self._lock = threading.Lock()
        self._seq = 0
        self._spi = spi
        if self._spi is None:
            self._spi = self._open_spidev()

    @staticmethod
    def _open_spidev():  # pragma: no cover - requires hardware
        import spidev  # type: ignore import

        cfg = STM32LinkConfig()
        spi = spidev.SpiDev()
        spi.open(cfg.bus, cfg.device)
        spi.max_speed_hz = cfg.max_speed_hz
        spi.mode = cfg.mode
        return spi

    def close(self) -> None:
        spi = self._spi
        self._spi = None
        if spi is not None and hasattr(spi, "close"):
            spi.close()

    def __enter__(self) -> "STM32Link":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _next_seq(self) -> int:
        with self._lock:
            self._seq = (self._seq + 1) & 0xFF
            return self._seq

    def _transfer(self, frame: bytes) -> bytes:
        if self._spi is None:
            raise RuntimeError("STM32Link has been closed")
        if len(frame) != protocol.FRAME_SIZE:
            raise ValueError(
                f"frame must be {protocol.FRAME_SIZE} bytes, got {len(frame)}"
            )
        response = self._spi.xfer2(list(frame))
        return bytes(response)

    def exchange(self, frame: bytes) -> protocol.TelemetryFrame:
        """Ship a command frame and parse the telemetry clocked out in return."""
        raw = self._transfer(frame)
        return protocol.TelemetryFrame.from_bytes(raw)

    def ping(self) -> protocol.TelemetryFrame:
        return self.exchange(protocol.build_ping(self._next_seq()))

    def set_setpoint(self, left: float, right: float) -> protocol.TelemetryFrame:
        return self.exchange(
            protocol.build_setpoint(self._next_seq(), left, right)
        )

    def arm(self, armed: bool = True) -> protocol.TelemetryFrame:
        return self.exchange(protocol.build_arm(self._next_seq(), armed))
