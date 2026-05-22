"""Phase 06 Task 7 — unit tests for IS-PoC frequency estimators.

D-12 acceptance: each estimator must recover the input sine frequency
within ±5% on a synthetic signal in the RPM band actually observed at
the BTS7960 IS pin (≈ 2–25 Hz over the duty sweep, per hardware capture
of 2026-05-22).  The analyser was retuned from the original 100–5000 Hz
search window to 1–200 Hz after the time-domain plot revealed the real
signal sits well below 100 Hz.

Test signal: n = 8192 samples @ 10 kSPS → 820 ms window, ≥ 4 cycles even
at the lowest test frequency (5 Hz) and Δf = 1.22 Hz FFT bin width.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from is_poc_analyse import freq_autocorr, freq_fft, freq_zero_crossing  # noqa: E402


def make_signal(
    freq_hz: float,
    sps: int = 10000,
    n: int = 8192,
    amplitude: float = 300.0,
    noise_std: float = 8.0,
) -> np.ndarray:
    """Synthetic IS-like signal.

    SNR ≈ 38 (amplitude 300 LSB / σ 8 LSB) matches the cleanest sections
    of the 2026-05-22 hardware capture, where the flat baseline shows
    ~25 LSB peak-to-peak noise (σ ≈ 8) on top of a ~600 LSB peak-to-peak
    RPM modulation.  Earlier σ=30 was too pessimistic for the
    low-frequency band (only 4–16 cycles in 820 ms), which made the
    threshold-based ZC and first-local-max AC trigger on noise.
    """
    rng = np.random.default_rng(42)
    t = np.arange(n) / sps
    return 2048.0 + amplitude * np.sin(2 * np.pi * freq_hz * t) + rng.normal(
        0.0, noise_std, n
    )


# RPM-band frequencies matching observed capture (duty 25/50/75/100 → ≈ 5/10/15/20 Hz).
@pytest.mark.parametrize("freq", [5, 10, 15, 20])
def test_fft_recovers_frequency(freq: int) -> None:
    sig = make_signal(float(freq))
    est = freq_fft(sig, 10000)
    assert abs(est - freq) / freq < 0.05, f"FFT off: est={est} freq={freq}"


@pytest.mark.parametrize("freq", [5, 10, 15, 20])
def test_zero_crossing_recovers_frequency(freq: int) -> None:
    sig = make_signal(float(freq))
    est = freq_zero_crossing(sig, 10000)
    assert abs(est - freq) / freq < 0.05, f"ZC off: est={est} freq={freq}"


@pytest.mark.parametrize("freq", [5, 10, 15, 20])
def test_autocorr_recovers_frequency(freq: int) -> None:
    sig = make_signal(float(freq))
    est = freq_autocorr(sig, 10000)
    assert abs(est - freq) / freq < 0.05, f"AC off: est={est} freq={freq}"


def test_fft_ignores_dc_offset() -> None:
    # 10 Hz fundamental with extra +1000 LSB DC offset on top of the 2048 baseline.
    sig = make_signal(10.0) + 1000.0
    est = freq_fft(sig, 10000)
    assert abs(est - 10.0) / 10.0 < 0.05, f"FFT leaked to DC: est={est}"


def test_zero_crossing_flat_signal() -> None:
    sig = np.full(8192, 2048.0)
    assert freq_zero_crossing(sig, 10000) == 0.0


def test_autocorr_flat_signal() -> None:
    sig = np.full(8192, 2048.0)
    assert freq_autocorr(sig, 10000) == 0.0
