"""Motor-based sound playback using the BTS7960 hardware PWM pins."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import config
import pigpio

from buzzer import melodies
from buzzer.blheli_parser import parse_blheli
from buzzer.wav_player import (
    DEFAULT_CARRIER_HZ,
    load_or_build_peak_frames,
    load_or_build_split_peak_frames,
    load_wav,
    play_bipolar_samples,
    play_bipolar_split_peak_frames,
    play_peak_frames,
    play_split_peak_frames,
    play_samples,
)

LOGGER = logging.getLogger(__name__)
_DEFAULT_DUTY_CYCLE = 50_000
_DEFAULT_SOFTWARE_DUTY_CYCLE = 250_000
_DEFAULT_SOFTWARE_DETUNE_RATIO = 0.20
_DEFAULT_SOFTWARE_DETUNE_MIN_HZ = 60
_SOFTWARE_PWM_RANGE = 255
_HARDWARE_PWM_CHANNELS = {
    12: 0,
    18: 0,
    13: 1,
    19: 1,
}


@dataclass(frozen=True)
class _SoftwarePinState:
    frequency: int
    pwm_range: int


def _hardware_pwm_channel(pin: int) -> int | None:
    return _HARDWARE_PWM_CHANNELS.get(pin)


def _drop_shared_channel_comp_pins(
    pwm_pins: list[int],
    comp_pins: list[int],
    *,
    group_name: str,
) -> list[int]:
    pwm_channels = {
        channel
        for pin in pwm_pins
        if (channel := _hardware_pwm_channel(pin)) is not None
    }
    if not pwm_channels:
        return comp_pins

    filtered: list[int] = []
    dropped: list[int] = []
    for pin in comp_pins:
        channel = _hardware_pwm_channel(pin)
        if channel is not None and channel in pwm_channels:
            dropped.append(pin)
            continue
        filtered.append(pin)

    if dropped:
        LOGGER.warning(
            "Dropping complementary synth pins that share a hardware PWM channel with %s pins: %s",
            group_name,
            dropped,
        )
    return filtered


class MotorSynth:
    """Play melodies through the motor PWM pins using hardware PWM."""

    def __init__(
        self,
        pi: pigpio.pi,
        pwm_pins: list[int],
        duty_cycle: int = _DEFAULT_DUTY_CYCLE,
        comp_pins: list[int] | None = None,
        pwm_mode: str | None = None,
        *,
        left_pwm_pins: list[int] | None = None,
        left_comp_pins: list[int] | None = None,
        right_pwm_pins: list[int] | None = None,
        right_comp_pins: list[int] | None = None,
    ) -> None:
        self.pi = pi
        self._pwm_mode = self._normalize_pwm_mode(pwm_mode)
        self.pwm_pins = list(dict.fromkeys(pwm_pins))
        self.left_pwm_pins = list(dict.fromkeys(left_pwm_pins)) if left_pwm_pins else []
        self.right_pwm_pins = list(dict.fromkeys(right_pwm_pins)) if right_pwm_pins else []
        self._raw_left_comp_pins = list(dict.fromkeys(left_comp_pins)) if left_comp_pins else []
        self.left_comp_pins = list(self._raw_left_comp_pins)
        if self._pwm_mode == "HARDWARE":
            self.left_comp_pins = _drop_shared_channel_comp_pins(
                self.left_pwm_pins,
                self.left_comp_pins,
                group_name="left motor synth",
            )
        self._raw_right_comp_pins = list(dict.fromkeys(right_comp_pins)) if right_comp_pins else []
        self.right_comp_pins = list(self._raw_right_comp_pins)
        if self._pwm_mode == "HARDWARE":
            self.right_comp_pins = _drop_shared_channel_comp_pins(
                self.right_pwm_pins,
                self.right_comp_pins,
                group_name="right motor synth",
            )
        self.comp_pins = list(dict.fromkeys(comp_pins)) if comp_pins else []
        if self._pwm_mode == "HARDWARE":
            self.comp_pins = _drop_shared_channel_comp_pins(
                self.pwm_pins,
                self.comp_pins,
                group_name="combined motor synth",
            )
        if self._has_split_motor_groups():
            self.comp_pins = list(dict.fromkeys(self.left_comp_pins + self.right_comp_pins))
        self.duty_cycle = duty_cycle
        if self._pwm_mode == "SOFTWARE" and duty_cycle == _DEFAULT_DUTY_CYCLE:
            self.duty_cycle = _DEFAULT_SOFTWARE_DUTY_CYCLE
        self._lock = threading.Lock()
        self._interrupt_event = threading.Event()
        self._control_active = False
        self._bipolar_phase_forward = True
        self._software_pin_states: dict[int, _SoftwarePinState] = {}
        for pin in self._all_audio_pins():
            self.pi.set_mode(pin, pigpio.OUTPUT)
            if self._pwm_mode == "SOFTWARE":
                self._software_pin_states[pin] = _SoftwarePinState(
                    frequency=self.pi.get_PWM_frequency(pin),
                    pwm_range=self.pi.get_PWM_range(pin),
                )
        self.off()

    @staticmethod
    def _normalize_pwm_mode(pwm_mode: str | None) -> str:
        normalized = (pwm_mode or config.BTS7960_PWM_MODE).strip().upper()
        if normalized in {"HARDWARE", "SOFTWARE"}:
            return normalized
        return "HARDWARE"

    @staticmethod
    def _scale_software_duty(duty_cycle: int) -> int:
        return max(0, min(_SOFTWARE_PWM_RANGE, int(duty_cycle * _SOFTWARE_PWM_RANGE / 1_000_000)))

    def _all_audio_pins(self) -> list[int]:
        return list(
            dict.fromkeys(
                self.pwm_pins
                + self.comp_pins
                + self._raw_left_comp_pins
                + self._raw_right_comp_pins
            )
        )

    def _has_split_motor_groups(self) -> bool:
        return bool(
            self.left_pwm_pins
            or self.left_comp_pins
            or self.right_pwm_pins
            or self.right_comp_pins
        )

    def _has_shared_channel_direction_groups(self) -> bool:
        return bool(
            (self.left_pwm_pins and self._raw_left_comp_pins and not self.left_comp_pins)
            or (self.right_pwm_pins and self._raw_right_comp_pins and not self.right_comp_pins)
        )

    def set_control_active(self, active: bool) -> None:
        if active == self._control_active:
            return

        self._control_active = active
        if active:
            self._interrupt_event.set()
            self.off()
        else:
            self._interrupt_event.clear()

    def _apply(self, frequency: int, duty_cycle: int) -> None:
        if self._pwm_mode == "SOFTWARE" and self.comp_pins:
            forward_frequency, reverse_frequency = self._detune_frequency_pair(frequency)
            self._apply_group(self.pwm_pins, forward_frequency, duty_cycle)
            self._apply_group(self.comp_pins, reverse_frequency, duty_cycle)
            return
        for pin in self.pwm_pins + self.comp_pins:
            self._apply_pin(pin, frequency, duty_cycle)

    def _apply_group(self, pins: list[int], frequency: int, duty_cycle: int) -> None:
        for pin in pins:
            self._apply_pin(pin, frequency, duty_cycle)

    def _apply_pin(self, pin: int, frequency: int, duty_cycle: int) -> None:
        if self._pwm_mode == "SOFTWARE":
            if frequency <= 0 or duty_cycle <= 0:
                self._restore_software_pin(pin)
                return
            self.pi.set_PWM_range(pin, _SOFTWARE_PWM_RANGE)
            self.pi.set_PWM_frequency(pin, frequency)
            self.pi.set_PWM_dutycycle(pin, self._scale_software_duty(duty_cycle))
            return
        self.pi.hardware_PWM(pin, frequency, duty_cycle)

    def _restore_software_pin(self, pin: int) -> None:
        self.pi.set_PWM_dutycycle(pin, 0)
        state = self._software_pin_states.get(pin)
        if state is None:
            return
        self.pi.set_PWM_frequency(pin, state.frequency)
        self.pi.set_PWM_range(pin, state.pwm_range)
        self.pi.set_PWM_dutycycle(pin, 0)

    def _stop_group(self, pins: list[int]) -> None:
        for pin in pins:
            if self._pwm_mode == "SOFTWARE":
                self._restore_software_pin(pin)
            else:
                self.pi.hardware_PWM(pin, 0, 0)

    @staticmethod
    def _detune_frequency_pair(frequency: int) -> tuple[int, int]:
        if frequency <= 0:
            return 0, 0
        delta_hz = max(
            _DEFAULT_SOFTWARE_DETUNE_MIN_HZ,
            round(frequency * _DEFAULT_SOFTWARE_DETUNE_RATIO),
        )
        lower_half = delta_hz // 2
        upper_half = delta_hz - lower_half
        return max(1, frequency - lower_half), frequency + upper_half

    def _apply_split(
        self,
        left_frequency: int,
        left_duty_cycle: int,
        right_frequency: int,
        right_duty_cycle: int,
    ) -> None:
        if self._pwm_mode == "SOFTWARE" and (self.left_comp_pins or self.right_comp_pins):
            left_forward_frequency, left_reverse_frequency = self._detune_frequency_pair(left_frequency)
            right_forward_frequency, right_reverse_frequency = self._detune_frequency_pair(right_frequency)
            self._apply_group(self.left_pwm_pins, left_forward_frequency, left_duty_cycle)
            self._apply_group(self.left_comp_pins, left_reverse_frequency, left_duty_cycle)
            self._apply_group(self.right_pwm_pins, right_forward_frequency, right_duty_cycle)
            self._apply_group(self.right_comp_pins, right_reverse_frequency, right_duty_cycle)
            return

        left_pins = self.left_pwm_pins + self.left_comp_pins
        right_pins = self.right_pwm_pins + self.right_comp_pins
        self._apply_group(left_pins, left_frequency, left_duty_cycle)
        self._apply_group(right_pins, right_frequency, right_duty_cycle)

    def _apply_manual_split(
        self,
        left_frequency: int,
        left_duty_cycle: int,
        right_frequency: int,
        right_duty_cycle: int,
    ) -> None:
        # Manual motor-test PWM should use the active direction pin for each motor
        # and hold the opposite BTS7960 input at zero, matching the drive path.
        left_active_pins = list(dict.fromkeys(self.left_pwm_pins))
        right_active_pins = list(dict.fromkeys(self.right_pwm_pins))
        left_inactive_pins = list(dict.fromkeys(self._raw_left_comp_pins))
        right_inactive_pins = list(dict.fromkeys(self._raw_right_comp_pins))
        if not left_active_pins and not right_active_pins:
            self._apply_split(left_frequency, left_duty_cycle, right_frequency, right_duty_cycle)
            return

        self._stop_group(left_inactive_pins)
        self._stop_group(right_inactive_pins)
        self._apply_group(left_active_pins, left_frequency, left_duty_cycle)
        self._apply_group(right_active_pins, right_frequency, right_duty_cycle)

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

    def _split_tone(self, left_freq: int, right_freq: int, duration_ms: int) -> bool:
        left_duty = self.duty_cycle if left_freq > 0 else 0
        right_duty = self.duty_cycle if right_freq > 0 else 0
        self._apply_split(left_freq, left_duty, right_freq, right_duty)
        interrupted = self._wait_or_interrupted(duration_ms / 1000.0)
        self.off()
        return interrupted

    def off(self) -> None:
        self._stop_group(self._all_audio_pins())

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

    def play_split_blheli(self, left_melody_str: str, right_melody_str: str, tempo_bpm: int = 120) -> None:
        left_notes = parse_blheli(left_melody_str, tempo_bpm=tempo_bpm)
        right_notes = parse_blheli(right_melody_str, tempo_bpm=tempo_bpm)
        if self._control_active:
            return
        with self._lock:
            for left_note, right_note in zip(left_notes, right_notes):
                if self._control_active:
                    break
                left_freq, left_duration_s = left_note
                right_freq, right_duration_s = right_note
                duration_ms = int(max(left_duration_s, right_duration_s) * 1000)
                interrupted = self._split_tone(int(left_freq), int(right_freq), duration_ms)
                if interrupted or self._control_active:
                    break
            self.off()

    def play_manual_split_pwm(
        self,
        left_frequency_hz: int,
        left_duty_cycle: int,
        right_frequency_hz: int,
        right_duty_cycle: int,
        duration_ms: int,
    ) -> None:
        if self._control_active:
            return
        with self._lock:
            self.pi.set_PWM_range(self.left_pwm_pins[0], _SOFTWARE_PWM_RANGE)
            self.pi.set_PWM_range(self.left_comp_pins[0], _SOFTWARE_PWM_RANGE)
            self.pi.set_PWM_range(self.right_pwm_pins[0], _SOFTWARE_PWM_RANGE)
            self.pi.set_PWM_range(self.right_comp_pins[0], _SOFTWARE_PWM_RANGE)
            self.pi.set_PWM_frequency(self.left_pwm_pins[0], left_frequency_hz)
            self.pi.set_PWM_frequency(self.right_pwm_pins[0], left_frequency_hz)
            self.pi.set_PWM_frequency(self.left_comp_pins[0], right_frequency_hz)
            self.pi.set_PWM_frequency(self.right_comp_pins[0], right_frequency_hz)
            self.pi.set_PWM_dutycycle(self.left_pwm_pins[0], self._scale_software_duty(left_duty_cycle))
            self.pi.set_PWM_dutycycle(self.right_pwm_pins[0], self._scale_software_duty(left_duty_cycle))
            self.pi.set_PWM_dutycycle(self.left_comp_pins[0], self._scale_software_duty(right_duty_cycle))
            self.pi.set_PWM_dutycycle(self.right_comp_pins[0], self._scale_software_duty(right_duty_cycle))

            #self._apply_manual_split(left_frequency_hz, left_duty_cycle, right_frequency_hz, right_duty_cycle)
            try:
                self._wait_or_interrupted(duration_ms / 1000.0)
            finally:
                self.off()

    def play_named(self, name: str) -> None:
        split_entry = melodies.SPLIT_BLHELI_CATALOG.get(name)
        if split_entry is not None and self._has_split_motor_groups():
            left_melody_str, right_melody_str, tempo = split_entry
            self.play_split_blheli(left_melody_str, right_melody_str, tempo_bpm=tempo)
            return
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

    # ------------------------------------------------------------------
    # WAV playback (PCM-over-PWM)
    # ------------------------------------------------------------------

    def play_wav(self, path: str) -> None:
        """Play a WAV file through motor coils (blocking)."""
        if self._control_active:
            return
        try:
            samples, sample_rate = load_wav(path)
        except Exception:
            LOGGER.warning("Failed to load WAV: %s", path, exc_info=True)
            return
        with self._lock:
            if self._control_active:
                return
            if self._has_shared_channel_direction_groups():
                play_bipolar_samples(
                    self.pi,
                    self.left_pwm_pins + self.right_pwm_pins,
                    self._raw_left_comp_pins + self._raw_right_comp_pins,
                    samples,
                    sample_rate,
                    carrier_freq=DEFAULT_CARRIER_HZ,
                    interrupt_event=self._interrupt_event,
                )
            else:
                play_samples(
                    self.pi,
                    self.pwm_pins,
                    samples,
                    sample_rate,
                    carrier_freq=DEFAULT_CARRIER_HZ,
                    interrupt_event=self._interrupt_event,
                    comp_pins=self.comp_pins,
                )

    def play_wav_async(self, path: str) -> threading.Thread:
        """Play a WAV file in a background thread. Returns the thread."""
        t = threading.Thread(target=self.play_wav, args=(path,), daemon=True)
        t.start()
        return t

    # ------------------------------------------------------------------
    # Spectral / vocoder playback
    # ------------------------------------------------------------------

    def play_spectral(self, path: str) -> None:
        """Play a WAV as an FFT-derived tone sequence (blocking)."""
        if self._control_active:
            return
        try:
            if self._has_split_motor_groups():
                left_frames, right_frames = load_or_build_split_peak_frames(path)
            else:
                frames = load_or_build_peak_frames(path)
        except Exception:
            LOGGER.warning("Failed to load WAV for spectral: %s", path, exc_info=True)
            return
        with self._lock:
            if self._control_active:
                return
            if self._has_split_motor_groups():
                if self._has_shared_channel_direction_groups():
                    play_bipolar_split_peak_frames(
                        self.pi,
                        self.left_pwm_pins,
                        self._raw_left_comp_pins,
                        self.right_pwm_pins,
                        self._raw_right_comp_pins,
                        left_frames,
                        right_frames,
                        interrupt_event=self._interrupt_event,
                    )
                else:
                    play_split_peak_frames(
                        self.pi,
                        self.left_pwm_pins + self.left_comp_pins,
                        self.right_pwm_pins + self.right_comp_pins,
                        left_frames,
                        right_frames,
                        interrupt_event=self._interrupt_event,
                    )
            else:
                play_peak_frames(
                    self.pi,
                    self.pwm_pins + self.comp_pins,
                    frames,
                    interrupt_event=self._interrupt_event,
                )

    def play_spectral_async(self, path: str) -> threading.Thread:
        """Play spectral in a background thread. Returns the thread."""
        t = threading.Thread(target=self.play_spectral, args=(path,), daemon=True)
        t.start()
        return t