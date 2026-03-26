"""Voice file selection policy for grouped event sounds."""

from __future__ import annotations

import random


class VoiceSelector:
    """Choose a voice file from an event-specific group.

    Supported modes:
    - ``ROUND_ROBIN``: cycle deterministically through the list per event.
    - ``RANDOM``: choose any entry randomly.
    """

    def __init__(self, mode: str = "ROUND_ROBIN") -> None:
        self.mode = mode.strip().upper()
        self._indices: dict[str, int] = {}

    def choose(self, event: str, voices: list[str]) -> str | None:
        if not voices:
            return None

        if self.mode == "RANDOM":
            return random.choice(voices)

        index = self._indices.get(event, 0)
        chosen = voices[index % len(voices)]
        self._indices[event] = (index + 1) % len(voices)
        return chosen