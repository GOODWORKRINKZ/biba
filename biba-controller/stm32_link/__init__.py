"""Optional SPI link to the BiBa STM32F103 add-on.

This package is disabled by default (``STM32_LINK_ENABLED=0``) so that the
existing GPIO-based controller runtime keeps working unchanged. Once the
hardware is wired up operators can flip the environment flag and consume
telemetry / push setpoints over SPI through the :class:`STM32Link` client.

The on-wire format lives in :mod:`biba_controller.stm32_link.protocol`
and mirrors the C headers under ``firmware/src/proto`` byte
for byte. Unit tests in ``tests/test_stm32_link_protocol.py`` keep the
two implementations locked together.
"""

from .protocol import (
    PROTOCOL_VERSION,
    FRAME_SIZE,
    PAYLOAD_MAX,
    Command,
    TelemetryFrame,
    Telemetry,
    Flag,
    build_frame,
    parse_frame,
    crc16_ccitt,
)

__all__ = [
    "PROTOCOL_VERSION",
    "FRAME_SIZE",
    "PAYLOAD_MAX",
    "Command",
    "TelemetryFrame",
    "Telemetry",
    "Flag",
    "build_frame",
    "parse_frame",
    "crc16_ccitt",
    "STM32Link",
]


def __getattr__(name: str):
    # Lazy import so `import stm32_link` works on hosts without spidev.
    if name == "STM32Link":
        from .client import STM32Link as _STM32Link

        return _STM32Link
    raise AttributeError(name)
