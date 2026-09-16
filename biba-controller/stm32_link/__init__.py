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
    FRAME_SIZE,
    PAYLOAD_MAX,
    PROTOCOL_VERSION,
    Command,
    Flag,
    Telemetry,
    TelemetryFrame,
    build_frame,
    crc16_ccitt,
    parse_frame,
)

__all__ = [
    "FRAME_SIZE",
    "PAYLOAD_MAX",
    "PROTOCOL_VERSION",
    "Command",
    "Flag",
    "STM32Link",
    "Telemetry",
    "TelemetryFrame",
    "build_frame",
    "crc16_ccitt",
    "parse_frame",
]


def __getattr__(name: str):
    # Lazy import so `import stm32_link` works on hosts without spidev.
    if name == "STM32Link":
        from .client import STM32Link as _STM32Link

        return _STM32Link
    raise AttributeError(name)
