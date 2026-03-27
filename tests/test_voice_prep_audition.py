from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml


def _load_voice_prep_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "voice_prep.py"
    assert module_path.exists(), f"missing script: {module_path}"
    spec = importlib.util.spec_from_file_location("voice_prep_audition", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_audition_manifest_records_candidate_order(tmp_path: Path) -> None:
    module = _load_voice_prep_module()
    candidates = [
        tmp_path / "startup__command_slow__v01.wav",
        tmp_path / "startup__command_slow__v02.wav",
    ]

    manifest_path = module.write_audition_manifest(
        tmp_path,
        event="startup",
        candidates=candidates,
        profile="command_slow",
    )

    assert manifest_path.name == "audition.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["event"] == "startup"
    assert manifest["profile"] == "command_slow"
    assert manifest["candidates"] == [str(path) for path in candidates]
    assert manifest["labels"] == ["v01", "v02"]


def test_build_audition_candidates_expands_alternative_texts(tmp_path: Path) -> None:
    module = _load_voice_prep_module()
    entry = module.PhraseEntry(
        text="щиты пали, запрашиваю подкрепление",
        tts_text="shchity pali, zaprashayu podkreplenie",
        alternatives=["щит пробит, вызываю подмогу", "контур рушится, держите строй"],
        tts_alternatives=["shchit probit, vyzyvayu podmogu", "kontur rushitsya, derzhite stroy"],
        profiles=["robot_harsh"],
    )

    candidates = module.build_audition_candidates(tmp_path, event="sos", entry=entry)

    assert [candidate.path.name for candidate in candidates] == [
        "sos__robot_harsh__v01.wav",
        "sos__robot_harsh__v02.wav",
        "sos__robot_harsh__v03.wav",
    ]
    assert [candidate.text for candidate in candidates] == [
        "щиты пали, запрашиваю подкрепление",
        "щит пробит, вызываю подмогу",
        "контур рушится, держите строй",
    ]
    assert [candidate.tts_text for candidate in candidates] == [
        "shchity pali, zaprashayu podkreplenie",
        "shchit probit, vyzyvayu podmogu",
        "kontur rushitsya, derzhite stroy",
    ]
    assert [candidate.label for candidate in candidates] == ["v01", "v02", "v03"]


def test_write_event_audition_manifest_includes_candidate_texts(tmp_path: Path) -> None:
    module = _load_voice_prep_module()
    entry = module.PhraseEntry(
        text="щиты пали, запрашиваю подкрепление",
        tts_text="shchity pali, zaprashayu podkreplenie",
        alternatives=["щит пробит, вызываю подмогу"],
        tts_alternatives=["shchit probit, vyzyvayu podmogu"],
        profiles=["robot_harsh"],
    )

    manifest_path = module.write_event_audition_manifest(tmp_path, event="sos", entry=entry)

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["event"] == "sos"
    assert manifest["profile"] == "robot_harsh"
    assert manifest["labels"] == ["v01", "v02"]
    assert manifest["texts"] == [
        "щиты пали, запрашиваю подкрепление",
        "щит пробит, вызываю подмогу",
    ]
    assert manifest["tts_texts"] == [
        "shchity pali, zaprashayu podkreplenie",
        "shchit probit, vyzyvayu podmogu",
    ]
    assert manifest["candidates"] == [
        str(tmp_path / "sos" / "sos__robot_harsh__v01.wav"),
        str(tmp_path / "sos" / "sos__robot_harsh__v02.wav"),
    ]
    raw_text = manifest_path.read_text(encoding="utf-8")
    assert "щиты пали, запрашиваю подкрепление" in raw_text


def test_main_generates_audition_manifest_for_selected_event(tmp_path: Path) -> None:
        module = _load_voice_prep_module()
        manifest_path = tmp_path / "phrases.yml"
        manifest_path.write_text(
                """
events:
    startup:
        text: я вернулся
        profiles:
            - command_slow
    sos:
        text: щиты пали, запрашиваю подкрепление
        tts_text: shchity pali, zaprashayu podkreplenie
        alternatives:
            - щит пробит, вызываю подмогу
        tts_alternatives:
            - shchit probit, vyzyvayu podmogu
        profiles:
            - robot_harsh
""".strip()
                + "\n",
                encoding="utf-8",
        )
        output_dir = tmp_path / "voice-work"

        exit_code = module.main(
                [
                        "prepare-audition",
                        "--manifest",
                        str(manifest_path),
                        "--base-dir",
                        str(output_dir),
                        "--event",
                        "sos",
                ]
        )

        assert exit_code == 0
        audition_path = output_dir / "robot-audition" / "sos" / "audition.yml"
        manifest = yaml.safe_load(audition_path.read_text(encoding="utf-8"))
        assert manifest["event"] == "sos"
        assert manifest["texts"] == [
                "щиты пали, запрашиваю подкрепление",
                "щит пробит, вызываю подмогу",
        ]
        assert manifest["tts_texts"] == [
            "shchity pali, zaprashayu podkreplenie",
            "shchit probit, vyzyvayu podmogu",
        ]


def test_repository_connected_audition_manifest_matches_phrase_manifest() -> None:
    module = _load_voice_prep_module()
    repo_root = Path(__file__).resolve().parents[1]
    phrases_path = repo_root / "voice-src" / "phrases.yml"
    audition_path = repo_root / "voice-work" / "robot-audition" / "connected" / "audition.yml"

    phrases = module.load_manifest(phrases_path)
    audition_manifest = yaml.safe_load(audition_path.read_text(encoding="utf-8"))

    assert audition_manifest["event"] == "connected"
    assert audition_manifest["texts"] == [phrases["connected"].text]
    assert audition_manifest["tts_texts"] == [phrases["connected"].tts_text or phrases["connected"].text]
