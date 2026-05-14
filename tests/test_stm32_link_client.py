"""Tests for the :class:`STM32Link` SPI master client.

We stub out ``spidev`` so that the tests run on any developer machine.
The stub captures outgoing frames and returns pre-baked telemetry frames
so we can assert that the client serialises commands correctly and
surfaces structured telemetry back to the caller.
"""

from __future__ import annotations

from typing import List

import pytest

from stm32_link import Command, Flag, Telemetry, TelemetryFrame
from stm32_link.client import STM32Link, STM32LinkConfig
from stm32_link.protocol import FRAME_SIZE, parse_frame


class FakeSpi:
    def __init__(self, telemetry_frames: List[bytes]) -> None:
        self._queue = list(telemetry_frames)
        self.sent: List[bytes] = []
        self.closed = False

    def xfer2(self, data):
        self.sent.append(bytes(data))
        if not self._queue:
            pytest.fail("FakeSpi ran out of canned telemetry frames")
        return list(self._queue.pop(0))

    def close(self):
        self.closed = True


def _canned_telemetry(seq: int, **kwargs) -> bytes:
    tlm = Telemetry(**kwargs)
    return TelemetryFrame(seq=seq, flags=int(Flag.ARMED), telemetry=tlm).to_bytes()


def test_ping_roundtrips_and_increments_seq():
    fake = FakeSpi(
        [
            _canned_telemetry(1, crsf_rssi=77, uptime_ms=5_000),
            _canned_telemetry(2, crsf_rssi=78, uptime_ms=5_010),
        ]
    )
    link = STM32Link(STM32LinkConfig(), spi=fake)
    first = link.ping()
    second = link.ping()
    assert first.telemetry.crsf_rssi == 77
    assert second.telemetry.uptime_ms == 5_010
    sent_first = parse_frame(fake.sent[0])
    sent_second = parse_frame(fake.sent[1])
    assert sent_first.cmd == int(Command.PING)
    assert sent_second.cmd == int(Command.PING)
    assert sent_second.seq == (sent_first.seq + 1) & 0xFF


def test_set_setpoint_packs_values():
    fake = FakeSpi([_canned_telemetry(1)])
    link = STM32Link(STM32LinkConfig(), spi=fake)
    link.set_setpoint(0.5, -0.5)
    assert len(fake.sent[0]) == FRAME_SIZE
    sent = parse_frame(fake.sent[0])
    assert sent.cmd == int(Command.SET_SETPOINT)
    # Payload layout is little-endian int16 pair.
    import struct

    left, right = struct.unpack("<hh", sent.payload[:4])
    assert left == int(round(0.5 * 32767))
    assert right == int(round(-0.5 * 32767))


def test_arm_and_disarm_emit_the_right_command_codes():
    fake = FakeSpi([_canned_telemetry(1), _canned_telemetry(2)])
    link = STM32Link(STM32LinkConfig(), spi=fake)
    link.arm(True)
    link.arm(False)
    assert parse_frame(fake.sent[0]).cmd == int(Command.ARM)
    assert parse_frame(fake.sent[1]).cmd == int(Command.DISARM)


def test_close_releases_underlying_spi():
    fake = FakeSpi([])
    link = STM32Link(STM32LinkConfig(), spi=fake)
    link.close()
    assert fake.closed


def test_transfer_after_close_raises():
    fake = FakeSpi([])
    link = STM32Link(STM32LinkConfig(), spi=fake)
    link.close()
    with pytest.raises(RuntimeError):
        link.ping()
