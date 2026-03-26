from __future__ import annotations

from buzzer.voice_selector import VoiceSelector


def test_round_robin_cycles_through_group() -> None:
    selector = VoiceSelector(mode="ROUND_ROBIN")
    voices = ["a.wav", "b.wav", "c.wav"]

    assert selector.choose("startup", voices) == "a.wav"
    assert selector.choose("startup", voices) == "b.wav"
    assert selector.choose("startup", voices) == "c.wav"
    assert selector.choose("startup", voices) == "a.wav"


def test_round_robin_state_is_per_event() -> None:
    selector = VoiceSelector(mode="ROUND_ROBIN")
    voices = ["a.wav", "b.wav"]

    assert selector.choose("startup", voices) == "a.wav"
    assert selector.choose("arm", voices) == "a.wav"
    assert selector.choose("startup", voices) == "b.wav"
    assert selector.choose("arm", voices) == "b.wav"


def test_random_mode_chooses_from_group() -> None:
    selector = VoiceSelector(mode="RANDOM")
    voices = ["a.wav", "b.wav"]

    chosen = selector.choose("startup", voices)

    assert chosen in voices


def test_empty_group_returns_none() -> None:
    selector = VoiceSelector(mode="ROUND_ROBIN")

    assert selector.choose("startup", []) is None