from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_voice_prep_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "voice_prep.py"
    assert module_path.exists(), f"missing script: {module_path}"
    spec = importlib.util.spec_from_file_location("voice_prep", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_manifest_reads_event_entries(tmp_path: Path) -> None:
    module = _load_voice_prep_module()
    manifest_path = tmp_path / "phrases.yml"
    manifest_path.write_text(
        """
events:
  startup:
    text: я вернулся
    profiles:
      - command_slow
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = module.load_manifest(manifest_path)

    assert manifest["startup"].text == "я вернулся"
    assert manifest["startup"].profiles == ["command_slow"]


def test_load_manifest_reads_alternative_phrases(tmp_path: Path) -> None:
        module = _load_voice_prep_module()
        manifest_path = tmp_path / "phrases.yml"
        manifest_path.write_text(
                """
events:
    sos:
        text: щиты пали, запрашиваю подкрепление
        tts_text: shchity pali, zaprashayu podkreplenie
        alternatives:
            - щит пробит, вызываю подмогу
            - контур рушится, держите строй
        tts_alternatives:
            - shchit probit, vyzyvayu podmogu
            - kontur rushitsya, derzhite stroy
        profiles:
            - robot_harsh
""".strip()
                + "\n",
                encoding="utf-8",
        )

        manifest = module.load_manifest(manifest_path)

        assert manifest["sos"].alternatives == [
                "щит пробит, вызываю подмогу",
                "контур рушится, держите строй",
        ]
        assert manifest["sos"].tts_text == "shchity pali, zaprashayu podkreplenie"
        assert manifest["sos"].tts_alternatives == [
            "shchit probit, vyzyvayu podmogu",
            "kontur rushitsya, derzhite stroy",
        ]


def test_build_tts_command_for_text_phrase(tmp_path: Path) -> None:
    module = _load_voice_prep_module()
    output_path = tmp_path / "startup.wav"

    command = module.build_tts_command("я вернулся", output_path, "command_slow")

    assert command[0].endswith("espeak-ng")
    assert "-v" in command
    assert command[command.index("-v") + 1] == "ru"
    assert "-w" in command
    assert str(output_path) in command
    assert command[-1] == "я вернулся"


def test_repository_phrase_manifest_uses_russian_text() -> None:
    module = _load_voice_prep_module()
    manifest_path = Path(__file__).resolve().parents[1] / "voice-src" / "phrases.yml"

    manifest = module.load_manifest(manifest_path)

    assert manifest["startup"].text == "я вернулся"
    assert manifest["arm"].text == "режим боя"
    assert manifest["disarm"].text == "жду приказа"
    assert manifest["connected"].text == "принимаю сигнал"
    assert manifest["disconnected"].text == "связь потеряна"
    assert manifest["failsafe"].text == "аварийный режим"
    assert manifest["low_voltage"].text == "низкий заряд"
    assert manifest["sos"].text == "зову подмогу"
    assert manifest["sos"].alternatives == []
    assert manifest["sos"].tts_text is None
    assert manifest["sos"].tts_alternatives == []
