"""WAV file loading and PCM-over-PWM audio playback through motor coils.

Technique: Pulse Code Modulation over a high-frequency PWM carrier.
A fixed carrier (25 kHz, inaudible) has its duty cycle modulated by each
audio sample.  Motor coil inductance acts as a natural low-pass filter,
reconstructing the audio waveform.
"""

from __future__ import annotations

import struct
import threading
import time
import wave

import pigpio

DEFAULT_CARRIER_HZ = 4000
_DUTY_MAX = 1_000_000
_INTERRUPT_CHECK_INTERVAL = 256  # check interrupt every N samples


def load_wav(path: str) -> tuple[bytes, int]:
    """Read a WAV file and return (8-bit unsigned mono samples, sample_rate).

    Handles 8-bit and 16-bit WAVs, mono and stereo.
    Normalises the result so peak amplitude spans the full 0-255 range.
    """
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        # 16-bit signed little-endian
        total_samples = len(raw) // 2
        all_samples = struct.unpack(f"<{total_samples}h", raw)

        if n_channels == 2:
            # Mix stereo to mono: average pairs
            mono = []
            for i in range(0, len(all_samples), 2):
                mono.append((all_samples[i] + all_samples[i + 1]) // 2)
            all_samples = mono

        # Convert signed 16-bit (-32768..32767) → unsigned 8-bit (0..255)
        samples_8 = [(s + 32768) >> 8 for s in all_samples]

    elif sampwidth == 1:
        # 8-bit unsigned already
        if n_channels == 2:
            # Mix stereo to mono
            samples_8 = [(raw[i] + raw[i + 1]) // 2 for i in range(0, len(raw), 2)]
        else:
            samples_8 = list(raw)
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    # Normalise to full 0-255 range for maximum volume
    if samples_8:
        lo = min(samples_8)
        hi = max(samples_8)
        span = hi - lo
        if span > 0:
            samples_8 = [(v - lo) * 255 // span for v in samples_8]

    return bytes(samples_8), sample_rate


def play_samples(
    pi: pigpio.pi,
    pins: list[int],
    samples: bytes,
    sample_rate: int,
    carrier_freq: int = DEFAULT_CARRIER_HZ,
    interrupt_event: threading.Event | None = None,
) -> None:
    """Play 8-bit unsigned PCM samples via hardware PWM duty-cycle modulation.

    When hardware_PWM calls are slower than the sample period (common with
    multiple pins over the pigpio socket), samples are skipped to maintain
    real-time playback speed.
    """
    n_samples = len(samples)
    start = time.monotonic()
    i = 0

    while i < n_samples:
        if interrupt_event and i % _INTERRUPT_CHECK_INTERVAL == 0:
            if interrupt_event.is_set():
                break

        duty = samples[i] * _DUTY_MAX // 255
        for pin in pins:
            pi.hardware_PWM(pin, carrier_freq, duty)

        # Advance index to where we should be in real time
        elapsed = time.monotonic() - start
        i = max(i + 1, int(elapsed * sample_rate))

    # Cleanup: silence all pins
    for pin in pins:
        pi.hardware_PWM(pin, 0, 0)
