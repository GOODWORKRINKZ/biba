"""Phase 06 Task 7 — unit tests for IS-PoC frequency estimators.

D-12 acceptance: each estimator must recover the input sine frequency
within ±5% on a synthetic signal of duration 2048 / 10000 ≈ 205 ms with
modest amplitude (300 LSB) and noise (σ=30 LSB) at the test frequencies.
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
    n: int = 2048,
    amplitude: float = 300.0,
    noise_std: float = 30.0,
) -> np.ndarray:
    rng = np.random.default_rng(42)
    t = np.arange(n) / sps
    return 2048.0 + amplitude * np.sin(2 * np.pi * freq_hz * t) + rng.normal(
        0.0, noise_std, n
    )


@pytest.mark.parametrize("freq", [300, 500, 800, 1000])
def test_fft_recovers_frequency(freq: int) -> None:
    sig = make_signal(float(freq))
    est = freq_fft(sig, 10000)
    assert abs(est - freq) / freq < 0.05, f"FFT off: est={est} freq={freq}"


@pytest.mark.parametrize("freq", [300, 500, 800, 1000])
def test_zero_crossing_recovers_frequency(freq: int) -> None:
    sig = make_signal(float(freq))
    est = freq_zero_crossing(sig, 10000)
    assert abs(est - freq) / freq < 0.05, f"ZC off: est={est} freq={freq}"


@pytest.mark.parametrize("freq", [300, 500, 800, 1000])
def test_autocorr_recovers_frequency(freq: int) -> None:
    sig = make_signal(float(freq))
    est = freq_autocorr(sig, 10000)
    assert abs(est - freq) / freq < 0.05, f"AC off: est={est} freq={freq}"


def test_fft_ignores_dc_offset() -> None:
    sig = make_signal(1000.0) + 1000.0
    assert freq_fft(sig, 10000) > 100.0


def test_zero_crossing_flat_signal() -> None:
    sig = np.full(2048, 2048.0)
    assert freq_zero_crossing(sig, 10000) == 0.0


def test_autocorr_flat_signal() -> None:
    sig = np.full(2048, 2048.0)
    assert freq_autocorr(sig, 10000) == 0.0
