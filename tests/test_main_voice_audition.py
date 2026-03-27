from __future__ import annotations

import importlib
from pathlib import Path


def test_main_robot_audition_mode_plays_manifest_candidates(monkeypatch, tmp_path: Path) -> None:
    main = importlib.import_module("main")
    played: list[str] = []
    manifest_path = tmp_path / "audition.yml"
    manifest_path.write_text(
        """
event: startup
profile: command_slow
candidates:
    - /app/voice-work/robot-audition/startup/candidate1.wav
    - /app/voice-work/robot-audition/startup/candidate2.wav
labels:
    - v01
    - v02
""".strip()
        + "\n",
        encoding="utf-8",
    )

    class FakePi:
        connected = True

        def stop(self) -> None:
            played.append("pi.stop")

    class FakeMotorSynth:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def play_spectral(self, path: str) -> None:
            played.append(path)

        def off(self) -> None:
            played.append("off")

    monkeypatch.setattr(main.pigpio, "pi", lambda: FakePi())
    monkeypatch.setattr(main, "MotorSynth", FakeMotorSynth)
    monkeypatch.setattr(main.config, "VOICE_AUDITION_ENABLED", True)
    monkeypatch.setattr(main.config, "VOICE_AUDITION_MANIFEST", str(manifest_path))
    monkeypatch.setattr(main.config, "LEFT_MOTOR_ENABLED", True)
    monkeypatch.setattr(main.config, "RIGHT_MOTOR_ENABLED", False)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_RPWM", 18)
    monkeypatch.setattr(main.config, "LEFT_MOTOR_LPWM", 13)

    assert main.main() == 0
    assert played[:2] == [
        "/app/voice-work/robot-audition/startup/candidate1.wav",
        "/app/voice-work/robot-audition/startup/candidate2.wav",
    ]
    assert "off" in played
    assert "pi.stop" in played
