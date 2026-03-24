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


def test_main_returns_error_when_pigpio_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")

    class FakePi:
        connected = False

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())

    assert main.main() == 1