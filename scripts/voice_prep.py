from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

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
_PRODUCTION_VOICE_FILENAMES: dict[str, str] = {
    "startup": "startup_returned.wav",
    "arm": "arm_begin.wav",
    "disarm": "disarm_waiting.wav",
    "connected": "connected_online.wav",
    "disconnected": "disconnected_protocol.wav",
    "failsafe": "failsafe_intruder.wav",
    "low_voltage": "low_voltage_retribution.wav",
    "sos": "sos_comply.wav",
}


@dataclass(frozen=True)
class PhraseEntry:
    text: str
    profiles: list[str]
    tts_text: str | None = None
    alternatives: list[str] = field(default_factory=list)
    tts_alternatives: list[str] = field(default_factory=list)
    seed_wav: str | None = None


@dataclass(frozen=True)
class AuditionCandidate:
    path: Path
    text: str
    tts_text: str
    profile: str
    label: str


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
        raw_alternatives = raw_entry.get("alternatives") or []
        if not isinstance(raw_alternatives, list) or not all(
            isinstance(item, str) and item.strip() for item in raw_alternatives
        ):
            raise ValueError(f"event '{event}' alternatives must be a list of non-empty strings")
        raw_tts_text = raw_entry.get("tts_text")
        if raw_tts_text is not None and (not isinstance(raw_tts_text, str) or not raw_tts_text.strip()):
            raise ValueError(f"event '{event}' tts_text must be a non-empty string when provided")
        raw_tts_alternatives = raw_entry.get("tts_alternatives") or []
        if not isinstance(raw_tts_alternatives, list) or not all(
            isinstance(item, str) and item.strip() for item in raw_tts_alternatives
        ):
            raise ValueError(f"event '{event}' tts_alternatives must be a list of non-empty strings")
        if raw_tts_alternatives and len(raw_tts_alternatives) != len(raw_alternatives):
            raise ValueError(f"event '{event}' tts_alternatives must match alternatives length")
        seed_wav = raw_entry.get("seed_wav")
        if seed_wav is not None and not isinstance(seed_wav, str):
            raise ValueError(f"event '{event}' seed_wav must be a string when provided")
        manifest[event] = PhraseEntry(
            text=text.strip(),
            profiles=raw_profiles,
            tts_text=raw_tts_text.strip() if isinstance(raw_tts_text, str) else None,
            alternatives=[item.strip() for item in raw_alternatives],
            tts_alternatives=[item.strip() for item in raw_tts_alternatives],
            seed_wav=seed_wav,
        )
    return manifest


def build_tts_command(text: str, output_path: str | Path, profile: str) -> list[str]:
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("text must be non-empty")
    voice = _select_tts_voice(normalized_text)
    command = [
        "espeak-ng",
        "-v",
        voice,
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


def build_audition_candidates(base_dir: str | Path, *, event: str, entry: PhraseEntry) -> list[AuditionCandidate]:
    candidates: list[AuditionCandidate] = []
    texts = [entry.text, *entry.alternatives]
    tts_texts = [entry.tts_text or entry.text, *(entry.tts_alternatives or entry.alternatives)]
    for profile in entry.profiles:
        for variant, (text, tts_text) in enumerate(zip(texts, tts_texts), start=1):
            path = build_candidate_path(base_dir, event, profile, variant)
            candidates.append(
                AuditionCandidate(
                    path=path,
                    text=text,
                    tts_text=tts_text,
                    profile=profile,
                    label=f"v{variant:02d}",
                )
            )
    return candidates


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
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return manifest_path


def write_event_audition_manifest(base_dir: str | Path, *, event: str, entry: PhraseEntry) -> Path:
    candidates = build_audition_candidates(base_dir, event=event, entry=entry)
    manifest_path = write_audition_manifest(
        base_dir,
        event=event,
        candidates=[candidate.path for candidate in candidates],
        profile=entry.profiles[0],
    )
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    payload["texts"] = [candidate.text for candidate in candidates]
    payload["tts_texts"] = [candidate.tts_text for candidate in candidates]
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return manifest_path


def generate_audition_manifests(
    manifest_path: str | Path,
    base_dir: str | Path,
    *,
    events: Sequence[str] | None = None,
) -> list[Path]:
    manifest = load_manifest(manifest_path)
    selected_events = list(events) if events else list(manifest.keys())
    output_paths: list[Path] = []
    for event in selected_events:
        entry = manifest.get(event)
        if entry is None:
            raise ValueError(f"unknown event: {event}")
        output_paths.append(write_event_audition_manifest(base_dir, event=event, entry=entry))
    return output_paths


def build_production_voice_path(repo_root: str | Path, event: str) -> Path:
    filename = _PRODUCTION_VOICE_FILENAMES.get(event)
    if filename is None:
        raise ValueError(f"unsupported production voice event: {event}")
    return Path(repo_root) / "biba-controller" / "voice" / filename


def promote_approved_voices(
    manifest_path: str | Path,
    base_dir: str | Path,
    repo_root: str | Path,
    *,
    events: Sequence[str] | None = None,
) -> list[Path]:
    manifest = load_manifest(manifest_path)
    selected_events = list(events) if events else list(manifest.keys())
    output_paths: list[Path] = []
    for event in selected_events:
        entry = manifest.get(event)
        if entry is None:
            raise ValueError(f"unknown event: {event}")
        source_path = build_candidate_path(base_dir, event, entry.profiles[0], 1)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        target_path = build_production_voice_path(repo_root, event)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        output_paths.append(target_path)
    return output_paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice_prep")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_audition = subparsers.add_parser("prepare-audition")
    prepare_audition.add_argument("--manifest", required=True)
    prepare_audition.add_argument("--base-dir", required=True)
    prepare_audition.add_argument("--event", action="append", dest="events")

    promote_approved = subparsers.add_parser("promote-approved")
    promote_approved.add_argument("--manifest", required=True)
    promote_approved.add_argument("--base-dir", required=True)
    promote_approved.add_argument("--repo-root", required=True)
    promote_approved.add_argument("--event", action="append", dest="events")

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "prepare-audition":
        generate_audition_manifests(args.manifest, args.base_dir, events=args.events)
        return 0
    if args.command == "promote-approved":
        promote_approved_voices(
            args.manifest,
            args.base_dir,
            args.repo_root,
            events=args.events,
        )
        return 0
    raise ValueError(f"unsupported command: {args.command}")


def _profile_args(profile: str) -> list[str]:
    args = _PROFILE_ARGS.get(profile)
    if args is None:
        raise ValueError(f"unsupported profile: {profile}")
    return args.copy()


def _candidate_label(path: Path) -> str:
    parts = path.stem.split("__")
    return parts[-1] if parts else path.stem


def _select_tts_voice(text: str) -> str:
    if any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in text):
        return "ru"
    return "en"


if __name__ == "__main__":
    raise SystemExit(main())
