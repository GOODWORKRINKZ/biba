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
import hashlib
import json
import math
import struct
import threading
import time
import wave
from pathlib import Path

import pigpio

DEFAULT_CARRIER_HZ = 16000
_DUTY_MAX = 1_000_000
_INTERRUPT_CHECK_INTERVAL = 256  # check interrupt every N samples
_SPECTRAL_DUTY_MAX = 500_000  # 50 % duty → max fundamental amplitude
_SPECTRAL_FRAME_MS = 12
_SPECTRAL_HOP_MS = 6
_SPECTRAL_N_PEAKS = 2
_SPEECH_MIN_FREQ = 150
_SPEECH_MAX_FREQ = 800
_SPECTRAL_CACHE_VERSION = 1


def split_peak_frames_by_side(
    frames: list[tuple[list[tuple[int, int]], int]],
) -> tuple[list[tuple[list[tuple[int, int]], int]], list[tuple[list[tuple[int, int]], int]]]:
    left_frames: list[tuple[list[tuple[int, int]], int]] = []
    right_frames: list[tuple[list[tuple[int, int]], int]] = []

    for peaks, duration_ms in frames:
        left_frames.append((peaks[0::2], duration_ms))
        right_frames.append((peaks[1::2], duration_ms))

    return left_frames, right_frames


def _stabilize_peak_frames(
    frames: list[tuple[list[tuple[int, int]], int]],
    *,
    freq_snap_hz: int = 80,
    duty_blend: float = 0.35,
) -> list[tuple[list[tuple[int, int]], int]]:
    """Reduce frame-to-frame jitter in peak frequency and duty.

    Peaks are matched by position within the frame. When a peak stays within
    ``freq_snap_hz`` of the previous frame's peak, its frequency snaps to the
    previous value and its duty is blended with the previous duty.
    """
    if not frames:
        return []

    stabilized: list[tuple[list[tuple[int, int]], int]] = []
    previous_peaks: list[tuple[int, int]] = []

    for peaks, duration_ms in frames:
        if not peaks:
            stabilized.append(([], duration_ms))
            previous_peaks = []
            continue

        current: list[tuple[int, int]] = []
        for index, (freq, duty) in enumerate(peaks):
            if index < len(previous_peaks):
                prev_freq, prev_duty = previous_peaks[index]
                if abs(freq - prev_freq) <= freq_snap_hz:
                    freq = prev_freq
                    duty = int(prev_duty * (1.0 - duty_blend) + duty * duty_blend)
            current.append((freq, duty))

        stabilized.append((current, duration_ms))
        previous_peaks = current

    return stabilized


def _select_peak_bins(
    magnitudes: list[float],
    *,
    min_bin: int,
    sample_rate: int,
    fft_size: int,
    n_peaks: int,
) -> list[tuple[int, float]]:
    """Return up to *n_peaks* dominant bins as (freq_hz, magnitude)."""
    if not magnitudes:
        return []

    top_mag = max(magnitudes)
    if top_mag < 1:
        return []

    ranked = sorted(
        enumerate(magnitudes, start=min_bin),
        key=lambda item: item[1],
        reverse=True,
    )

    chosen: list[tuple[int, float]] = []
    chosen_bins: list[int] = []
    for bin_idx, magnitude in ranked:
        if magnitude < top_mag * 0.25:
            break
        if any(abs(bin_idx - existing) <= 1 for existing in chosen_bins):
            continue
        freq = int(bin_idx * sample_rate / fft_size)
        chosen.append((freq, magnitude))
        chosen_bins.append(bin_idx)
        if len(chosen) >= n_peaks:
            break
    return chosen


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


def wav_to_peak_frames(
    path: str,
    frame_ms: int = _SPECTRAL_FRAME_MS,
    hop_ms: int = _SPECTRAL_HOP_MS,
    n_peaks: int = _SPECTRAL_N_PEAKS,
    min_freq: int = _SPEECH_MIN_FREQ,
    max_freq: int = _SPEECH_MAX_FREQ,
) -> list[tuple[list[tuple[int, int]], int]]:
    """Analyze a WAV into overlapping multi-peak spectral frames.

    Returns a list of ``(peaks, duration_ms)`` where ``peaks`` is a list of
    ``(freq_hz, duty)`` pairs for the strongest peaks in that frame.

    Peak duty is scaled by both local peak prominence and the frame RMS
    envelope so quieter syllables remain quieter across the whole phrase
    instead of every voiced frame normalizing to the same duty ceiling.
    """
    samples_8, sample_rate = load_wav(path)
    signed = [s - 128 for s in samples_8]

    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    hop_size = max(1, int(sample_rate * hop_ms / 1000))
    fft_size = _next_pow2(frame_size)
    min_bin = max(1, int(min_freq * fft_size / sample_rate))
    max_bin = min(fft_size // 2, int(max_freq * fft_size / sample_rate))
    hamming = [
        0.54 - 0.46 * math.cos(2 * math.pi * i / (fft_size - 1))
        for i in range(fft_size)
    ]

    raw_frames: list[tuple[list[tuple[int, float]], float]] = []
    for start in range(0, len(signed), hop_size):
        chunk = signed[start : start + frame_size]
        if len(chunk) < frame_size // 4:
            break

        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        if rms < 5.0:
            raw_frames.append(([], 0.0))
            continue

        padded = chunk + [0] * (fft_size - len(chunk))
        windowed = [complex(padded[i] * hamming[i]) for i in range(fft_size)]
        spectrum = _fft(windowed)
        magnitudes = [abs(spectrum[k]) for k in range(min_bin, max_bin + 1)]
        peaks = _select_peak_bins(
            magnitudes,
            min_bin=min_bin,
            sample_rate=sample_rate,
            fft_size=fft_size,
            n_peaks=n_peaks,
        )
        if not peaks:
            raw_frames.append(([], 0.0))
            continue

        raw_frames.append((peaks, rms))

    max_rms = max((rms for _peaks, rms in raw_frames), default=1.0) or 1.0
    frames: list[tuple[list[tuple[int, int]], int]] = []
    for peaks, rms in raw_frames:
        if not peaks or rms <= 0.0:
            frames.append(([], hop_ms))
            continue

        top_mag = max(magnitude for _, magnitude in peaks) or 1.0
        frame_scale = min(1.0, rms / max_rms)
        peak_frame = [
            (freq, int((magnitude / top_mag) * frame_scale * _SPECTRAL_DUTY_MAX))
            for freq, magnitude in peaks
        ]
        frames.append((peak_frame, hop_ms))

    return _stabilize_peak_frames(frames)


def write_peak_frame_cache(
    cache_path: str | Path,
    source_path: str | Path,
    frames: list[tuple[list[tuple[int, int]], int]],
) -> Path:
    source_file = Path(source_path)
    cache_file = Path(cache_path)
    payload = {
        "version": _SPECTRAL_CACHE_VERSION,
        "source_name": source_file.name,
        "source_sha256": _hash_file(source_file),
        "frames": frames,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return cache_file


def load_peak_frame_cache(
    cache_path: str | Path,
    source_path: str | Path,
) -> list[tuple[list[tuple[int, int]], int]] | None:
    cache_file = Path(cache_path)
    source_file = Path(source_path)
    if not cache_file.exists() or not source_file.exists():
        return None

    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if payload.get("version") != _SPECTRAL_CACHE_VERSION:
            return None
        if payload.get("source_name") != source_file.name:
            return None
        if payload.get("source_sha256") != _hash_file(source_file):
            return None

        cached_frames = payload.get("frames")
        if not isinstance(cached_frames, list):
            return None
        return [
            ([(int(freq), int(duty)) for freq, duty in peaks], int(duration_ms))
            for peaks, duration_ms in cached_frames
        ]
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_or_build_peak_frames(
    source_path: str | Path,
    *,
    cache_path: str | Path | None = None,
) -> list[tuple[list[tuple[int, int]], int]]:
    source_file = Path(source_path)
    resolved_cache_path = Path(cache_path) if cache_path is not None else _default_peak_frame_cache_path(source_file)
    if resolved_cache_path is not None:
        cached_frames = load_peak_frame_cache(resolved_cache_path, source_file)
        if cached_frames is not None:
            return cached_frames
    return wav_to_peak_frames(str(source_file))


def load_or_build_split_peak_frames(
    source_path: str | Path,
) -> tuple[list[tuple[list[tuple[int, int]], int]], list[tuple[list[tuple[int, int]], int]]]:
    source_file = Path(source_path)
    left_cache_path, right_cache_path = _default_split_peak_frame_cache_paths(source_file)
    if left_cache_path is not None and right_cache_path is not None:
        left_frames = load_peak_frame_cache(left_cache_path, source_file)
        right_frames = load_peak_frame_cache(right_cache_path, source_file)
        if left_frames is not None and right_frames is not None:
            return left_frames, right_frames

    live_frames = wav_to_peak_frames(str(source_file))
    return split_peak_frames_by_side(live_frames)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _default_peak_frame_cache_path(source_path: Path) -> Path | None:
    if source_path.parent.name != "voice":
        return None
    return source_path.parent.parent / "voice-cache" / f"{source_path.stem}.peaks.json"


def _default_split_peak_frame_cache_paths(source_path: Path) -> tuple[Path | None, Path | None]:
    if source_path.parent.name != "voice":
        return None, None
    cache_dir = source_path.parent.parent / "voice-cache"
    return (
        cache_dir / f"{source_path.stem}.left.peaks.json",
        cache_dir / f"{source_path.stem}.right.peaks.json",
    )


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


def play_peak_frames(
    pi: pigpio.pi,
    pins: list[int],
    frames: list[tuple[list[tuple[int, int]], int]],
    interrupt_event: threading.Event | None = None,
) -> None:
    """Play overlapping-analysis frames as a deterministic sequence of peaks."""
    all_pins = list(pins)

    for peaks, duration_ms in frames:
        if interrupt_event and interrupt_event.is_set():
            break

        if not peaks:
            for pin in all_pins:
                pi.hardware_PWM(pin, 0, 0)
            delay_s = duration_ms / 1000.0
            if interrupt_event:
                if interrupt_event.wait(delay_s):
                    break
            else:
                time.sleep(delay_s)
            continue

        slot_s = (duration_ms / 1000.0) / max(len(peaks), 1)
        for freq, duty in peaks:
            if interrupt_event and interrupt_event.is_set():
                break
            for pin in all_pins:
                pi.hardware_PWM(pin, freq, duty)
            if interrupt_event:
                if interrupt_event.wait(slot_s):
                    break
            else:
                time.sleep(slot_s)

    for pin in all_pins:
        pi.hardware_PWM(pin, 0, 0)


def play_split_peak_frames(
    pi: pigpio.pi,
    left_pins: list[int],
    right_pins: list[int],
    left_frames: list[tuple[list[tuple[int, int]], int]],
    right_frames: list[tuple[list[tuple[int, int]], int]],
    interrupt_event: threading.Event | None = None,
) -> None:
    all_left_pins = list(left_pins)
    all_right_pins = list(right_pins)
    frame_count = max(len(left_frames), len(right_frames))

    for frame_index in range(frame_count):
        if interrupt_event and interrupt_event.is_set():
            break

        left_peaks, left_duration_ms = left_frames[frame_index] if frame_index < len(left_frames) else ([], 0)
        right_peaks, right_duration_ms = right_frames[frame_index] if frame_index < len(right_frames) else ([], 0)
        duration_ms = left_duration_ms or right_duration_ms
        slot_count = max(len(left_peaks), len(right_peaks), 1)
        slot_s = (duration_ms / 1000.0) / slot_count if duration_ms > 0 else 0.0

        for slot_index in range(slot_count):
            if interrupt_event and interrupt_event.is_set():
                break

            if slot_index < len(left_peaks):
                left_freq, left_duty = left_peaks[slot_index]
                for pin in all_left_pins:
                    pi.hardware_PWM(pin, left_freq, left_duty)
            else:
                for pin in all_left_pins:
                    pi.hardware_PWM(pin, 0, 0)

            if slot_index < len(right_peaks):
                right_freq, right_duty = right_peaks[slot_index]
                for pin in all_right_pins:
                    pi.hardware_PWM(pin, right_freq, right_duty)
            else:
                for pin in all_right_pins:
                    pi.hardware_PWM(pin, 0, 0)

            if interrupt_event:
                if interrupt_event.wait(slot_s):
                    break
            else:
                time.sleep(slot_s)

    for pin in all_left_pins + all_right_pins:
        pi.hardware_PWM(pin, 0, 0)
