from __future__ import annotations

import importlib

import pytest

from bms.daly import BatteryState


def test_is_armed_uses_configured_channel_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "CH_ARM", 2)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.25)

    assert main._is_armed([0.0, 0.1, 0.3]) is True
    assert main._is_armed([0.0, 0.1, 0.2]) is False


def test_get_channel_returns_zero_when_index_is_missing() -> None:
    main = importlib.import_module("main")

    assert main._get_channel([0.4, -0.2], 1) == -0.2
    assert main._get_channel([0.4, -0.2], 3) == 0.0


def test_battery_is_low_prefers_cell_voltage_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "LOW_CELL_VOLTAGE", 3.5)
    monkeypatch.setattr(main.config, "LOW_PACK_VOLTAGE", 21.0)

    state = BatteryState(
        voltage=24.0,
        current=5.0,
        soc=70.0,
        cells=[3.48, 3.6, 3.62],
        temperatures=[21.0],
        min_cell=3.48,
        max_cell=3.62,
        delta=0.14,
    )

    assert main._battery_is_low(state) is True


def test_battery_is_low_falls_back_to_pack_voltage_without_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "LOW_CELL_VOLTAGE", 3.5)
    monkeypatch.setattr(main.config, "LOW_PACK_VOLTAGE", 21.0)

    state = BatteryState(
        voltage=20.5,
        current=3.0,
        soc=40.0,
        cells=[],
        temperatures=[19.0],
        min_cell=0.0,
        max_cell=0.0,
        delta=0.0,
    )

    assert main._battery_is_low(state) is True


def test_main_continues_when_pigpio_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")

    class FakePi:
        connected = False

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            return None

    class FakeTelemetry:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def attach(self, serial_port) -> None:
            assert serial_port is not None

    class FakeBMS:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def open(self) -> None:
            raise FileNotFoundError("/dev/ttyUSB0")

        def close(self) -> None:
            pass

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0


def test_main_continues_when_bms_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            return None

    class FakeTelemetry:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def attach(self, serial_port) -> None:
            assert serial_port is not None

    class FakeBMS:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def open(self) -> None:
            raise FileNotFoundError("/dev/ttyUSB0")

        def close(self) -> None:
            pass

    class FakeMotorDriver:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> None:
            pass

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeBuzzer:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

    class FakeBeacon:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def on_connected(self) -> None:
            pass

        def set_manual(self, *args, **kwargs) -> None:
            pass

        def on_failsafe(self, *args, **kwargs) -> None:
            pass

        def should_sos(self, *args, **kwargs) -> bool:
            return False

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "MotorDriver", FakeMotorDriver)
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "Buzzer", FakeBuzzer)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0


def test_main_sends_test_battery_telemetry_when_bms_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    sent_packets: list[tuple[float, float, int, int]] = []

    class FakePi:
        connected = False

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._read_count = 0

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            self._read_count += 1
            main.RUNNING = False
            return [0.0, 0.0, 0.0, 0.0, -1.0, 0.0]

    class FakeTelemetry:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def attach(self, serial_port) -> None:
            assert serial_port is not None

        def send_battery(self, voltage_v: float, current_a: float, capacity_mah: int, remaining_pct: int) -> None:
            sent_packets.append((voltage_v, current_a, capacity_mah, remaining_pct))

    class FakeBMS:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def open(self) -> None:
            raise FileNotFoundError("/dev/ttyUSB0")

        def close(self) -> None:
            pass

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr(main.config, "TEST_BATTERY_VOLTAGE", 25.0)
    monkeypatch.setattr(main.config, "TEST_BATTERY_CURRENT", 1.2)
    monkeypatch.setattr(main.config, "TEST_BATTERY_CAPACITY_MAH", 0)
    monkeypatch.setattr(main.config, "TEST_BATTERY_REMAINING_PCT", 55)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert sent_packets == [(25.0, 1.2, 0, 55)]