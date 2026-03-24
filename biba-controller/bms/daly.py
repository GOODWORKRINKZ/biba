"""Daly BMS protocol helpers for serial telemetry polling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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

    def _send_command(self, command: int) -> Optional[bytes]:
        """Send a Daly request frame and return a validated 13-byte response."""
        if self.serial_port is None:
            raise RuntimeError("DalyBMS serial port is not open")

        request = bytes([0xA5, 0x40, command, 0x08]) + bytes(8)
        request += bytes([sum(request) & 0xFF])
        self.serial_port.reset_input_buffer()
        self.serial_port.write(request)
        response = self.serial_port.read(13)

        if len(response) != 13:
            return None
        if response[0] != 0xA5 or response[2] != command:
            return None
        if self._checksum(response) != response[-1]:
            return None
        return response

    def get_soc(self) -> Optional[dict[str, float]]:
        """Return pack voltage, current, and state-of-charge information."""
        response = self._send_command(0x90)
        if response is None:
            return None

        data = response[4:12]
        total_voltage = int.from_bytes(data[0:2], byteorder="big") / 10.0
        raw_current = int.from_bytes(data[4:6], byteorder="big")
        current = (raw_current - 30000) / 10.0
        soc = int.from_bytes(data[6:8], byteorder="big") / 10.0

        return {"voltage": total_voltage, "current": current, "soc": soc}

    def get_cell_voltages(self) -> list[float]:
        """Read per-cell voltages.

        Daly may answer with up to three cell values per response; this method keeps
        polling until no more valid frames arrive within the serial timeout.
        """
        if self.serial_port is None:
            raise RuntimeError("DalyBMS serial port is not open")

        request = bytes([0xA5, 0x40, 0x95, 0x08]) + bytes(8)
        request += bytes([sum(request) & 0xFF])

        self.serial_port.reset_input_buffer()
        self.serial_port.write(request)

        cells: list[float] = []
        while True:
            response = self.serial_port.read(13)
            if len(response) != 13:
                break
            if response[0] != 0xA5 or response[2] != 0x95:
                continue
            if self._checksum(response) != response[-1]:
                continue

            data = response[4:12]
            frame_cells = [
                int.from_bytes(data[index:index + 2], byteorder="big") / 1000.0
                for index in range(0, 6, 2)
            ]
            cells.extend(value for value in frame_cells if value > 0)
            if len(cells) >= 6:
                break

        return cells[:6]

    def get_temperatures(self) -> list[float]:
        """Return a list of BMS temperatures in Celsius."""
        response = self._send_command(0x92)
        if response is None:
            return []

        data = response[4:12]
        temperatures: list[float] = []
        for value in data:
            if value > 0:
                temperatures.append(float(value - 40))
        return temperatures

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