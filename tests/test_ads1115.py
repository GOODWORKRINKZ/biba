"""Tests for ADS1115 data-conversion formulas.

These tests exercise the pure maths embedded in the C firmware driver
(firmware/src/drivers/ads1115.c) without requiring hardware.  Each test
encodes a known raw value → expected voltage, or verifies that the
ADS1115 config-register MUX field is built correctly for each channel.

Firmware reference: ads1115.c  ads1115.h  (BIBA_NATIVE_TEST path)
"""

from __future__ import annotations

import struct


# ---------------------------------------------------------------------------
# Voltage-conversion formula
# ---------------------------------------------------------------------------
# FSR ±4.096 V, 16-bit signed → LSB = 4.096 / 32768 V

ADS1115_FSR_4096_LSB_V = 4.096 / 32768.0


def _raw_to_volts(raw_int16: int) -> float:
    """Replicate: v = (int16_t)raw * (4.096f / 32768.0f)"""
    # Ensure two's-complement interpretation
    if raw_int16 > 0x7FFF:
        raw_int16 -= 0x10000
    return raw_int16 * ADS1115_FSR_4096_LSB_V


def test_voltage_conversion_positive_full_scale() -> None:
    """0x7FFF (32767) → +4.096 V × (32767/32768) ≈ +4.09587 V."""
    v = _raw_to_volts(0x7FFF)
    assert abs(v - (32767 * ADS1115_FSR_4096_LSB_V)) < 1e-9


def test_voltage_conversion_zero() -> None:
    """0x0000 → 0 V."""
    assert _raw_to_volts(0x0000) == 0.0


def test_voltage_conversion_negative_full_scale() -> None:
    """0x8000 (-32768 two's-complement) → -4.096 V."""
    v = _raw_to_volts(0x8000)
    assert abs(v - (-32768 * ADS1115_FSR_4096_LSB_V)) < 1e-9
    assert abs(v - (-4.096)) < 1e-6


def test_voltage_conversion_midscale_positive() -> None:
    """0x4000 (16384) → approximately +2.048 V."""
    v = _raw_to_volts(0x4000)
    expected = 16384 * ADS1115_FSR_4096_LSB_V  # ≈ 2.048 V
    assert abs(v - expected) < 1e-6


def test_voltage_conversion_known_current_at_8amps() -> None:
    """IS pin at 8 A → VIS = 8/8.5 ≈ 0.941 V.
    raw = 0.941 / LSB ≈ 7534.  Verify reverse: raw → volts → amps ≈ 8 A."""
    amps_per_volt = 8.5
    expected_amps = 8.0
    raw = int(round((expected_amps / amps_per_volt) / ADS1115_FSR_4096_LSB_V))
    v = _raw_to_volts(raw)
    computed_amps = v * amps_per_volt
    assert abs(computed_amps - expected_amps) < 0.05  # within 50 mA


# ---------------------------------------------------------------------------
# Config-register MUX encoding
# ---------------------------------------------------------------------------
# Firmware encodes single-ended channels as MUX = 0b100 | channel.
# Config register bits [14:12] = MUX[2:0], bits [11:9] = PGA.

CFG_MUX_SHIFT = 12
CFG_OS_BIT    = 15
CFG_PGA_SHIFT = 9
CFG_MODE_BIT  = 8
CFG_DR_SHIFT  = 5
CFG_DR_128SPS = 4   # DR=100b → 128 SPS

# Expected MUX codes for single-ended AINx vs GND
_MUX_SE = {0: 4, 1: 5, 2: 6, 3: 7}


def _build_config(channel: int, pga_bits: int = 1) -> int:
    """Build ADS1115 config register word exactly as the firmware does."""
    mux = _MUX_SE[channel]
    return (
        (1 << CFG_OS_BIT)
        | (mux << CFG_MUX_SHIFT)
        | (pga_bits << CFG_PGA_SHIFT)
        | (1 << CFG_MODE_BIT)
        | (CFG_DR_128SPS << CFG_DR_SHIFT)
    )


def test_config_mux_channel0_is_ain0_vs_gnd() -> None:
    """Channel 0 → MUX = 100b (bits 14:12)."""
    cfg = _build_config(0)
    mux = (cfg >> CFG_MUX_SHIFT) & 0x7
    assert mux == 4, f"expected MUX=100b (4), got {mux}"


def test_config_mux_channel1_is_ain1_vs_gnd() -> None:
    """Channel 1 → MUX = 101b (bits 14:12)."""
    cfg = _build_config(1)
    mux = (cfg >> CFG_MUX_SHIFT) & 0x7
    assert mux == 5


def test_config_mux_channel2_is_ain2_vs_gnd() -> None:
    """Channel 2 → MUX = 110b (bits 14:12)."""
    cfg = _build_config(2)
    mux = (cfg >> CFG_MUX_SHIFT) & 0x7
    assert mux == 6


def test_config_mux_channel3_is_ain3_vs_gnd() -> None:
    """Channel 3 → MUX = 111b (bits 14:12)."""
    cfg = _build_config(3)
    mux = (cfg >> CFG_MUX_SHIFT) & 0x7
    assert mux == 7


def test_config_os_bit_is_set_to_start_conversion() -> None:
    """OS bit (15) must be 1 to trigger single-shot conversion."""
    for ch in (0, 1, 2, 3):
        cfg = _build_config(ch)
        assert cfg & (1 << CFG_OS_BIT), f"OS bit not set for channel {ch}"


def test_config_mode_bit_is_single_shot() -> None:
    """MODE bit (8) must be 1 for single-shot (power-down after)."""
    for ch in (0, 1, 2, 3):
        cfg = _build_config(ch)
        assert cfg & (1 << CFG_MODE_BIT), f"MODE bit not set for channel {ch}"


def test_config_pga_is_4096mv_fsr() -> None:
    """PGA bits [11:9] = 001b → FSR ±4.096 V for BTS7960 IS measurement."""
    cfg = _build_config(0, pga_bits=1)
    pga = (cfg >> CFG_PGA_SHIFT) & 0x7
    assert pga == 1, f"expected PGA=001b (1), got {pga}"
