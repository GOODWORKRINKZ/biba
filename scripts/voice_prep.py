from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_PROFILE = "command_slow"
_PROFILE_ARGS: dict[str, list[str]] = {
    "command_slow": ["-s", "118", "-p", "44"],
    "robot_harsh": ["-s", "132", "-p", "52"],
    "seed_clean": ["-s", "124", "-p", "48"],
}
_PROFILE_FILTERS: dict[str, list[str]] = {
    "command_slow": ["highpass", "lowpass", "loudnorm"],
    "robot_harsh": ["highpass", "overdrive", "lowpass", "loudnorm"],
    "seed_clean": ["highpass", "lowpass", "loudnorm"],
}


@dataclass(frozen=True)
class PhraseEntry:
    text: str
    profiles: list[str]
    seed_wav: str | None = None


def load_manifest(path: str | Path) -> dict[str, PhraseEntry]:
    manifest_path = Path(path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    events = data.get("events", {})
    if not isinstance(events, dict):
        raise ValueError("manifest 'events' must be a mapping")

    manifest: dict[str, PhraseEntry] = {}
    for event, raw_entry in events.items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"event '{event}' must be a mapping")
        text = raw_entry.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"event '{event}' must define non-empty text")
        raw_profiles = raw_entry.get("profiles") or [_DEFAULT_PROFILE]
        if not isinstance(raw_profiles, list) or not all(isinstance(item, str) for item in raw_profiles):
            raise ValueError(f"event '{event}' profiles must be a list of strings")
        seed_wav = raw_entry.get("seed_wav")
        if seed_wav is not None and not isinstance(seed_wav, str):
            raise ValueError(f"event '{event}' seed_wav must be a string when provided")
        manifest[event] = PhraseEntry(
            text=text.strip(),
            profiles=raw_profiles,
            seed_wav=seed_wav,
        )
    return manifest


def build_tts_command(text: str, output_path: str | Path, profile: str) -> list[str]:
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("text must be non-empty")
    command = [
        "espeak-ng",
        *_profile_args(profile),
        "-w",
        str(Path(output_path)),
        normalized_text,
    ]
    return command


def build_filter_chain(profile: str) -> list[str]:
    filters = _PROFILE_FILTERS.get(profile)
    if filters is None:
        raise ValueError(f"unsupported profile: {profile}")
    return filters.copy()


def build_candidate_path(base_dir: str | Path, event: str, profile: str, variant: int) -> Path:
    if variant < 1:
        raise ValueError("variant must be >= 1")
    event_dir = Path(base_dir) / event
    return event_dir / f"{event}__{profile}__v{variant:02d}.wav"


def write_audition_manifest(
    base_dir: str | Path,
    *,
    event: str,
    candidates: list[Path],
    profile: str,
) -> Path:
    manifest_dir = Path(base_dir) / "robot-audition" / event
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "audition.yml"
    payload = {
        "event": event,
        "profile": profile,
        "candidates": [str(path) for path in candidates],
        "labels": [_candidate_label(path) for path in candidates],
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest_path


def _profile_args(profile: str) -> list[str]:
    args = _PROFILE_ARGS.get(profile)
    if args is None:
        raise ValueError(f"unsupported profile: {profile}")
    return args.copy()


def _candidate_label(path: Path) -> str:
    parts = path.stem.split("__")
    return parts[-1] if parts else path.stem
