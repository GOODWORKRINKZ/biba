from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_voice_prep_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "voice_prep.py"
    assert module_path.exists(), f"missing script: {module_path}"
    spec = importlib.util.spec_from_file_location("voice_prep_promote", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_promote_approved_voices_copies_default_candidate_to_production_path(tmp_path: Path) -> None:
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
    text: зову подмогу
    profiles:
      - robot_harsh
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "voice-work"
    startup_candidate = output_dir / "startup" / "startup__command_slow__v01.wav"
    sos_candidate = output_dir / "sos" / "sos__robot_harsh__v01.wav"
    startup_candidate.parent.mkdir(parents=True, exist_ok=True)
    sos_candidate.parent.mkdir(parents=True, exist_ok=True)
    startup_candidate.write_bytes(b"startup-audio")
    sos_candidate.write_bytes(b"sos-audio")

    repo_root = tmp_path / "repo"

    promoted = module.promote_approved_voices(manifest_path, output_dir, repo_root)

    assert promoted == [
        repo_root / "biba-controller" / "voice" / "startup_returned.wav",
        repo_root / "biba-controller" / "voice" / "sos_comply.wav",
    ]
    assert promoted[0].read_bytes() == b"startup-audio"
    assert promoted[1].read_bytes() == b"sos-audio"


def test_main_promote_approved_supports_selected_event(tmp_path: Path) -> None:
    module = _load_voice_prep_module()
    manifest_path = tmp_path / "phrases.yml"
    manifest_path.write_text(
        """
events:
  startup:
    text: я вернулся
    profiles:
      - command_slow
  arm:
    text: режим боя
    profiles:
      - command_slow
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "voice-work"
    startup_candidate = output_dir / "startup" / "startup__command_slow__v01.wav"
    arm_candidate = output_dir / "arm" / "arm__command_slow__v01.wav"
    startup_candidate.parent.mkdir(parents=True, exist_ok=True)
    arm_candidate.parent.mkdir(parents=True, exist_ok=True)
    startup_candidate.write_bytes(b"startup-audio")
    arm_candidate.write_bytes(b"arm-audio")
    repo_root = tmp_path / "repo"

    exit_code = module.main(
        [
            "promote-approved",
            "--manifest",
            str(manifest_path),
            "--base-dir",
            str(output_dir),
            "--repo-root",
            str(repo_root),
            "--event",
            "startup",
        ]
    )

    assert exit_code == 0
    assert (repo_root / "biba-controller" / "voice" / "startup_returned.wav").read_bytes() == b"startup-audio"
    assert not (repo_root / "biba-controller" / "voice" / "arm_begin.wav").exists()
