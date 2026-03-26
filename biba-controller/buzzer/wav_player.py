"""WAV file loading and audio playback through motor coils.

Two playback modes:

1. **PCM-over-PWM** (`play_samples`): A fixed carrier has its duty cycle
   modulated per audio sample.  Limited by pigpio socket latency (~150 µs
   per pin), giving an effective update rate of ~1.6 kHz with 4 pins.

2. **Spectral / vocoder** (`wav_to_tones` + `play_tone_sequence`): STFT
   decomposes the WAV into dominant-frequency frames.  Each frame is played
   as a hardware-PWM tone, so the motor generates the *exact* frequency —
   no sample-rate limitation.  Sounds cleaner at the cost of being a
   simplified spectral representation.
"""

from __future__ import annotations

import cmath
import math
import struct
import threading
import time
import wave

import pigpio

DEFAULT_CARRIER_HZ = 16000
_DUTY_MAX = 1_000_000
_INTERRUPT_CHECK_INTERVAL = 256  # check interrupt every N samples
_SPECTRAL_DUTY_MAX = 500_000  # 50 % duty → max fundamental amplitude


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
    comp_pins: list[int] | None = None,
) -> None:
    """Play 8-bit unsigned PCM samples via hardware PWM duty-cycle modulation.

    When *comp_pins* is provided, those pins receive the complementary duty
    cycle (1 − D), creating a push-pull H-bridge drive that doubles the
    voltage swing across the motor coil.

    When hardware_PWM calls are slower than the sample period (common with
    multiple pins over the pigpio socket), samples are skipped to maintain
    real-time playback speed.
    """
    n_samples = len(samples)
    _comp = comp_pins or []
    start = time.monotonic()
    i = 0

    while i < n_samples:
        if interrupt_event and i % _INTERRUPT_CHECK_INTERVAL == 0:
            if interrupt_event.is_set():
                break

        duty = samples[i] * _DUTY_MAX // 255
        for pin in pins:
            pi.hardware_PWM(pin, carrier_freq, duty)
        if _comp:
            anti_duty = _DUTY_MAX - duty
            for pin in _comp:
                pi.hardware_PWM(pin, carrier_freq, anti_duty)

        # Advance index to where we should be in real time
        elapsed = time.monotonic() - start
        i = max(i + 1, int(elapsed * sample_rate))

    # Cleanup: silence all pins
    for pin in pins:
        pi.hardware_PWM(pin, 0, 0)
    for pin in _comp:
        pi.hardware_PWM(pin, 0, 0)


# ---------------------------------------------------------------------------
# Spectral / vocoder playback
# ---------------------------------------------------------------------------

def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def _fft(x: list[complex]) -> list[complex]:
    """Radix-2 Cooley-Tukey FFT.  *x* length must be a power of 2."""
    n = len(x)
    if n <= 1:
        return list(x)
    even = _fft(x[0::2])
    odd = _fft(x[1::2])
    half = n // 2
    result: list[complex] = [complex(0)] * n
    for k in range(half):
        t = cmath.exp(-2j * cmath.pi * k / n) * odd[k]
        result[k] = even[k] + t
        result[k + half] = even[k] - t
    return result


def wav_to_tones(
    path: str,
    frame_ms: int = 20,
    min_freq: int = 60,
    max_freq: int = 3500,
) -> list[tuple[int, int, int]]:
    """Decompose a WAV file into (freq_hz, duty, duration_ms) tone frames.

    Uses STFT to find the dominant frequency in each *frame_ms* window,
    with amplitude mapped to a PWM duty value (0 … ``_SPECTRAL_DUTY_MAX``).
    """
    samples_8, sample_rate = load_wav(path)
    # Convert unsigned 8-bit (0-255) to signed for FFT
    signed = [s - 128 for s in samples_8]

    frame_size = int(sample_rate * frame_ms / 1000)
    fft_size = _next_pow2(frame_size)
    min_bin = max(1, int(min_freq * fft_size / sample_rate))
    max_bin = min(fft_size // 2, int(max_freq * fft_size / sample_rate))

    # Precompute Hamming window
    hamming = [
        0.54 - 0.46 * math.cos(2 * math.pi * i / (fft_size - 1))
        for i in range(fft_size)
    ]

    # First pass: gather peak frequencies and RMS per frame
    raw_frames: list[tuple[int, float]] = []  # (peak_freq, rms)
    for start in range(0, len(signed), frame_size):
        chunk = signed[start : start + frame_size]
        if len(chunk) < frame_size // 4:
            break

        # RMS amplitude of original chunk
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))

        # Zero-pad and window
        padded = chunk + [0] * (fft_size - len(chunk))
        windowed = [complex(padded[i] * hamming[i]) for i in range(fft_size)]

        spectrum = _fft(windowed)
        magnitudes = [abs(spectrum[k]) for k in range(min_bin, max_bin + 1)]

        if not magnitudes or max(magnitudes) < 1:
            raw_frames.append((0, 0.0))
            continue

        peak_idx = magnitudes.index(max(magnitudes))
        peak_freq = int((peak_idx + min_bin) * sample_rate / fft_size)
        raw_frames.append((peak_freq, rms))

    # Normalise RMS → duty across all frames
    max_rms = max((r for _, r in raw_frames), default=1.0) or 1.0
    tones: list[tuple[int, int, int]] = []
    for freq, rms in raw_frames:
        duty = int(rms / max_rms * _SPECTRAL_DUTY_MAX) if freq > 0 else 0
        tones.append((freq, duty, frame_ms))

    return tones


def play_tone_sequence(
    pi: pigpio.pi,
    pins: list[int],
    tones: list[tuple[int, int, int]],
    interrupt_event: threading.Event | None = None,
) -> None:
    """Play a sequence of *(freq_hz, duty, duration_ms)* tone frames.

    All *pins* are driven at the same frequency and duty (like melodies).
    """
    all_pins = list(pins)

    for freq, duty, duration_ms in tones:
        if interrupt_event and interrupt_event.is_set():
            break

        if freq > 0 and duty > 0:
            for pin in all_pins:
                pi.hardware_PWM(pin, freq, duty)
        else:
            for pin in all_pins:
                pi.hardware_PWM(pin, 0, 0)

        if interrupt_event:
            if interrupt_event.wait(duration_ms / 1000.0):
                break
        else:
            time.sleep(duration_ms / 1000.0)

    # Cleanup
    for pin in all_pins:
        pi.hardware_PWM(pin, 0, 0)
