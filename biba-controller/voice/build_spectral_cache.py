from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_spectral_cache(voice_dir: str | Path, out_dir: str | Path) -> list[Path]:
    from buzzer.wav_player import split_peak_frames_by_side, wav_to_peak_frames, write_peak_frame_cache

    source_dir = Path(voice_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(source_dir)

    wav_paths = sorted(source_dir.glob("*.wav"))
    if not wav_paths:
        raise ValueError(f"no WAV files found in {source_dir}")

    cache_dir = Path(out_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_paths: list[Path] = []
    for wav_path in wav_paths:
        frames = wav_to_peak_frames(str(wav_path))
        left_frames, right_frames = split_peak_frames_by_side(frames)
        left_cache_path = cache_dir / f"{wav_path.stem}.left.peaks.json"
        right_cache_path = cache_dir / f"{wav_path.stem}.right.peaks.json"
        write_peak_frame_cache(left_cache_path, wav_path, left_frames)
        write_peak_frame_cache(right_cache_path, wav_path, right_frames)
        cache_paths.extend([left_cache_path, right_cache_path])
    return cache_paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_spectral_cache")
    parser.add_argument("--voice-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    build_spectral_cache(args.voice_dir, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())