from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_voice_prep_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "voice_prep.py"
    assert module_path.exists(), f"missing script: {module_path}"
    spec = importlib.util.spec_from_file_location("voice_prep_profiles", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_slow_profile_contains_band_shaping_and_normalization() -> None:
    module = _load_voice_prep_module()

    filters = module.build_filter_chain("command_slow")

    assert "highpass" in filters
    assert "lowpass" in filters
    assert "loudnorm" in filters


def test_candidate_output_path_encodes_event_profile_and_variant(tmp_path: Path) -> None:
    module = _load_voice_prep_module()

    path = module.build_candidate_path(tmp_path, "startup", "command_slow", 1)

    assert path.parent == tmp_path / "startup"
    assert path.name == "startup__command_slow__v01.wav"
