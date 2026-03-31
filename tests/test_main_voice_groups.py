from __future__ import annotations

import importlib

import pytest


def test_main_uses_round_robin_voice_group_for_startup(monkeypatch: pytest.MonkeyPatch) -> None:
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

        def drive(self, *args, **kwargs):
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def startup_tone(self) -> None:
            played.append("startup_tone")

        def shutdown_tone(self) -> None:
            pass

        def off(self) -> None:
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
            played.append(name)

        def play_named_async(self, name: str) -> None:
            played.append(name)

        def play_wav(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral(self, path: str) -> None:
            played.append(f"spectral:{path}")

        def play_wav_async(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral_async(self, path: str) -> None:
            played.append(f"spectral:{path}")

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
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", True)
    monkeypatch.setattr(main.config, "STARTUP_VOICES", ["/app/voice/startup_a.wav", "/app/voice/startup_b.wav"])
    monkeypatch.setattr(main.config, "VOICE_SELECTION_MODE", "ROUND_ROBIN")
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert "spectral:/app/voice/startup_a.wav" in played
    assert "wav:/app/voice/startup_a.wav" not in played


def test_main_uses_named_synth_for_startup_when_sound_mode_is_synth(monkeypatch: pytest.MonkeyPatch) -> None:
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

        def drive(self, *args, **kwargs):
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def startup_tone(self) -> None:
            played.append("startup_tone")

        def shutdown_tone(self) -> None:
            pass

        def off(self) -> None:
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
            played.append(name)

        def play_named_async(self, name: str) -> None:
            played.append(name)

        def play_wav(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral(self, path: str) -> None:
            played.append(f"spectral:{path}")

        def play_wav_async(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral_async(self, path: str) -> None:
            played.append(f"spectral:{path}")

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
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", True)
    monkeypatch.setattr(main.config, "STARTUP_VOICES", ["/app/voice/startup_a.wav"])
    monkeypatch.setattr(main.config, "VOICE_SELECTION_MODE", "ROUND_ROBIN")
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "biba_signature")
    monkeypatch.setattr(main.config, "SOUND_MODE", "synth", raising=False)
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert "biba_signature" in played
    assert "spectral:/app/voice/startup_a.wav" not in played
    assert "wav:/app/voice/startup_a.wav" not in played


def test_main_uses_voice_group_for_disarm(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._frames = [
                [0.0, 0.0, 0.0, 0.0, 0.98],
                [0.0, 0.0, 0.0, 0.0, -0.98],
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

        def stop(self) -> None:
            pass

        def drive(self, *args, **kwargs):
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def off(self) -> None:
            pass

        def connected_tone(self) -> None:
            pass

        def disconnected_tone(self) -> None:
            pass

        def arm_tone(self) -> None:
            played.append("arm_tone")

        def disarm_tone(self) -> None:
            played.append("disarm_tone")

        def failsafe_tone(self) -> None:
            pass

        def sos_beacon(self) -> None:
            pass

        def low_voltage_alarm(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            played.append(name)

        def play_named_async(self, name: str) -> None:
            played.append(name)

        def play_wav(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral(self, path: str) -> None:
            played.append(f"spectral:{path}")

        def play_wav_async(self, path: str) -> None:
            played.append(f"wav:{path}")

        def play_spectral_async(self, path: str) -> None:
            played.append(f"spectral:{path}")

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
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "CH_ARM", 4)
    monkeypatch.setattr(main.config, "ARM_THRESHOLD", 0.3)
    monkeypatch.setattr(main.config, "ARM_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "DISARM_VOICES", ["/app/voice/disarm_wait.wav"])
    monkeypatch.setattr(main.config, "VOICE_SELECTION_MODE", "ROUND_ROBIN")
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert "spectral:/app/voice/disarm_wait.wav" in played
    assert "wav:/app/voice/disarm_wait.wav" not in played


def test_main_uses_sos_melody_even_when_sos_voice_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    main = importlib.import_module("main")
    played: list[str] = []

    class FakePi:
        connected = True

        def stop(self) -> None:
            pass

    class FakeReceiver:
        def __init__(self, *args, **kwargs) -> None:
            self.serial_port = object()
            self._calls = 0

        def open(self) -> None:
            pass

        def close(self) -> None:
            pass

        def get_channels(self):
            self._calls += 1
            if self._calls > 1:
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

        def drive(self, *args, **kwargs):
            return (0.0, 0.0)

        def check_failsafe(self, *args, **kwargs) -> bool:
            return False

        def emergency_stop(self) -> None:
            pass

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def startup_tone(self) -> None:
            pass

        def shutdown_tone(self) -> None:
            pass

        def off(self) -> None:
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
            played.append("sos_beacon")

        def low_voltage_alarm(self) -> None:
            pass

        def play_named(self, name: str) -> None:
            played.append(name)

        def play_named_async(self, name: str) -> None:
            played.append(name)

        def play_spectral(self, path: str) -> None:
            played.append(path)

        def play_spectral_async(self, path: str) -> None:
            played.append(path)

        def set_control_active(self, active: bool) -> None:
            del active

    class FakeBeacon:
        def __init__(self, *args, **kwargs) -> None:
            self._returned = False

        def on_connected(self) -> None:
            pass

        def set_manual(self, *args, **kwargs) -> None:
            pass

        def on_failsafe(self, *args, **kwargs) -> None:
            pass

        def should_sos(self, *args, **kwargs) -> bool:
            if self._returned:
                return False
            self._returned = True
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
    monkeypatch.setattr(main.config, "STARTUP_VOICE_ENABLED", False)
    monkeypatch.setattr(main.config, "STARTUP_MELODY", "")
    monkeypatch.setattr(main.config, "SOS_VOICES", ["/app/voice/sos_comply.wav"])
    monkeypatch.setattr(main.config, "VOICE_SELECTION_MODE", "ROUND_ROBIN")
    monkeypatch.setattr(main, "RUNNING", True)

    assert main.main() == 0
    assert "sos_beacon" in played
    assert "/app/voice/sos_comply.wav" not in played