"""Daly BMS protocol helpers for serial telemetry polling."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import serial


@dataclass(slots=True)
class BatteryState:
    """Aggregated battery telemetry derived from Daly BMS responses."""

    voltage: float
    current: float
    soc: float
    cells: list[float]
    temperatures: list[float]
    min_cell: float
    max_cell: float
    delta: float


class BleClientProtocol(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def start_notify(self, uuid: str, callback: Callable[[bytes], None]) -> None: ...

    def stop_notify(self, uuid: str) -> None: ...

    def write_gatt_char(self, uuid: str, data: bytes) -> None: ...


class DalyBMS:
    """Read battery telemetry from a Daly BMS over UART."""

    def __init__(self, port: str, baudrate: int, timeout: float = 0.2) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_port: Optional[serial.Serial] = None

    def open(self) -> None:
        """Open the configured BMS serial port."""
        self.serial_port = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        """Close the BMS serial port if it is open."""
        if self.serial_port is not None and self.serial_port.is_open:
            self.serial_port.close()
        self.serial_port = None

    @staticmethod
    def _checksum(frame: bytes) -> int:
        return sum(frame[:-1]) & 0xFF

    @classmethod
    def _build_request(cls, command: int) -> bytes:
        request = bytes([0xA5, 0x40, command, 0x08]) + bytes(8)
        return request + bytes([sum(request) & 0xFF])

    @classmethod
    def _validate_response(cls, response: bytes, command: int) -> bool:
        if len(response) != 13:
            return False
        if response[0] != 0xA5 or response[2] != command:
            return False
        return cls._checksum(response) == response[-1]

    @classmethod
    def _parse_soc_data(cls, response: bytes) -> dict[str, float]:
        data = response[4:12]
        total_voltage = int.from_bytes(data[0:2], byteorder="big") / 10.0
        raw_current = int.from_bytes(data[4:6], byteorder="big")
        current = (raw_current - 30000) / 10.0
        soc = int.from_bytes(data[6:8], byteorder="big") / 10.0
        return {"voltage": total_voltage, "current": current, "soc": soc}

    @classmethod
    def _parse_temperature_data(cls, response: bytes) -> list[float]:
        data = response[4:12]
        temperatures: list[float] = []
        for value in data:
            if value > 0:
                temperatures.append(float(value - 40))
        return temperatures

    @classmethod
    def _extract_cell_values(cls, response: bytes) -> list[float]:
        data = response[4:12]
        frame_cells = [
            int.from_bytes(data[index:index + 2], byteorder="big") / 1000.0
            for index in range(0, 6, 2)
        ]
        return [value for value in frame_cells if value > 0]

    def _send_command(self, command: int) -> Optional[bytes]:
        """Send a Daly request frame and return a validated 13-byte response."""
        if self.serial_port is None:
            raise RuntimeError("DalyBMS serial port is not open")

        request = self._build_request(command)
        self.serial_port.reset_input_buffer()
        self.serial_port.write(request)
        response = self.serial_port.read(13)

        if not self._validate_response(response, command):
            return None
        return response

    def get_soc(self) -> Optional[dict[str, float]]:
        """Return pack voltage, current, and state-of-charge information."""
        response = self._send_command(0x90)
        if response is None:
            return None

        return self._parse_soc_data(response)

    def get_cell_voltages(self) -> list[float]:
        """Read per-cell voltages.

        Daly may answer with up to three cell values per response; this method keeps
        polling until no more valid frames arrive within the serial timeout.
        """
        if self.serial_port is None:
            raise RuntimeError("DalyBMS serial port is not open")

        request = self._build_request(0x95)

        self.serial_port.reset_input_buffer()
        self.serial_port.write(request)

        cells: list[float] = []
        while True:
            response = self.serial_port.read(13)
            if len(response) != 13:
                break
            if not self._validate_response(response, 0x95):
                continue

            cells.extend(self._extract_cell_values(response))
            if len(cells) >= 6:
                break

        return cells[:6]

    def get_temperatures(self) -> list[float]:
        """Return a list of BMS temperatures in Celsius."""
        response = self._send_command(0x92)
        if response is None:
            return []

        return self._parse_temperature_data(response)

    def read_state(self) -> Optional[BatteryState]:
        """Read all available telemetry and return an aggregated battery state."""
        soc = self.get_soc()
        if soc is None:
            return None

        cells = self.get_cell_voltages()
        temperatures = self.get_temperatures()
        min_cell = min(cells) if cells else 0.0
        max_cell = max(cells) if cells else 0.0

        return BatteryState(
            voltage=soc["voltage"],
            current=soc["current"],
            soc=soc["soc"],
            cells=cells,
            temperatures=temperatures,
            min_cell=min_cell,
            max_cell=max_cell,
            delta=max_cell - min_cell if cells else 0.0,
        )


class DalyBMSBle(DalyBMS):
    """Read battery telemetry from a Daly BMS over BLE."""

    def __init__(
        self,
        address: str,
        service_uuid: str,
        write_uuid: str,
        notify_uuid: str,
        timeout: float = 1.5,
        client_factory: Optional[Callable[[str, str], BleClientProtocol]] = None,
    ) -> None:
        super().__init__(port=address, baudrate=0, timeout=timeout)
        self.address = address
        self.service_uuid = service_uuid
        self.write_uuid = write_uuid
        self.notify_uuid = notify_uuid
        self._client_factory = client_factory or _build_ble_client
        self._client: Optional[BleClientProtocol] = None
        self._response_lock = threading.Lock()
        self._response_event = threading.Event()
        self._pending_command: Optional[int] = None
        self._pending_frames: list[bytes] = []

    def open(self) -> None:
        if not self.address:
            raise ValueError("BMS_BLE_ADDRESS is required for BLE transport")

        client = self._client_factory(self.address, self.service_uuid)
        client.connect()
        client.start_notify(self.notify_uuid, self._handle_notification)
        self._client = client

    def close(self) -> None:
        if self._client is None:
            return

        try:
            self._client.stop_notify(self.notify_uuid)
        except Exception:
            pass
        try:
            self._client.disconnect()
        finally:
            self._client = None

    def _handle_notification(self, data: bytes) -> None:
        with self._response_lock:
            if self._pending_command is None:
                return
            if not self._validate_response(data, self._pending_command):
                return
            self._pending_frames.append(data)
            self._response_event.set()

    def _send_command(self, command: int) -> Optional[bytes]:
        if self._client is None:
            raise RuntimeError("DalyBMSBle client is not connected")

        with self._response_lock:
            self._pending_command = command
            self._pending_frames.clear()
            self._response_event.clear()

        self._client.write_gatt_char(self.write_uuid, self._build_request(command))
        if not self._response_event.wait(self.timeout):
            with self._response_lock:
                self._pending_command = None
            return None

        with self._response_lock:
            response = self._pending_frames.pop(0) if self._pending_frames else None
            self._pending_command = None
        return response

    def get_cell_voltages(self) -> list[float]:
        cells: list[float] = []
        while len(cells) < 6:
            response = self._send_command(0x95)
            if response is None:
                break
            frame_cells = self._extract_cell_values(response)
            if not frame_cells:
                break
            cells.extend(frame_cells)
            with self._response_lock:
                queued_frames = list(self._pending_frames)
                self._pending_frames.clear()
            for queued_response in queued_frames:
                cells.extend(self._extract_cell_values(queued_response))
                if len(cells) >= 6:
                    break
        return cells[:6]


def _build_ble_client(address: str, service_uuid: str) -> BleClientProtocol:
    del service_uuid

    try:
        from bleak import BleakClient
    except ImportError as exc:
        raise RuntimeError("BLE transport requires the 'bleak' package") from exc

    class _BleakClientAdapter:
        def __init__(self, device_address: str) -> None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self._client = BleakClient(device_address)

        def _run_loop(self) -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        def _run_coroutine(self, coroutine: asyncio.Future) -> object:
            future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
            return future.result(timeout=10.0)

        def connect(self) -> None:
            self._run_coroutine(self._client.connect())

        def disconnect(self) -> None:
            try:
                self._run_coroutine(self._client.disconnect())
            finally:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join(timeout=1.0)

        def start_notify(self, uuid: str, callback: Callable[[bytes], None]) -> None:
            self._run_coroutine(
                self._client.start_notify(uuid, lambda _sender, data: callback(bytes(data)))
            )

        def stop_notify(self, uuid: str) -> None:
            self._run_coroutine(self._client.stop_notify(uuid))

        def write_gatt_char(self, uuid: str, data: bytes) -> None:
            self._run_coroutine(self._client.write_gatt_char(uuid, data))

    return _BleakClientAdapter(address)