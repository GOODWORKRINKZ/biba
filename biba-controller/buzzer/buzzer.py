"""BiBa buzzer with signature R2-D2 style melodies."""

from __future__ import annotations

import threading
import time

import pigpio

from buzzer import melodies
from buzzer.blheli_parser import parse_blheli


class Buzzer:
    """Control a piezo buzzer using pigpio PWM output."""

    def __init__(self, pi: pigpio.pi, pin: int) -> None:
        self.pi = pi
        self.pin = pin
        self.pi.set_mode(self.pin, pigpio.OUTPUT)
        self.off()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Low-level
    # ------------------------------------------------------------------

    def _tone(self, freq: int, duration_ms: int) -> None:
        """Play a blocking tone (internal, must hold lock)."""
        if freq > 0:
            self.pi.set_PWM_frequency(self.pin, freq)
            self.pi.set_PWM_dutycycle(self.pin, 128)
        else:
            self.pi.set_PWM_dutycycle(self.pin, 0)
        time.sleep(duration_ms / 1000.0)
        self.pi.set_PWM_dutycycle(self.pin, 0)

    def off(self) -> None:
        """Disable PWM output on the buzzer pin."""
        self.pi.set_PWM_dutycycle(self.pin, 0)

    # ------------------------------------------------------------------
    # Melody player
    # ------------------------------------------------------------------

    def play(self, sequence: list[tuple[int, int, int]]) -> None:
        """Play a melody sequence (blocking). Thread-safe."""
        with self._lock:
            for freq, duration_ms, pause_ms in sequence:
                self._tone(freq, duration_ms)
                if pause_ms > 0:
                    time.sleep(pause_ms / 1000.0)

    def play_async(self, sequence: list[tuple[int, int, int]]) -> None:
        """Play a melody in a background thread (non-blocking)."""
        t = threading.Thread(target=self.play, args=(sequence,), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # BLHeli melody player
    # ------------------------------------------------------------------

    def play_blheli(self, melody_str: str, tempo_bpm: int = 120) -> None:
        """Play a BLHeli32 format melody string (blocking). Thread-safe."""
        notes = parse_blheli(melody_str, tempo_bpm=tempo_bpm)
        with self._lock:
            for freq, duration_s in notes:
                self._tone(int(freq), int(duration_s * 1000))

    def play_named(self, name: str) -> None:
        """Play a melody from BLHELI_CATALOG by name (blocking)."""
        entry = melodies.BLHELI_CATALOG.get(name)
        if entry is None:
            return
        melody_str, tempo = entry
        self.play_blheli(melody_str, tempo_bpm=tempo)

    def play_named_async(self, name: str) -> None:
        """Play a named melody in a background thread."""
        t = threading.Thread(target=self.play_named, args=(name,), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Named convenience methods
    # ------------------------------------------------------------------

    def startup_tone(self) -> None:
        self.play(melodies.STARTUP)

    def shutdown_tone(self) -> None:
        self.play(melodies.SHUTDOWN)

    def arm_tone(self) -> None:
        self.play(melodies.ARM)

    def disarm_tone(self) -> None:
        self.play(melodies.DISARM)

    def low_voltage_alarm(self) -> None:
        self.play(melodies.LOW_VOLTAGE)

    def failsafe_tone(self) -> None:
        self.play(melodies.FAILSAFE)

    def sos_beacon(self) -> None:
        self.play(melodies.SOS)

    def connected_tone(self) -> None:
        self.play_async(melodies.CONNECTED)

    def disconnected_tone(self) -> None:
        self.play_async(melodies.DISCONNECTED)
