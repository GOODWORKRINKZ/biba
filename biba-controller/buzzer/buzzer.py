"""Simple buzzer patterns for BiBa state notifications."""

from __future__ import annotations

import time

import pigpio


class Buzzer:
    """Control a buzzer using pigpio PWM output."""

    def __init__(self, pi: pigpio.pi, pin: int) -> None:
        self.pi = pi
        self.pin = pin
        self.pi.set_mode(self.pin, pigpio.OUTPUT)
        self.off()

    def beep(self, freq: int, duration_ms: int) -> None:
        """Play a blocking tone for the requested duration."""
        self.pi.set_PWM_frequency(self.pin, freq)
        self.pi.set_PWM_dutycycle(self.pin, 128)
        time.sleep(duration_ms / 1000.0)
        self.off()

    def arm_tone(self) -> None:
        """Play a short ascending arm confirmation pattern."""
        for freq in (1000, 1500, 2000):
            self.beep(freq, 100)

    def disarm_tone(self) -> None:
        """Play a short descending disarm confirmation pattern."""
        for freq in (2000, 1500, 1000):
            self.beep(freq, 100)

    def low_voltage_alarm(self) -> None:
        """Play a short low-voltage warning pattern."""
        for _ in range(2):
            self.beep(900, 120)
            time.sleep(0.05)

    def off(self) -> None:
        """Disable PWM output on the buzzer pin."""
        self.pi.set_PWM_dutycycle(self.pin, 0)
