from __future__ import annotations

import importlib
import logging

import pytest

from bms.daly import BatteryState
from motors.current_control import MotorCurrentSample


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


def test_main_filters_throttle_before_passing_it_to_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    drive_calls: list[tuple[float, float, float]] = []

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                [0.0, 1.0, 0.0, 0.0, 0.98, 0.0],
                [0.0, 1.0, 0.0, 0.0, 0.98, 0.0],
                [0.0, 1.0, 0.0, 0.0, 0.98, 0.0],
                [0.0, -1.0, 0.0, 0.0, 0.98, 0.0],
            ]

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            frame = self._frames.pop(0)
            if not self._frames:
                main.RUNNING = False
            return frame

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

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            drive_calls.append((throttle, steering, dt))
            return (0.0, 0.0)

        def stop(self) -> None:
            pass

        def check_failsafe(self, last_frame_time: float) -> bool:
            del last_frame_time
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            pass

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            pass

        def off(self) -> None:
            pass

        def set_control_active(self, active: bool) -> None:
            del active

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "THROTTLE_FILTER_MODE", "KALMAN")
    monkeypatch.setattr(main.config, "THROTTLE_KALMAN_PROCESS_NOISE", 0.02)
    monkeypatch.setattr(main.config, "THROTTLE_KALMAN_MEASUREMENT_NOISE", 0.5)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert drive_calls[-1][0] > 0.0


def test_main_uses_elapsed_time_between_drive_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    drive_calls: list[tuple[float, float, float]] = []

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                [0.0, 1.0, 0.0, 0.0, 0.98, 0.0],
                [0.0, 1.0, 0.0, 0.0, 0.98, 0.0],
            ]

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            frame = self._frames.pop(0)
            if not self._frames:
                main.RUNNING = False
            return frame

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

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            drive_calls.append((throttle, steering, dt))
            return (0.0, 0.0)

        def stop(self) -> None:
            pass

        def check_failsafe(self, last_frame_time: float) -> bool:
            del last_frame_time
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            pass

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            pass

        def off(self) -> None:
            pass

        def set_control_active(self, active: bool) -> None:
            del active

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

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

    monotonic_values = iter([0.0, 1.0, 1.0, 1.05, 1.05])

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "THROTTLE_FILTER_MODE", "NONE")
    monkeypatch.setattr(main.config, "MAIN_LOOP_HZ", 50)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert len(drive_calls) == 2
    assert drive_calls[0][2] == pytest.approx(0.02)
    assert drive_calls[1][2] == pytest.approx(0.05)


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


def test_log_battery_telemetry_reports_raw_clamped_and_encoded_current(caplog: pytest.LogCaptureFixture) -> None:
    main = importlib.import_module("main")
    state = BatteryState(
        voltage=24.1,
        current=-7.34,
        soc=63.0,
        cells=[3.4, 3.45],
        temperatures=[22.0],
        min_cell=3.4,
        max_cell=3.45,
        delta=0.05,
    )

    with caplog.at_level(logging.INFO, logger="biba-controller"):
        next_log_at = main._log_battery_telemetry(state, now=10.0, last_log_at=0.0)

    assert next_log_at == 10.0
    assert "raw_current_a=-7.34" in caplog.text
    assert "telemetry_current_a=7.34" in caplog.text
    assert "crsf_current_da=73" in caplog.text
    assert "telemetry_direction=DIS" in caplog.text


def test_send_battery_telemetry_uses_absolute_bms_current_for_discharge() -> None:
    main = importlib.import_module("main")
    sent_packets: list[tuple[float, float, int, int]] = []

    class FakeTelemetry:
        def send_battery(self, voltage_v: float, current_a: float, capacity_mah: int, remaining_pct: int) -> None:
            sent_packets.append((voltage_v, current_a, capacity_mah, remaining_pct))

    state = BatteryState(
        voltage=24.1,
        current=-1.3,
        soc=63.0,
        cells=[3.4, 3.45],
        temperatures=[22.0],
        min_cell=3.4,
        max_cell=3.45,
        delta=0.05,
    )

    main._send_battery_telemetry(FakeTelemetry(), state)

    assert sent_packets == [(24.1, 1.3, 2, 63)]


def test_send_battery_telemetry_marks_positive_current_as_charging() -> None:
    main = importlib.import_module("main")
    sent_packets: list[tuple[float, float, int, int]] = []

    class FakeTelemetry:
        def send_battery(self, voltage_v: float, current_a: float, capacity_mah: int, remaining_pct: int) -> None:
            sent_packets.append((voltage_v, current_a, capacity_mah, remaining_pct))

    state = BatteryState(
        voltage=24.1,
        current=1.6,
        soc=63.0,
        cells=[3.4, 3.45],
        temperatures=[22.0],
        min_cell=3.4,
        max_cell=3.45,
        delta=0.05,
    )

    main._send_battery_telemetry(FakeTelemetry(), state)

    assert sent_packets == [(24.1, 1.6, 1, 63)]


def test_log_battery_telemetry_skips_until_interval_elapsed(caplog: pytest.LogCaptureFixture) -> None:
    main = importlib.import_module("main")
    state = BatteryState(
        voltage=24.1,
        current=2.5,
        soc=63.0,
        cells=[3.4, 3.45],
        temperatures=[22.0],
        min_cell=3.4,
        max_cell=3.45,
        delta=0.05,
    )

    with caplog.at_level(logging.INFO, logger="biba-controller"):
        next_log_at = main._log_battery_telemetry(state, now=4.0, last_log_at=1.0)

    assert next_log_at == 1.0
    assert caplog.text == ""


def test_get_motor_supply_voltage_prefers_bms_state(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_LIMIT_FALLBACK_VOLTAGE", 22.2)

    state = BatteryState(
        voltage=25.4,
        current=3.0,
        soc=50.0,
        cells=[],
        temperatures=[],
        min_cell=0.0,
        max_cell=0.0,
        delta=0.0,
    )

    assert main._get_motor_supply_voltage(state) == pytest.approx(25.4)


def test_get_motor_supply_voltage_falls_back_to_config(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_LIMIT_FALLBACK_VOLTAGE", 22.2)

    assert main._get_motor_supply_voltage(None) == pytest.approx(22.2)


def test_limit_drive_outputs_returns_requested_when_limiter_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_LIMITING_ENABLED", False)

    result = main._limit_drive_outputs(
        requested_left=0.6,
        requested_right=-0.3,
        left_sample=MotorCurrentSample(current_a=30.0),
        right_sample=MotorCurrentSample(current_a=30.0),
        battery_state=None,
    )

    assert result.left_output == pytest.approx(0.6)
    assert result.right_output == pytest.approx(-0.3)
    assert result.left_limited is False
    assert result.right_limited is False


def test_limit_drive_outputs_uses_configured_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_LIMITING_ENABLED", True)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_MAX_CURRENT_A", 10.0)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_MAX_CURRENT_A", 20.0)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_MAX_POWER_W", 1000.0)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_MAX_POWER_W", 1000.0)
    monkeypatch.setattr(main.config, "MOTOR_LIMIT_FALLBACK_VOLTAGE", 24.0)

    result = main._limit_drive_outputs(
        requested_left=0.8,
        requested_right=0.5,
        left_sample=MotorCurrentSample(current_a=20.0),
        right_sample=MotorCurrentSample(current_a=5.0),
        battery_state=None,
    )

    assert result.left_output == pytest.approx(0.4)
    assert result.right_output == pytest.approx(0.5)
    assert result.left_limited is True
    assert result.right_limited is False


def test_create_motor_current_reader_returns_null_reader_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_SENSE_ENABLED", False)

    reader = main._create_motor_current_reader()
    left_sample, right_sample = reader.read_currents()

    assert left_sample.valid is False
    assert right_sample.valid is False


def test_main_applies_limited_outputs_when_current_limit_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    applied_outputs: list[tuple[float, float, float, float, float]] = []

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                [0.0, 1.0, 0.0, 0.0, 0.98, 0.0],
            ]

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            frame = self._frames.pop(0)
            main.RUNNING = False
            return frame

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

    class FakeCurrentReader:
        def read_currents(self) -> tuple[MotorCurrentSample, MotorCurrentSample]:
            return MotorCurrentSample(current_a=20.0), MotorCurrentSample(current_a=5.0)

        def close(self) -> None:
            pass

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def mix_and_ramp(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del throttle, steering, dt
            return (0.8, 0.5)

        def apply_output(
            self,
            left_duty: float,
            right_duty: float,
            *,
            throttle: float = 0.0,
            steering: float = 0.0,
            dt: float = 0.02,
        ) -> tuple[float, float]:
            applied_outputs.append((left_duty, right_duty, throttle, steering, dt))
            return (left_duty, right_duty)

        def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            applied_outputs.append((throttle, steering, throttle, steering, dt))
            return (throttle, steering)

        def stop(self) -> None:
            pass

        def check_failsafe(self, last_frame_time: float) -> bool:
            del last_frame_time
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            pass

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            pass

        def off(self) -> None:
            pass

        def set_control_active(self, active: bool) -> None:
            del active

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main, "_create_motor_current_reader", lambda: FakeCurrentReader())
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "THROTTLE_FILTER_MODE", "NONE")
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_LIMITING_ENABLED", True)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_MAX_CURRENT_A", 10.0)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_MAX_CURRENT_A", 20.0)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_MAX_POWER_W", 1000.0)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_MAX_POWER_W", 1000.0)
    monkeypatch.setattr(main.config, "MOTOR_LIMIT_FALLBACK_VOLTAGE", 24.0)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert applied_outputs[-1][0] == pytest.approx(0.4)
    assert applied_outputs[-1][1] == pytest.approx(0.5)


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


def test_create_bms_returns_uart_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")

    created: list[tuple[str, tuple[object, ...]]] = []

    class FakeUartBMS:
        def __init__(self, *args) -> None:
            created.append(("uart", args))

    class FakeBleBMS:
        def __init__(self, *args) -> None:
            created.append(("ble", args))

    monkeypatch.setattr(main, "DalyBMS", FakeUartBMS)
    monkeypatch.setattr(main, "DalyBMSBle", FakeBleBMS)
    monkeypatch.setattr(main.config, "BMS_TRANSPORT", "UART")
    monkeypatch.setattr(main.config, "BMS_PORT", "/dev/ttyUSB0")
    monkeypatch.setattr(main.config, "BMS_BAUD", 9600)

    bms = main._create_bms()

    assert isinstance(bms, FakeUartBMS)
    assert created == [("uart", ("/dev/ttyUSB0", 9600))]


def test_create_bms_returns_ble_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")

    created: list[tuple[str, tuple[object, ...]]] = []

    class FakeUartBMS:
        def __init__(self, *args) -> None:
            created.append(("uart", args))

    class FakeBleBMS:
        def __init__(self, *args) -> None:
            created.append(("ble", args))

    monkeypatch.setattr(main, "DalyBMS", FakeUartBMS)
    monkeypatch.setattr(main, "DalyBMSBle", FakeBleBMS)
    monkeypatch.setattr(main.config, "BMS_TRANSPORT", "BLE")
    monkeypatch.setattr(main.config, "BMS_BLE_ADDRESS", "71:C1:46:20:25:4F")
    monkeypatch.setattr(main.config, "BMS_BLE_SERVICE_UUID", "0000fff0-0000-1000-8000-00805f9b34fb")
    monkeypatch.setattr(main.config, "BMS_BLE_WRITE_UUID", "0000fff2-0000-1000-8000-00805f9b34fb")
    monkeypatch.setattr(main.config, "BMS_BLE_NOTIFY_UUID", "0000fff1-0000-1000-8000-00805f9b34fb")
    monkeypatch.setattr(main.config, "BMS_BLE_TIMEOUT_S", 1.5)

    bms = main._create_bms()

    assert isinstance(bms, FakeBleBMS)
    assert created == [(
        "ble",
        (
            "71:C1:46:20:25:4F",
            "0000fff0-0000-1000-8000-00805f9b34fb",
            "0000fff2-0000-1000-8000-00805f9b34fb",
            "0000fff1-0000-1000-8000-00805f9b34fb",
            1.5,
        ),
    )]


def test_main_continues_when_bms_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    played: list[str] = []

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

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            played.append(name)

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "MOTOR_DRIVER_TYPE", "PWM_DIR")
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "imperial_march")
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0
    assert played == ["imperial_march"]


def test_main_continues_when_ble_bms_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
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

    class FakeBleBMS:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def open(self) -> None:
            raise RuntimeError("ble unavailable")

        def close(self) -> None:
            pass

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMSBle", FakeBleBMS)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "BMS_TRANSPORT", "BLE")
    monkeypatch.setattr(main.config, "BMS_BLE_ADDRESS", "71:C1:46:20:25:4F")
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0


def test_main_uses_bts7960_driver_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    created: list[tuple[int, int, int, int, bool]] = []

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

    class FakeBTS7960MotorDriver:
        def __init__(self, pi, rpwm_pin: int, lpwm_pin: int, ren_pin: int, len_pin: int, inverted: bool = False) -> None:
            del pi
            created.append((rpwm_pin, lpwm_pin, ren_pin, len_pin, inverted))

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    synth_created: list[dict] = []

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            synth_created.append({"pins": tuple(args[1]), "comp": tuple(kwargs.get("comp_pins") or [])})

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

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
    monkeypatch.setattr(main, "BTS7960MotorDriver", FakeBTS7960MotorDriver)
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "MOTOR_DRIVER_TYPE", "BTS7960")
    monkeypatch.setattr(main.config, "LEFT_MOTOR_RPWM", 18)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LPWM", 13)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_REN", 23)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LEN", 24)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_RPWM", 12)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LPWM", 19)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_REN", 20)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LEN", 21)
    monkeypatch.setattr(main.config, "MOTOR1_INVERTED", 1)
    monkeypatch.setattr(main.config, "MOTOR2_INVERTED", 0)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0
    assert created == [
        (18, 13, 23, 24, True),
        (12, 19, 20, 21, False),
    ]
    assert synth_created == [{"pins": (18, 12), "comp": (13, 19)}]


def test_main_excludes_disabled_motor_from_motor_synth_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    synth_created: list[dict] = []

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

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            synth_created.append({"pins": tuple(args[1]), "comp": tuple(kwargs.get("comp_pins") or [])})

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_RPWM", 18)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LPWM", 13)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_RPWM", 12)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LPWM", 19)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_ENABLED", True)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_ENABLED", False)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0
    assert synth_created == [{"pins": (18,), "comp": (13,)}]


def test_main_does_not_trigger_failsafe_after_blocking_arm_tone_when_frame_was_received(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    fake_time = [0.0]
    failsafe_calls: list[str] = []

    class FakePi:
        connected = True

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
            return [0.0, 0.0, 0.0, 0.0, 0.98, 0.0, 0.0, 0.0, 0.0]

    class FakeTelemetry:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def attach(self, serial_port) -> None:
            assert serial_port is not None

        def send_battery(self, *args, **kwargs) -> None:
            pass

        def send_system_stats(self, *args, **kwargs) -> None:
            pass

    class FakeBMS:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def open(self) -> None:
            raise FileNotFoundError("/dev/ttyUSB0")

        def close(self) -> None:
            pass

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            main.RUNNING = False
            return (0.0, 0.0)

        def check_failsafe(self, last_frame_time: float) -> bool:
            return main.time.monotonic() - last_frame_time > main.config.FAILSAFE_TIMEOUT_S

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            fake_time[0] += 1.0

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            failsafe_calls.append("failsafe")

        def sos_beacon(self) -> None:
            pass

        def low_voltage_alarm(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

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

    class FakeStats:
        def cpu_percent(self) -> float:
            return 0.0

        def memory_percent(self) -> float:
            return 0.0

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main, "SystemStats", FakeStats)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 999.0)
    monkeypatch.setattr(main.config, "FAILSAFE_TIMEOUT_S", 0.5)
    monkeypatch.setattr(main.time, "monotonic", lambda: fake_time[0])
    monkeypatch.setattr(main.time, "sleep", lambda delay: fake_time.__setitem__(0, fake_time[0] + delay))
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert failsafe_calls == []


def test_main_does_not_start_playlist_melody_during_arm_or_disarm_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    tone_calls: list[str] = []
    playlist_calls: list[str] = []
    frames = iter(
        [
            [0.0, 0.0, 0.0, 0.0, 0.98, 0.0, 0.0, 0.0, 0.98],
            [0.0, 0.0, 0.0, 0.0, -0.98, 0.0, 0.0, 0.0, -0.98],
        ]
    )

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
            try:
                channels = next(frames)
            except StopIteration:
                main.RUNNING = False
                return None
            if channels[main.config.CH_ARM] < 0:
                main.RUNNING = False
            return channels

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

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            tone_calls.append("arm")

        def disarm_tone(self) -> None:
            tone_calls.append("disarm")

        def failsafe_tone(self) -> None:
            pass

        def sos_beacon(self) -> None:
            pass

        def low_voltage_alarm(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def play_named_async(self, name: str) -> None:
            playlist_calls.append(name)

        def play_wav(self, path: str) -> None:
            if "arm" in path:
                tone_calls.append("arm")

        def play_spectral(self, path: str) -> None:
            if "arm" in path:
                tone_calls.append("arm")

        def play_wav_async(self, path: str) -> None:
            if "arm" in path:
                tone_calls.append("arm")

        def play_spectral_async(self, path: str) -> None:
            if "arm" in path:
                tone_calls.append("arm")

        def set_control_active(self, active: bool) -> None:
            del active

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_MELODY", 8)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "DISARM_VOICES", [])
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert tone_calls == ["arm", "disarm"]
    assert playlist_calls == []


def test_main_does_not_start_playlist_melody_when_rc_melodies_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    playlist_calls: list[str] = []
    frames = iter(
        [
            [0.0, 0.0, 0.0, 0.0, -0.98, 0.0, 0.0, 0.0, -0.98],
            [0.0, 0.0, 0.0, 0.0, -0.98, 0.0, 0.0, 0.0, 0.98],
        ]
    )

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
            try:
                channels = next(frames)
            except StopIteration:
                main.RUNNING = False
                return None
            return channels

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

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            pass

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            pass

        def sos_beacon(self) -> None:
            pass

        def low_voltage_alarm(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def play_named_async(self, name: str) -> None:
            playlist_calls.append(name)

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "ENABLE_RC_MELODIES", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_MELODY", 8)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert playlist_calls == []


def test_main_only_plays_low_voltage_alarm_once_per_low_battery_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    low_voltage_calls: list[str] = []
    fake_time = [10.0]
    low_state = BatteryState(
        voltage=24.2,
        current=0.0,
        soc=20.0,
        cells=[3.45, 3.46, 3.47, 3.45, 3.46, 3.47, 3.44],
        temperatures=[25.0],
        min_cell=3.44,
        max_cell=3.47,
        delta=0.03,
    )

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._count = 0

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            self._count += 1
            if self._count >= 4:
                main.RUNNING = False
            fake_time[0] += 4.0
            return [0.0, 0.0, 0.0, 0.0, -0.98, 0.0, 0.0, 0.0, 0.0]

    class FakeTelemetry:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def attach(self, serial_port) -> None:
            assert serial_port is not None

        def send_battery(self, *args, **kwargs) -> None:
            pass

        def send_system_stats(self, *args, **kwargs) -> None:
            pass

    class FakeBMS:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeBMSPoller:
        def __init__(self, *args, **kwargs) -> None:
            self.latest_state = low_state

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            pass

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            pass

        def sos_beacon(self) -> None:
            pass

        def low_voltage_alarm(self) -> None:
            low_voltage_calls.append("low")

        def play_named(self, name: str) -> None:
            del name

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

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

    class FakeStats:
        def cpu_percent(self) -> float:
            return 0.0

        def memory_percent(self) -> float:
            return 0.0

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "_create_bms", lambda: FakeBMS())
    monkeypatch.setattr(main, "BMSPoller", FakeBMSPoller)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main, "SystemStats", FakeStats)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.time, "monotonic", lambda: fake_time[0])
    monkeypatch.setattr(main.time, "sleep", lambda delay: fake_time.__setitem__(0, fake_time[0] + delay))
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr(main.config, "LOW_CELL_VOLTAGE", 3.5)
    monkeypatch.setattr(main.config, "LOW_PACK_VOLTAGE", 21.0)
    monkeypatch.setattr(main.config, "LOW_VOLTAGE_VOICES", [])
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert low_voltage_calls == ["low"]


def test_main_sets_control_priority_when_drive_input_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    control_active_calls: list[bool] = []
    frames = iter(
        [
            [0.0, 0.75, 0.0, 0.10, 0.98, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.00, 0.0, 0.00, 0.98, 0.0, 0.0, 0.0, 0.0],
        ]
    )

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
            try:
                return next(frames)
            except StopIteration:
                main.RUNNING = False
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

    class FakeDrive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs) -> tuple[float, float]:
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def off(self) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            pass

        def disarm_tone(self) -> None:
            pass

        def failsafe_tone(self) -> None:
            pass

        def sos_beacon(self) -> None:
            pass

        def low_voltage_alarm(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            del name

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            control_active_calls.append(active)

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
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", FakeDrive)
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert control_active_calls == [True, False]


def test_main_clears_battery_telemetry_when_bms_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
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
            if self._read_count >= 2:
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
    monkeypatch.setattr(main.config, "MAIN_LOOP_HZ", 1000)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert sent_packets == [(0.0, 0.0, 0, 0)]


def test_connect_pigpio_retries_on_initial_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """_connect_pigpio should retry when first attempt fails and succeed on later attempt."""
    main = importlib.import_module("main")

    call_count = 0

    class DisconnectedPi:
        connected = False
        def stop(self) -> None:
            pass

    class ConnectedPi:
        connected = True
        def stop(self) -> None:
            pass

    def fake_pi():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return DisconnectedPi()
        return ConnectedPi()

    monkeypatch.setattr(main.pigpio, "pi", fake_pi)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    pi = main._connect_pigpio(retries=5, delay=0.5)
    assert pi.connected is True
    assert call_count == 3


def test_connect_pigpio_returns_disconnected_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """_connect_pigpio returns disconnected pi if all retries fail."""
    main = importlib.import_module("main")

    class DisconnectedPi:
        connected = False
        def stop(self) -> None:
            pass

    monkeypatch.setattr(main.pigpio, "pi", lambda: DisconnectedPi())
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    pi = main._connect_pigpio(retries=3, delay=0.5)
    assert pi.connected is False