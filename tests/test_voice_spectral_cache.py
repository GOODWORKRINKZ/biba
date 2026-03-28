from __future__ import annotations

import importlib.util
import math
import sys
import wave
from pathlib import Path

import pytest

from buzzer.wav_player import load_peak_frame_cache


def _load_build_cache_module():
    module_path = Path(__file__).resolve().parents[1] / "biba-controller" / "voice" / "build_spectral_cache.py"
    assert module_path.exists(), f"missing script: {module_path}"
    spec = importlib.util.spec_from_file_location("build_spectral_cache", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_wav(path: Path, *, frequency_hz: int) -> None:
    sample_rate = 8000
    samples = [
        int(16000 * math.sin(2 * math.pi * frequency_hz * index / sample_rate))
        for index in range(320)
    ]
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))


def test_build_spectral_cache_writes_one_cache_file_per_wav(tmp_path: Path) -> None:
    module = _load_build_cache_module()
    voice_dir = tmp_path / "voice"
    out_dir = tmp_path / "voice-cache"
    voice_dir.mkdir()
    _write_wav(voice_dir / "startup.wav", frequency_hz=320)
    _write_wav(voice_dir / "arm.wav", frequency_hz=480)
    (voice_dir / "ignore.txt").write_text("skip", encoding="utf-8")

    cache_paths = module.build_spectral_cache(voice_dir=voice_dir, out_dir=out_dir)

    assert [path.name for path in cache_paths] == ["arm.peaks.json", "startup.peaks.json"]
    assert load_peak_frame_cache(out_dir / "startup.peaks.json", voice_dir / "startup.wav")
    assert load_peak_frame_cache(out_dir / "arm.peaks.json", voice_dir / "arm.wav")


def test_main_builds_spectral_cache_from_cli_arguments(tmp_path: Path) -> None:
    module = _load_build_cache_module()
    voice_dir = tmp_path / "voice"
    out_dir = tmp_path / "voice-cache"
    voice_dir.mkdir()
    _write_wav(voice_dir / "connected.wav", frequency_hz=400)

    exit_code = module.main([
        "--voice-dir",
        str(voice_dir),
        "--out-dir",
        str(out_dir),
    ])

    assert exit_code == 0
    assert (out_dir / "connected.peaks.json").exists()


def test_build_spectral_cache_rejects_empty_voice_directory(tmp_path: Path) -> None:
    module = _load_build_cache_module()
    voice_dir = tmp_path / "voice"
    out_dir = tmp_path / "voice-cache"
    voice_dir.mkdir()

    with pytest.raises(ValueError, match="no WAV files"):
        module.build_spectral_cache(voice_dir=voice_dir, out_dir=out_dir)