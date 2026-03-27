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
