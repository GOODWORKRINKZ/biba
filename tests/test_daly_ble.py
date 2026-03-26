from __future__ import annotations

import sys
import threading
import types
from collections import deque

import pytest

from bms.daly import BatteryState, DalyBMSBle, _build_ble_client


def build_response(command: int, data: bytes) -> bytes:
    frame = bytes([0xA5, 0x01, command, 0x08]) + data
    return frame + bytes([sum(frame) & 0xFF])


class FakeBleClient:
    def __init__(self, responses: list[bytes] | None = None) -> None:
        self.responses = deque(responses or [])
        self.connected = False
        self.notify_uuid: str | None = None
        self.callback = None
        self.written: list[tuple[str, bytes]] = []
        self.stop_notify_calls: list[str] = []
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True
        self.connected = False

    def start_notify(self, uuid: str, callback) -> None:
        self.notify_uuid = uuid
        self.callback = callback

    def stop_notify(self, uuid: str) -> None:
        self.stop_notify_calls.append(uuid)

    def write_gatt_char(self, uuid: str, data: bytes) -> None:
        self.written.append((uuid, data))
        if self.callback is None or not self.responses:
            return

        command = data[2]
        while self.responses and self.responses[0][2] == command:
            self.callback(self.responses.popleft())


def test_ble_open_connects_and_enables_notifications() -> None:
    client = FakeBleClient()
    bms = DalyBMSBle(
        "71:C1:46:20:25:4F",
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000fff2-0000-1000-8000-00805f9b34fb",
        "0000fff1-0000-1000-8000-00805f9b34fb",
        client_factory=lambda address, service_uuid: client,
    )

    bms.open()

    assert client.connected is True
    assert client.notify_uuid == "0000fff1-0000-1000-8000-00805f9b34fb"


def test_ble_send_command_writes_request_and_returns_matching_frame() -> None:
    response = build_response(0x90, bytes(8))
    client = FakeBleClient([response])
    bms = DalyBMSBle(
        "71:C1:46:20:25:4F",
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000fff2-0000-1000-8000-00805f9b34fb",
        "0000fff1-0000-1000-8000-00805f9b34fb",
        client_factory=lambda address, service_uuid: client,
    )
    bms.open()

    result = bms._send_command(0x90)

    assert result == response
    assert client.written == [(
        "0000fff2-0000-1000-8000-00805f9b34fb",
        bytes.fromhex("a540900800000000000000007d"),
    )]


def test_ble_send_command_returns_none_on_timeout() -> None:
    client = FakeBleClient()
    bms = DalyBMSBle(
        "71:C1:46:20:25:4F",
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000fff2-0000-1000-8000-00805f9b34fb",
        "0000fff1-0000-1000-8000-00805f9b34fb",
        timeout=0.01,
        client_factory=lambda address, service_uuid: client,
    )
    bms.open()

    assert bms._send_command(0x90) is None


def test_ble_read_state_aggregates_all_measurements() -> None:
    responses = [
        build_response(0x90, bytes.fromhex("00fc0000755d030f")),
        build_response(0x95, bytes.fromhex("0dac0db600000000")),
        build_response(0x95, bytes.fromhex("0dc00dca0dd40000")),
        build_response(0x92, bytes([0, 45, 50, 0, 0, 0, 0, 0])),
    ]
    client = FakeBleClient(responses)
    bms = DalyBMSBle(
        "71:C1:46:20:25:4F",
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000fff2-0000-1000-8000-00805f9b34fb",
        "0000fff1-0000-1000-8000-00805f9b34fb",
        client_factory=lambda address, service_uuid: client,
    )
    bms.open()

    state = bms.read_state()

    assert state == BatteryState(
        voltage=25.2,
        current=4.5,
        soc=78.3,
        cells=[3.5, 3.51, 3.52, 3.53, 3.54],
        temperatures=[5.0, 10.0],
        min_cell=3.5,
        max_cell=3.54,
        delta=pytest.approx(0.04),
    )


def test_ble_close_stops_notifications_and_disconnects() -> None:
    client = FakeBleClient()
    bms = DalyBMSBle(
        "71:C1:46:20:25:4F",
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000fff2-0000-1000-8000-00805f9b34fb",
        "0000fff1-0000-1000-8000-00805f9b34fb",
        client_factory=lambda address, service_uuid: client,
    )
    bms.open()

    bms.close()

    assert client.stop_notify_calls == ["0000fff1-0000-1000-8000-00805f9b34fb"]
    assert client.disconnected is True


def test_build_ble_client_creates_bleak_client_in_loop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, int] = {}

    class FakeBleakClient:
        def __init__(self, device_address: str) -> None:
            observed["address"] = device_address
            observed["init_thread"] = threading.get_ident()

        async def connect(self) -> None:
            observed["connect_thread"] = threading.get_ident()

        async def disconnect(self) -> None:
            observed["disconnect_thread"] = threading.get_ident()

        async def start_notify(self, uuid: str, callback) -> None:
            del callback
            observed["notify_uuid"] = uuid
            observed["notify_thread"] = threading.get_ident()

        async def stop_notify(self, uuid: str) -> None:
            observed["stop_notify_uuid"] = uuid
            observed["stop_notify_thread"] = threading.get_ident()

        async def write_gatt_char(self, uuid: str, data: bytes) -> None:
            observed["write_uuid"] = uuid
            observed["write_data"] = data
            observed["write_thread"] = threading.get_ident()

    fake_bleak_module = types.SimpleNamespace(BleakClient=FakeBleakClient)
    monkeypatch.setitem(sys.modules, "bleak", fake_bleak_module)

    client = _build_ble_client("71:C1:46:20:25:4F", "0000fff0-0000-1000-8000-00805f9b34fb")

    client.connect()
    client.start_notify("0000fff1-0000-1000-8000-00805f9b34fb", lambda data: None)
    client.write_gatt_char("0000fff2-0000-1000-8000-00805f9b34fb", b"abc")
    client.stop_notify("0000fff1-0000-1000-8000-00805f9b34fb")
    client.disconnect()

    assert observed["address"] == "71:C1:46:20:25:4F"
    assert observed["init_thread"] == observed["connect_thread"]
    assert observed["init_thread"] == observed["notify_thread"]
    assert observed["init_thread"] == observed["write_thread"]
    assert observed["init_thread"] == observed["stop_notify_thread"]


def test_build_ble_client_uses_resolved_bluez_device(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_device = object()
    observed: dict[str, object] = {}

    class FakeBleakClient:
        def __init__(self, target: object) -> None:
            observed["target"] = target

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def start_notify(self, uuid: str, callback) -> None:
            del uuid, callback

        async def stop_notify(self, uuid: str) -> None:
            del uuid

        async def write_gatt_char(self, uuid: str, data: bytes) -> None:
            del uuid, data

    async def fake_resolve(address: str) -> object:
        assert address == "71:C1:46:20:25:4F"
        return fake_device

    fake_bleak_module = types.SimpleNamespace(BleakClient=FakeBleakClient)
    monkeypatch.setitem(sys.modules, "bleak", fake_bleak_module)
    monkeypatch.setattr("bms.daly._resolve_bleak_target", fake_resolve, raising=False)

    client = _build_ble_client("71:C1:46:20:25:4F", "0000fff0-0000-1000-8000-00805f9b34fb")

    client.connect()
    client.disconnect()

    assert observed["target"] is fake_device