from __future__ import annotations

import importlib
import json
import logging

import pytest

from bms.daly import BatteryState
from motors.current_control import MotorCurrentSample
from motors.current_sense import NullMotorCurrentReader


def test_is_armed_uses_configured_channel_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "CH_ARM", 2)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.25)

    assert main._is_armed([0.0, 0.1, 0.3]) is True
    assert main._is_armed([0.0, 0.1, 0.2]) is False


def test_is_muted_uses_configured_channel_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "CH_MUTE", 6)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.25)

    assert main._is_muted([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4]) is True
    assert main._is_muted([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2]) is False


def test_play_grouped_voice_async_if_allowed_skips_when_muted() -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakeSelector:
        def choose(self, event: str, voices: list[str]) -> str | None:
            assert event == "connected"
            assert voices == ["/app/voice/connected_online.wav"]
            return voices[0]

    class FakeBuzzer:
        def play_spectral_async(self, path: str) -> None:
            played.append(path)

    result = main._play_grouped_voice_async_if_allowed(
        FakeSelector(),
        "connected",
        ["/app/voice/connected_online.wav"],
        FakeBuzzer(),
        mute_active=True,
    )

    assert result is False
    assert played == []


def test_play_grouped_voice_uses_wav_in_voice_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakeSelector:
        def choose(self, event: str, voices: list[str]) -> str | None:
            assert event == "connected"
            return voices[0]

    class FakeBuzzer:
        def play_wav(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral(self, path: str) -> None:
            played.append(f"spectral:{path}")

    monkeypatch.setattr(main.config, "SOUND_MODE", "voice", raising=False)

    result = main._play_grouped_voice(
        FakeSelector(),
        "connected",
        ["/app/voice/connected_online.wav"],
        FakeBuzzer(),
    )

    assert result is True
    assert played == ["wav:/app/voice/connected_online.wav"]


def test_play_grouped_voice_uses_spectral_in_spectral_voice_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakeSelector:
        def choose(self, event: str, voices: list[str]) -> str | None:
            assert event == "connected"
            return voices[0]

    class FakeBuzzer:
        def play_wav(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral(self, path: str) -> None:
            played.append(f"spectral:{path}")

    monkeypatch.setattr(main.config, "SOUND_MODE", "spectral_voice", raising=False)

    result = main._play_grouped_voice(
        FakeSelector(),
        "connected",
        ["/app/voice/connected_online.wav"],
        FakeBuzzer(),
    )

    assert result is True
    assert played == ["spectral:/app/voice/connected_online.wav"]


def test_play_grouped_voice_async_uses_named_synth_in_synth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakeSelector:
        def choose(self, event: str, voices: list[str]) -> str | None:
            assert event == "connected"
            return voices[0]

    class FakeBuzzer:
        def play_named_async(self, name: str) -> None:
            played.append(f"named:{name}")

        def play_wav_async(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral_async(self, path: str) -> None:
            played.append(f"spectral:{path}")

    monkeypatch.setattr(main.config, "SOUND_MODE", "synth", raising=False)

    result = main._play_grouped_voice_async(
        FakeSelector(),
        "connected",
        ["/app/voice/connected_online.wav"],
        FakeBuzzer(),
    )

    assert result is True
    assert played == ["named:connected"]


def test_play_named_async_if_allowed_skips_when_muted() -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakeBuzzer:
        def play_named_async(self, name: str) -> None:
            played.append(name)

    main._play_named_async_if_allowed(FakeBuzzer(), "melody", mute_active=True)

    assert played == []


def test_get_channel_returns_zero_when_index_is_missing() -> None:
    main = importlib.import_module("main")

    assert main._get_channel([0.4, -0.2], 1) == -0.2
    assert main._get_channel([0.4, -0.2], 3) == 0.0


def test_create_buzzer_preserves_left_and_right_motor_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    captured: dict[str, object] = {}

    class FakeMotorSynth:
        def __init__(self, pi, pwm_pins, duty_cycle=50000, comp_pins=None, **kwargs) -> None:
            captured["pi"] = pi
            captured["pwm_pins"] = pwm_pins
            captured["duty_cycle"] = duty_cycle
            captured["comp_pins"] = comp_pins
            captured.update(kwargs)

    fake_pi = object()

    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_ENABLED", True)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_ENABLED", True)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_RPWM", 12)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LPWM", 18)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_RPWM", 19)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LPWM", 13)

    main._create_buzzer(fake_pi)

    assert captured["pi"] is fake_pi
    assert captured["pwm_pins"] == [12, 19]
    assert captured["comp_pins"] == [18, 13]
    assert captured["left_pwm_pins"] == [12]
    assert captured["left_comp_pins"] == [18]
    assert captured["right_pwm_pins"] == [19]
    assert captured["right_comp_pins"] == [13]


def test_create_motor_test_executor_uses_buzzer_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    captured: dict[str, object] = {}

    class FakeBuzzer:
        def play_manual_split_pwm(self, *args, **kwargs) -> None:
            del args, kwargs

    class FakeDrive:
        def emergency_stop(self) -> None:
            pass

    def fake_executor(synth, before_run=None, synth_factory=None):
        captured["synth"] = synth
        captured["before_run"] = before_run
        captured["synth_factory"] = synth_factory
        return "executor"

    monkeypatch.setattr(main.config, "MOTOR_TEST_API_ENABLED", True)
    monkeypatch.setattr(main, "MotorTestExecutor", fake_executor)

    buzzer = FakeBuzzer()
    drive = FakeDrive()
    executor = main._create_motor_test_executor(buzzer, drive)

    assert executor == "executor"
    assert captured["synth"] is buzzer
    assert callable(captured["before_run"])
    assert callable(captured["synth_factory"])


def test_create_motor_test_executor_returns_none_for_unsupported_buzzer(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")

    class FakeBuzzer:
        pass

    class FakeDrive:
        def emergency_stop(self) -> None:
            pass

    monkeypatch.setattr(main.config, "MOTOR_TEST_API_ENABLED", True)

    assert main._create_motor_test_executor(FakeBuzzer(), FakeDrive()) is None


def test_create_motor_test_server_uses_executor_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    captured: dict[str, object] = {}
    fake_server = object()

    def fake_server_factory(executor, *, host: str, port: int):
        captured["executor"] = executor
        captured["host"] = host
        captured["port"] = port
        return fake_server

    monkeypatch.setattr(main.config, "MOTOR_TEST_API_HOST", "0.0.0.0")
    monkeypatch.setattr(main.config, "MOTOR_TEST_API_PORT", 8765)
    monkeypatch.setattr(main, "create_motor_test_server", fake_server_factory)

    executor = object()
    server = main._create_motor_test_server(executor)

    assert server is fake_server
    assert captured["executor"] is executor
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8765


def test_shutdown_motor_test_server_closes_server() -> None:
    main = importlib.import_module("main")
    calls: list[str] = []

    class FakeServer:
        def shutdown(self) -> None:
            calls.append("shutdown")

        def server_close(self) -> None:
            calls.append("server_close")

    main._shutdown_motor_test_server(FakeServer())

    assert calls == ["shutdown", "server_close"]


def test_main_skips_drive_updates_while_manual_motor_test_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    mix_calls: list[tuple[float, float, float]] = []
    apply_calls: list[tuple[float, float]] = []
    drive_calls: list[tuple[float, float, float]] = []
    control_calls: list[bool] = []

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [[0.0, 0.0, 0.0, 0.0, -0.98, 0.0]]

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
        def mix_and_ramp(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            mix_calls.append((throttle, steering, dt))
            return (0.0, 0.0)

        def apply_output(self, left_duty: float, right_duty: float, **kwargs) -> tuple[float, float]:
            apply_calls.append((left_duty, right_duty))
            return (left_duty, right_duty)

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
            control_calls.append(active)

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

    class FakeMotorTestExecutor:
        is_active = True

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", lambda *args, **kwargs: FakeDrive())
    monkeypatch.setattr(main, "_create_buzzer", lambda pi: FakeMotorSynth())
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main, "_create_motor_test_executor", lambda buzzer, drive: FakeMotorTestExecutor())
    monkeypatch.setattr(main, "_create_motor_test_server", lambda executor: None)
    monkeypatch.setattr(main, "_start_motor_test_server", lambda server: None)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert mix_calls == []
    assert apply_calls == []
    assert drive_calls == []
    assert control_calls and control_calls[-1] is False


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

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def play_wav_async(self, path: str) -> None:
            del path

        def play_spectral_async(self, path: str) -> None:
            del path

        def play_named_async(self, name: str) -> None:
            del name

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


def test_main_enters_trim_mode_and_uses_live_ch9_for_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    applied_outputs: list[tuple[float, float]] = []
    sound_calls: list[str] = []

    def frame(ch1: float, ch2: float, ch3: float, ch4: float, arm: float, ch9: float) -> list[float]:
        return [ch1, ch2, ch3, ch4, arm, 0.0, 0.0, 0.0, ch9]

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.5),
                frame(0.0, 1.0, 0.0, 0.0, 1.0, 0.5),
            ]

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            frame_value = self._frames.pop(0)
            if not self._frames:
                main.RUNNING = False
            return frame_value

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
        def mix_and_ramp(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del steering, dt
            return throttle, throttle

        def apply_output(self, left_duty: float, right_duty: float, **kwargs) -> tuple[float, float]:
            applied_outputs.append((left_duty, right_duty))
            return left_duty, right_duty

        def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del throttle, steering, dt
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
            sound_calls.append(name)

        def play_spectral_async(self, path: str) -> None:
            del path

        def sos_beacon(self) -> None:
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

    monotonic_counter = iter(index * 0.5 for index in range(100))

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", lambda *args, **kwargs: FakeDrive())
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main.time, "monotonic", lambda: next(monotonic_counter))
    monkeypatch.setattr(main, "_load_saved_motor_trim", lambda: 0.0)
    monkeypatch.setattr(main, "_save_motor_trim", lambda trim: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "CH_TRIM", 8)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "MOTOR_TRIM_CONFIRM_HOLD_S", 5.0)
    monkeypatch.setattr(main.config, "MOTOR_TRIM_MAX_EFFECT", 0.2)
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 999.0)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert applied_outputs[-1][0] == pytest.approx(1.0)
    assert applied_outputs[-1][1] == pytest.approx(0.9)
    assert sound_calls == ["trim_enter"]


def test_main_confirmation_gesture_saves_trim_and_exits_trim_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    applied_outputs: list[tuple[float, float]] = []
    saved_trims: list[float] = []
    sound_calls: list[str] = []

    def frame(ch1: float, ch2: float, ch3: float, ch4: float, arm: float, ch9: float) -> list[float]:
        return [ch1, ch2, ch3, ch4, arm, 0.0, 0.0, 0.0, ch9]

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
                frame(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, -0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, -0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, -0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, -0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, -0.5),
                frame(1.0, 1.0, 1.0, 1.0, 0.0, -0.5),
                frame(0.0, 1.0, 0.0, 0.0, 1.0, 1.0),
            ]

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            frame_value = self._frames.pop(0)
            if not self._frames:
                main.RUNNING = False
            return frame_value

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
        def mix_and_ramp(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del steering, dt
            return throttle, throttle

        def apply_output(self, left_duty: float, right_duty: float, **kwargs) -> tuple[float, float]:
            applied_outputs.append((left_duty, right_duty))
            return left_duty, right_duty

        def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del throttle, steering, dt
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
            sound_calls.append(name)

        def play_spectral_async(self, path: str) -> None:
            del path

        def sos_beacon(self) -> None:
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

    monotonic_counter = iter(index * 0.5 for index in range(200))

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", lambda *args, **kwargs: FakeDrive())
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main.time, "monotonic", lambda: next(monotonic_counter))
    monkeypatch.setattr(main, "_load_saved_motor_trim", lambda: 0.0)
    monkeypatch.setattr(main, "_save_motor_trim", lambda trim: saved_trims.append(trim))
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "CH_TRIM", 8)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "MOTOR_TRIM_CONFIRM_HOLD_S", 5.0)
    monkeypatch.setattr(main.config, "MOTOR_TRIM_MAX_EFFECT", 0.2)
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 999.0)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert saved_trims == [pytest.approx(-0.1)]
    assert applied_outputs[-1][0] == pytest.approx(0.9)
    assert applied_outputs[-1][1] == pytest.approx(1.0)
    assert sound_calls == ["trim_enter", "trim_exit"]


def test_main_allows_sos_beacon_while_muted(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    sos_calls: list[str] = []
    frames = iter(
        [
            [0.0, 0.0, 0.0, 0.0, -0.98, 0.0, 0.98, 0.0, 0.0],
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
            sos_calls.append("sos")

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

        def play_wav_async(self, path: str) -> None:
            del path

        def play_spectral_async(self, path: str) -> None:
            del path

        def set_control_active(self, active: bool) -> None:
            del active

    class FakeBeacon:
        def __init__(self, *args, **kwargs) -> None:
            self._called = False

        def on_connected(self) -> None:
            pass

        def set_manual(self, *args, **kwargs) -> None:
            pass

        def on_failsafe(self, *args, **kwargs) -> None:
            pass

        def should_sos(self, *args, **kwargs) -> bool:
            if self._called:
                main.RUNNING = False
                return False
            self._called = True
            return True

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
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_MUTE", 6)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert sos_calls == ["sos"]


def test_main_replays_arm_sound_when_mute_is_disabled_while_still_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    tone_calls: list[str] = []
    frames = iter(
        [
            [0.0, 0.0, 0.0, 0.0, 0.98, 0.0, 0.98, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.98, 0.0, -0.98, 0.0],
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
            if channels[main.config.CH_MUTE] < 0:
                main.RUNNING = False
            return channels

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

        def connected_tone_async(self) -> None:
            tone_calls.append("connected")

        def disconnected_tone_async(self) -> None:
            tone_calls.append("disconnected")

        def arm_tone_async(self) -> None:
            tone_calls.append("arm")

        def disarm_tone_async(self) -> None:
            tone_calls.append("disarm")

        def failsafe_tone_async(self) -> None:
            tone_calls.append("failsafe")

        def low_voltage_alarm_async(self) -> None:
            tone_calls.append("low")

        def sos_beacon(self) -> None:
            tone_calls.append("sos")

        def play_named(self, name: str) -> None:
            del name

        def play_named_async(self, name: str) -> None:
            del name

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def play_wav_async(self, path: str) -> None:
            del path

        def play_spectral_async(self, path: str) -> None:
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
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "ARM_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_MUTE", 6)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 999.0)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert tone_calls == ["arm"]


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


def test_encode_battery_status_bits_preserves_direction_and_sets_flags() -> None:
    main = importlib.import_module("main")

    status_bits = main._encode_battery_status_bits(
        current_a=-3.2,
        armed=True,
        mute_active=True,
        beacon_active=True,
    )

    assert status_bits == 0b11110


def test_encode_battery_status_bits_includes_trim_mode_flag() -> None:
    main = importlib.import_module("main")

    status_bits = main._encode_battery_status_bits(
        current_a=-3.2,
        armed=True,
        mute_active=True,
        beacon_active=True,
        trim_mode_active=True,
    )

    assert status_bits == 0b111110


def test_apply_motor_trim_leaves_duties_unchanged_when_trim_is_zero() -> None:
    main = importlib.import_module("main")

    left_duty, right_duty = main._apply_motor_trim(0.65, 0.65, 0.0)

    assert left_duty == pytest.approx(0.65)
    assert right_duty == pytest.approx(0.65)


def test_apply_motor_trim_positive_reduces_only_right_side() -> None:
    main = importlib.import_module("main")

    left_duty, right_duty = main._apply_motor_trim(0.75, 0.75, 0.20)

    assert left_duty == pytest.approx(0.75)
    assert right_duty == pytest.approx(0.60)


def test_apply_motor_trim_negative_reduces_only_left_side() -> None:
    main = importlib.import_module("main")

    left_duty, right_duty = main._apply_motor_trim(0.75, 0.75, -0.20)

    assert left_duty == pytest.approx(0.60)
    assert right_duty == pytest.approx(0.75)


def test_apply_motor_trim_clamps_to_maximum_effect() -> None:
    main = importlib.import_module("main")

    left_duty, right_duty = main._apply_motor_trim(1.0, 1.0, 0.5)

    assert left_duty == pytest.approx(1.0)
    assert right_duty == pytest.approx(0.8)


def test_load_saved_motor_trim_defaults_to_zero_when_file_missing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_TRIM_SETTINGS_PATH", str(tmp_path / "motor-trim.json"))

    assert main._load_saved_motor_trim() == pytest.approx(0.0)


def test_load_saved_motor_trim_warns_and_defaults_when_file_is_invalid(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    main = importlib.import_module("main")
    settings_path = tmp_path / "motor-trim.json"
    settings_path.write_text("{not-json}", encoding="utf-8")
    monkeypatch.setattr(main.config, "MOTOR_TRIM_SETTINGS_PATH", str(settings_path))

    with caplog.at_level(logging.WARNING, logger="biba-controller"):
        trim = main._load_saved_motor_trim()

    assert trim == pytest.approx(0.0)
    assert "Failed to load motor trim settings" in caplog.text


def test_save_motor_trim_settings_persists_effective_trim(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    settings_path = tmp_path / "motor-trim.json"
    monkeypatch.setattr(main.config, "MOTOR_TRIM_SETTINGS_PATH", str(settings_path))

    main._save_motor_trim(0.125)

    assert settings_path.exists() is True
    saved = settings_path.read_text(encoding="utf-8")
    assert '"trim": 0.125' in saved
    assert '"updated_at":' in saved


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


def test_send_battery_telemetry_includes_arm_mute_and_beacon_flags() -> None:
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

    main._send_battery_telemetry(
        FakeTelemetry(),
        state,
        armed=True,
        mute_active=True,
        beacon_active=True,
    )

    assert sent_packets == [(24.1, 1.6, 0b11101, 63)]


def test_send_battery_telemetry_emits_trace_logs_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    main = importlib.import_module("main")

    class FakeTelemetry:
        def send_battery(self, voltage_v: float, current_a: float, capacity_mah: int, remaining_pct: int) -> None:
            assert (voltage_v, current_a, capacity_mah, remaining_pct) == (24.1, 1.3, 2, 63)

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

    monotonic_values = iter([10.25])
    monkeypatch.setattr(main.config, "BMS_TELEMETRY_TRACE_ENABLED", True, raising=False)
    monkeypatch.setattr(main.time, "monotonic", lambda: next(monotonic_values))

    with caplog.at_level(logging.INFO, logger="biba-controller"):
        main._send_battery_telemetry(FakeTelemetry(), state, consumed_at_s=10.0)

    assert "Battery telemetry trace stage=consume t=10.000000" in caplog.text
    assert "Battery telemetry trace stage=send t=10.250000" in caplog.text
    assert "raw_current_a=-1.30" in caplog.text


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


def test_create_motor_current_reader_uses_directional_channel_config(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    captured: dict[str, object] = {}

    def fake_open_ads1115_current_reader(**kwargs):
        captured.update(kwargs)
        return NullMotorCurrentReader()

    monkeypatch.setattr(main.config, "MOTOR_CURRENT_SENSE_ENABLED", True)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_SENSE_I2C_ADDRESS", 0x48)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL", 2)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL", 3)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL", 0)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL", 1)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_SENSE_GAIN", "1")
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ", 32.0)
    monkeypatch.setattr(main, "open_ads1115_current_reader", fake_open_ads1115_current_reader)

    main._create_motor_current_reader()

    assert captured["left_forward_channel"] == 2
    assert captured["left_reverse_channel"] == 3
    assert captured["right_forward_channel"] == 0
    assert captured["right_reverse_channel"] == 1


def test_motor_current_trace_logs_armed_motor_activity_even_with_zero_bms_current(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_TRACE_POST_ROLL_S", 2.0)

    should_log, last_activity_at_s = main._update_motor_current_trace_window(
        armed=True,
        raw_throttle=0.6,
        steering=0.0,
        left_duty=0.5,
        right_duty=0.5,
        left_sample=MotorCurrentSample(current_a=0.0, valid=True),
        right_sample=MotorCurrentSample(current_a=0.0, valid=True),
        now_s=10.0,
        last_activity_at_s=None,
    )

    assert should_log is True
    assert last_activity_at_s == pytest.approx(10.0)


def test_motor_current_trace_keeps_logging_during_post_roll(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_TRACE_POST_ROLL_S", 2.0)

    should_log, last_activity_at_s = main._update_motor_current_trace_window(
        armed=True,
        raw_throttle=0.0,
        steering=0.0,
        left_duty=0.0,
        right_duty=0.0,
        left_sample=MotorCurrentSample(current_a=0.0, valid=True),
        right_sample=MotorCurrentSample(current_a=0.0, valid=True),
        now_s=11.5,
        last_activity_at_s=10.0,
    )

    assert should_log is True
    assert last_activity_at_s == pytest.approx(10.0)


def test_motor_current_trace_record_includes_bms_age_and_sample_details() -> None:
    main = importlib.import_module("main")
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

    record = main._build_motor_current_trace_record(
        session_id="session-1",
        sample_index=7,
        now_s=10.5,
        wall_time_iso="2026-03-30T12:00:00Z",
        armed=True,
        raw_throttle=0.6,
        filtered_throttle=0.55,
        steering=0.1,
        control_active=True,
        requested_left=0.6,
        requested_right=0.5,
        limited_left=0.6,
        limited_right=0.5,
        trimmed_left=0.58,
        trimmed_right=0.48,
        left_duty=0.58,
        right_duty=0.48,
        left_sample=MotorCurrentSample(current_a=3.2, valid=True, voltage_v=1.25, raw_adc=10001, channel=2),
        right_sample=MotorCurrentSample(current_a=2.8, valid=True, voltage_v=1.10, raw_adc=9002, channel=0),
        battery_state=state,
        bms_sample_monotonic_s=9.9,
        mute_active=False,
        beacon_active=False,
        trim_mode_active=False,
        trace_reason="active",
    )

    assert record["session_id"] == "session-1"
    assert record["sample_index"] == 7
    assert record["bms_current_a"] == pytest.approx(1.6)
    assert record["bms_age_s"] == pytest.approx(0.6)
    assert record["left_raw_adc"] == 10001
    assert record["right_raw_adc"] == 9002
    assert record["left_voltage_v"] == pytest.approx(1.25)
    assert record["right_voltage_v"] == pytest.approx(1.10)
    assert record["left_active_channel"] == 2
    assert record["right_active_channel"] == 0
    assert record["trace_reason"] == "active"


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
        def read_currents(self, left_duty: float = 0.0, right_duty: float = 0.0) -> tuple[MotorCurrentSample, MotorCurrentSample]:
            del left_duty, right_duty
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


def test_main_writes_motor_current_trace_during_armed_activity(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    main = importlib.import_module("main")
    trace_path = tmp_path / "current-trace.jsonl"

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                [0.0, 0.8, 0.0, 0.0, 0.98, 0.0],
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
        def mix_and_ramp(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del steering, dt
            return throttle, throttle

        def apply_output(self, left_duty: float, right_duty: float, **kwargs) -> tuple[float, float]:
            return left_duty, right_duty

        def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
            del throttle, steering, dt
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

        def play_wav(self, path: str) -> None:
            del path

        def play_spectral(self, path: str) -> None:
            del path

        def play_wav_async(self, path: str) -> None:
            del path

        def play_spectral_async(self, path: str) -> None:
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

    class FakeCurrentReader:
        def read_currents(self, left_duty: float = 0.0, right_duty: float = 0.0) -> tuple[MotorCurrentSample, MotorCurrentSample]:
            del left_duty, right_duty
            return (
                MotorCurrentSample(current_a=3.2, valid=True, voltage_v=1.25, raw_adc=10001, channel=2),
                MotorCurrentSample(current_a=2.8, valid=True, voltage_v=1.10, raw_adc=9002, channel=0),
            )

        def close(self) -> None:
            pass

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "CRSFReceiver", FakeReceiver)
    monkeypatch.setattr(main, "CRSFTelemetry", FakeTelemetry)
    monkeypatch.setattr(main, "DalyBMS", FakeBMS)
    monkeypatch.setattr(main, "_create_motor_pair", lambda pi: (object(), object()))
    monkeypatch.setattr(main, "DifferentialDrive", lambda *args, **kwargs: FakeDrive())
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main, "BeaconManager", FakeBeacon)
    monkeypatch.setattr(main, "_create_motor_current_reader", lambda: FakeCurrentReader())
    monkeypatch.setattr(main.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "CH_THROTTLE", 1)
    monkeypatch.setattr(main.config, "CH_STEERING", 3)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "MOTOR_DEADBAND", 0.05)
    monkeypatch.setattr(main.config, "BMS_POLL_INTERVAL_S", 999.0)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_TRACE_ENABLED", True)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_TRACE_PATH", str(trace_path))
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_TRACE_POST_ROLL_S", 2.0)
    monkeypatch.setattr(main.config, "MOTOR_CURRENT_TRACE_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0

    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["armed"] is True
    assert records[0]["left_raw_adc"] == 10001
    assert records[0]["left_active_channel"] == 2
    assert records[0]["right_active_channel"] == 0
    assert records[0]["bms_present"] is False
    assert records[0]["trace_reason"] == "active"


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
    monkeypatch.setattr(main.config, "LEFT_MOTOR_RPWM", 12)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LPWM", 18)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_REN", 23)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LEN", 24)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_RPWM", 19)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LPWM", 13)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_REN", 20)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LEN", 21)
    monkeypatch.setattr(main.config, "MOTOR1_INVERTED", 0)
    monkeypatch.setattr(main.config, "MOTOR2_INVERTED", 1)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0
    assert created == [
        (12, 18, 23, 24, False),
        (19, 13, 20, 21, True),
    ]
    assert synth_created == [{"pins": (12, 19), "comp": (18, 13)}]


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
    monkeypatch.setattr(main.config, "LEFT_MOTOR_RPWM", 12)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LPWM", 18)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_RPWM", 19)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_LPWM", 13)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_ENABLED", True)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_ENABLED", False)
    monkeypatch.setattr(main, "RUNNING", False)

    assert main.main() == 0
    assert synth_created == [{"pins": (12,), "comp": (18,)}]


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