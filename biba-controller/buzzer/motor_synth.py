"""Motor-based sound playback using the BTS7960 hardware PWM pins."""

from __future__ import annotations

import threading

import pigpio

from buzzer import melodies
from buzzer.blheli_parser import parse_blheli


class MotorSynth:
    """Play melodies through the motor PWM pins using hardware PWM."""

    def __init__(self, pi: pigpio.pi, pwm_pins: list[int], duty_cycle: int = 50000) -> None:
        self.pi = pi
        self.pwm_pins = list(dict.fromkeys(pwm_pins))
        self.duty_cycle = duty_cycle
        self._lock = threading.Lock()
        self._interrupt_event = threading.Event()
        self._control_active = False
        for pin in self.pwm_pins:
            self.pi.set_mode(pin, pigpio.OUTPUT)
        self.off()

    def set_control_active(self, active: bool) -> None:
        self._control_active = active
        if active:
            self._interrupt_event.set()
            self.off()
        else:
            self._interrupt_event.clear()

    def _apply(self, frequency: int, duty_cycle: int) -> None:
        for pin in self.pwm_pins:
            self.pi.hardware_PWM(pin, frequency, duty_cycle)

    def _wait_or_interrupted(self, duration_s: float) -> bool:
        return self._interrupt_event.wait(duration_s)

    def _tone(self, freq: int, duration_ms: int) -> bool:
        if freq > 0:
            self._apply(freq, self.duty_cycle)
        else:
            self.off()
        interrupted = self._wait_or_interrupted(duration_ms / 1000.0)
        self.off()
        return interrupted

    def off(self) -> None:
        self._apply(0, 0)

    def play(self, sequence: list[tuple[int, int, int]]) -> None:
        if self._control_active:
            return
        with self._lock:
            for freq, duration_ms, pause_ms in sequence:
                if self._control_active:
                    break
                interrupted = self._tone(freq, duration_ms)
                if interrupted or self._control_active:
                    break
                if pause_ms > 0 and self._wait_or_interrupted(pause_ms / 1000.0):
                    break
            self.off()

    def play_async(self, sequence: list[tuple[int, int, int]]) -> None:
        t = threading.Thread(target=self.play, args=(sequence,), daemon=True)
        t.start()

    def play_blheli(self, melody_str: str, tempo_bpm: int = 120) -> None:
        notes = parse_blheli(melody_str, tempo_bpm=tempo_bpm)
        if self._control_active:
            return
        with self._lock:
            for freq, duration_s in notes:
                if self._control_active:
                    break
                interrupted = self._tone(int(freq), int(duration_s * 1000))
                if interrupted or self._control_active:
                    break
            self.off()

    def play_named(self, name: str) -> None:
        entry = melodies.BLHELI_CATALOG.get(name)
        if entry is None:
            return
        melody_str, tempo = entry
        self.play_blheli(melody_str, tempo_bpm=tempo)

    def play_named_async(self, name: str) -> None:
        t = threading.Thread(target=self.play_named, args=(name,), daemon=True)
        t.start()

    def startup_tone(self) -> None:
        self.play_named("startup")

    def shutdown_tone(self) -> None:
        self.play_named("shutdown")

    def arm_tone(self) -> None:
        self.play_named("arm")

    def disarm_tone(self) -> None:
        self.play_named("disarm")

    def low_voltage_alarm(self) -> None:
        self.play_named("low_voltage")

    def failsafe_tone(self) -> None:
        self.play_named("failsafe")

    def sos_beacon(self) -> None:
        self.play_named("sos")

    def connected_tone(self) -> None:
        self.play_named_async("connected")

    def disconnected_tone(self) -> None:
        self.play_named_async("disconnected")