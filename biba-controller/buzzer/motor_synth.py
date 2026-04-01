"""Software PWM motor synth built around two motors with LPWM and RPWM inputs."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pigpio

from buzzer import melodies
from buzzer.blheli_parser import parse_blheli

_SOFTWARE_PWM_RANGE = 255
_DEFAULT_DUTY_CYCLE = 250_000
_DEFAULT_DELTA_PERCENT = 20


@dataclass(frozen=True)
class _PinState:
	frequency: int
	pwm_range: int


class MotorSynth:
	"""Software PWM synth for two BTS7960-driven motors."""

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
		self.comp_pins = list(dict.fromkeys(comp_pins or []))
		self.left_pwm_pins = list(dict.fromkeys(left_pwm_pins or []))
		self.left_comp_pins = list(dict.fromkeys(left_comp_pins or []))
		self.right_pwm_pins = list(dict.fromkeys(right_pwm_pins or []))
		self.right_comp_pins = list(dict.fromkeys(right_comp_pins or []))
		self._raw_left_comp_pins = list(self.left_comp_pins)
		self._raw_right_comp_pins = list(self.right_comp_pins)
		self.duty_cycle = duty_cycle
		self._delta_percent = _DEFAULT_DELTA_PERCENT
		self._lock = threading.Lock()
		self._interrupt_event = threading.Event()
		self._control_active = False
		self._pin_states: dict[int, _PinState] = {}

		for pin in self._all_audio_pins():
			self.pi.set_mode(pin, pigpio.OUTPUT)
			self._pin_states[pin] = _PinState(
				frequency=self.pi.get_PWM_frequency(pin),
				pwm_range=self.pi.get_PWM_range(pin),
			)

		self.off()

	@staticmethod
	def _normalize_pwm_mode(pwm_mode: str | None) -> str:
		normalized = (pwm_mode or "SOFTWARE").strip().upper()
		if normalized in {"SOFTWARE", "HARDWARE"}:
			return normalized
		return "SOFTWARE"

	@staticmethod
	def _scale_software_duty(duty_cycle: int) -> int:
		return max(0, min(_SOFTWARE_PWM_RANGE, round(duty_cycle * _SOFTWARE_PWM_RANGE / 1_000_000)))

	@staticmethod
	def _frequency_pair_for_note(frequency_hz: int, delta_percent: int = _DEFAULT_DELTA_PERCENT) -> tuple[int, int]:
		if frequency_hz <= 0:
			return 0, 0
		delta_hz = round(frequency_hz * delta_percent / 100)
		lower_half = delta_hz // 2
		upper_half = delta_hz - lower_half
		return max(1, frequency_hz - lower_half), frequency_hz + upper_half

	def _all_audio_pins(self) -> list[int]:
		return list(
			dict.fromkeys(
				self.pwm_pins
				+ self.comp_pins
				+ self.left_pwm_pins
				+ self.left_comp_pins
				+ self.right_pwm_pins
				+ self.right_comp_pins
			)
		)

	def _apply_pin(self, pin: int, frequency_hz: int, duty_cycle: int) -> None:
		self.pi.set_PWM_range(pin, _SOFTWARE_PWM_RANGE)
		self.pi.set_PWM_frequency(pin, frequency_hz)
		self.pi.set_PWM_dutycycle(pin, self._scale_software_duty(duty_cycle))

	def _stop_pin(self, pin: int) -> None:
		self.pi.set_PWM_dutycycle(pin, 0)
		state = self._pin_states.get(pin)
		if state is None:
			return
		self.pi.set_PWM_frequency(pin, state.frequency)
		self.pi.set_PWM_range(pin, state.pwm_range)
		self.pi.set_PWM_dutycycle(pin, 0)

	def _apply_group(self, pins: list[int], frequency_hz: int, duty_cycle: int) -> None:
		if frequency_hz <= 0 or duty_cycle <= 0:
			for pin in pins:
				self._stop_pin(pin)
			return
		for pin in pins:
			self._apply_pin(pin, frequency_hz, duty_cycle)

	def _apply_motor_pwm(
		self,
		lpwm_pin: int,
		rpwm_pin: int,
		lpwm_frequency_hz: int,
		lpwm_duty: int,
		rpwm_frequency_hz: int,
		rpwm_duty: int,
	) -> None:
		self._apply_pin(lpwm_pin, lpwm_frequency_hz, lpwm_duty)
		self._apply_pin(rpwm_pin, rpwm_frequency_hz, rpwm_duty)

	def _apply_dual_motor_pwm(
		self,
		left_lpwm_frequency_hz: int,
		left_lpwm_duty: int,
		left_rpwm_frequency_hz: int,
		left_rpwm_duty: int,
		right_lpwm_frequency_hz: int,
		right_lpwm_duty: int,
		right_rpwm_frequency_hz: int,
		right_rpwm_duty: int,
	) -> None:
		if self.left_pwm_pins and self.left_comp_pins:
			self._apply_motor_pwm(
				self.left_pwm_pins[0],
				self.left_comp_pins[0],
				left_lpwm_frequency_hz,
				left_lpwm_duty,
				left_rpwm_frequency_hz,
				left_rpwm_duty,
			)
		if self.right_pwm_pins and self.right_comp_pins:
			self._apply_motor_pwm(
				self.right_pwm_pins[0],
				self.right_comp_pins[0],
				right_lpwm_frequency_hz,
				right_lpwm_duty,
				right_rpwm_frequency_hz,
				right_rpwm_duty,
			)

	def _apply_note_to_motor(self, pwm_pins: list[int], comp_pins: list[int], frequency_hz: int, duty_cycle: int) -> None:
		if not pwm_pins or not comp_pins:
			return
		lpwm_frequency_hz, rpwm_frequency_hz = self._frequency_pair_for_note(frequency_hz, self._delta_percent)
		self._apply_motor_pwm(
			pwm_pins[0],
			comp_pins[0],
			lpwm_frequency_hz,
			duty_cycle,
			rpwm_frequency_hz,
			duty_cycle,
		)

	def _wait_or_interrupted(self, duration_s: float) -> bool:
		return self._interrupt_event.wait(duration_s)

	def set_control_active(self, active: bool) -> None:
		if active == self._control_active:
			return
		self._control_active = active
		if active:
			self._interrupt_event.set()
			self.off()
		else:
			self._interrupt_event.clear()

	def off(self) -> None:
		for pin in self._all_audio_pins():
			self._stop_pin(pin)

	def play(self, sequence: list[tuple[int, int, int]]) -> None:
		if self._control_active:
			return
		with self._lock:
			for frequency_hz, duration_ms, pause_ms in sequence:
				if self._control_active:
					break
				if frequency_hz > 0:
					self._apply_note_to_motor(self.left_pwm_pins, self.left_comp_pins, frequency_hz, self.duty_cycle)
					self._apply_note_to_motor(self.right_pwm_pins, self.right_comp_pins, frequency_hz, self.duty_cycle)
				else:
					self.off()
				interrupted = self._wait_or_interrupted(duration_ms / 1000.0)
				self.off()
				if interrupted or self._control_active:
					break
				if pause_ms > 0 and self._wait_or_interrupted(pause_ms / 1000.0):
					break
			self.off()

	def play_async(self, sequence: list[tuple[int, int, int]]) -> None:
		threading.Thread(target=self.play, args=(sequence,), daemon=True).start()

	def play_blheli(self, melody_str: str, tempo_bpm: int = 120) -> None:
		notes = parse_blheli(melody_str, tempo_bpm=tempo_bpm)
		self.play([(int(freq), int(duration_s * 1000), 0) for freq, duration_s in notes])

	def play_split_blheli(self, left_melody_str: str, right_melody_str: str, tempo_bpm: int = 120) -> None:
		left_notes = parse_blheli(left_melody_str, tempo_bpm=tempo_bpm)
		right_notes = parse_blheli(right_melody_str, tempo_bpm=tempo_bpm)
		if self._control_active:
			return
		with self._lock:
			for left_note, right_note in zip(left_notes, right_notes):
				if self._control_active:
					break
				left_frequency_hz, left_duration_s = left_note
				right_frequency_hz, right_duration_s = right_note
				self._apply_note_to_motor(self.left_pwm_pins, self.left_comp_pins, int(left_frequency_hz), self.duty_cycle)
				self._apply_note_to_motor(self.right_pwm_pins, self.right_comp_pins, int(right_frequency_hz), self.duty_cycle)
				interrupted = self._wait_or_interrupted(max(left_duration_s, right_duration_s))
				self.off()
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
			self._apply_group(self.pwm_pins, left_frequency_hz, left_duty_cycle)
			self._apply_group(self.comp_pins, right_frequency_hz, right_duty_cycle)
			try:
				self._wait_or_interrupted(duration_ms / 1000.0)
			finally:
				self.off()

	def play_named(self, name: str) -> None:
		catalog = getattr(melodies, "CATALOG", {})
		entry = catalog.get(name)
		if entry is not None:
			if isinstance(entry, tuple) and len(entry) == 3:
				left_melody_str, right_melody_str, tempo = entry
				self.play_split_blheli(left_melody_str, right_melody_str, tempo_bpm=tempo)
				return
			if isinstance(entry, tuple) and len(entry) == 2:
				melody_str, tempo = entry
				self.play_blheli(melody_str, tempo_bpm=tempo)
				return
		return

	def play_named_async(self, name: str) -> None:
		threading.Thread(target=self.play_named, args=(name,), daemon=True).start()

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

	def play_wav(self, path: str) -> None:
		del path

	def play_wav_async(self, path: str):
		thread = threading.Thread(target=self.play_wav, args=(path,), daemon=True)
		thread.start()
		return thread

	def play_spectral(self, path: str) -> None:
		del path

	def play_spectral_async(self, path: str):
		thread = threading.Thread(target=self.play_spectral, args=(path,), daemon=True)
		thread.start()
		return thread
