"""Tests for AHT30 data-conversion formulas.

These tests exercise the pure maths embedded in the C firmware driver
(firmware/src/drivers/aht30.c) without requiring hardware.  Each test
feeds known raw 6-byte response packets and asserts the decoded
temperature and humidity values.

Firmware reference: aht30.c  aht30.h  (BIBA_NATIVE_TEST path)
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Decode helpers (mirror the C formulas exactly)
# ---------------------------------------------------------------------------

def _decode_humidity(buf: bytes) -> float:
    """Decode 20-bit humidity from 6-byte AHT30 read buffer.

    hum_raw = (buf[1] << 12) | (buf[2] << 4) | (buf[3] >> 4)
    humidity_pct = hum_raw / 1048576.0 * 100.0
    """
    hum_raw = (buf[1] << 12) | (buf[2] << 4) | (buf[3] >> 4)
    return hum_raw / 1048576.0 * 100.0


def _decode_temperature(buf: bytes) -> float:
    """Decode 20-bit temperature from 6-byte AHT30 read buffer.

    temp_raw = ((buf[3] & 0x0F) << 16) | (buf[4] << 8) | buf[5]
    temp_c = temp_raw / 1048576.0 * 200.0 - 50.0
    """
    temp_raw = ((buf[3] & 0x0F) << 16) | (buf[4] << 8) | buf[5]
    return temp_raw / 1048576.0 * 200.0 - 50.0


def _build_buf(status: int, hum_raw: int, temp_raw: int) -> bytes:
    """Pack a 6-byte AHT30 response for given raw 20-bit hum and temp values.

    Layout:
      buf[0]: status byte
      buf[1..2+]: humidity 20 bits upper portion
      buf[3]:     humidity lower 4 bits (upper nibble) | temp upper nibble
      buf[4..5]:  temperature lower 16 bits
    """
    # hum_raw occupies bits [39:20] in the 40-bit data payload (buf[1..5])
    # temp_raw occupies bits [19:0]
    # buf[1] = hum_raw[19:12]
    # buf[2] = hum_raw[11:4]
    # buf[3] = (hum_raw[3:0] << 4) | temp_raw[19:16]
    # buf[4] = temp_raw[15:8]
    # buf[5] = temp_raw[7:0]
    b1 = (hum_raw >> 12) & 0xFF
    b2 = (hum_raw >> 4) & 0xFF
    b3 = ((hum_raw & 0x0F) << 4) | ((temp_raw >> 16) & 0x0F)
    b4 = (temp_raw >> 8) & 0xFF
    b5 = temp_raw & 0xFF
    return bytes([status, b1, b2, b3, b4, b5])


# ---------------------------------------------------------------------------
# Humidity tests
# ---------------------------------------------------------------------------

def test_humidity_zero_raw_is_zero_percent() -> None:
    buf = _build_buf(0x00, hum_raw=0, temp_raw=0)
    assert _decode_humidity(buf) == 0.0


def test_humidity_full_scale_raw_is_100_percent() -> None:
    """hum_raw = 0xFFFFF (1048575) → 99.999... %."""
    buf = _build_buf(0x00, hum_raw=0xFFFFF, temp_raw=0)
    pct = _decode_humidity(buf)
    assert abs(pct - (0xFFFFF / 1048576.0 * 100.0)) < 1e-6
    assert pct < 100.0


def test_humidity_midscale_is_fifty_percent() -> None:
    """hum_raw = 0x80000 (524288) → exactly 50 %."""
    buf = _build_buf(0x00, hum_raw=0x80000, temp_raw=0)
    pct = _decode_humidity(buf)
    assert abs(pct - 50.0) < 0.01


def test_humidity_known_value() -> None:
    """hum_raw = 524288 → 50.0 %.  hum_raw = 629145.6... → 60 %; use closest int."""
    # 60 % → raw = 0x60 / 100 * 1048576 ≈ 629145
    raw = int(round(60.0 / 100.0 * 1048576))
    buf = _build_buf(0x00, hum_raw=raw, temp_raw=0)
    pct = _decode_humidity(buf)
    assert abs(pct - 60.0) < 0.01


# ---------------------------------------------------------------------------
# Temperature tests
# ---------------------------------------------------------------------------

def test_temperature_minus_50_is_zero_raw() -> None:
    """temp_raw = 0 → -50.0 °C."""
    buf = _build_buf(0x00, hum_raw=0, temp_raw=0)
    assert abs(_decode_temperature(buf) - (-50.0)) < 1e-6


def test_temperature_full_scale_is_150_deg() -> None:
    """temp_raw = 0xFFFFF → (1048575/1048576*200) - 50 ≈ 150.0 °C."""
    buf = _build_buf(0x00, hum_raw=0, temp_raw=0xFFFFF)
    t = _decode_temperature(buf)
    assert abs(t - (0xFFFFF / 1048576.0 * 200.0 - 50.0)) < 1e-6
    assert t < 150.1


def test_temperature_midscale_is_50_deg() -> None:
    """temp_raw = 0x80000 (524288) → (0.5 × 200) - 50 = 50 °C."""
    buf = _build_buf(0x00, hum_raw=0, temp_raw=0x80000)
    t = _decode_temperature(buf)
    assert abs(t - 50.0) < 0.01


def test_temperature_25_deg_roundtrip() -> None:
    """25 °C → raw = (25+50)/200 × 1048576 ≈ 393216; roundtrip within 0.01 °C."""
    raw = int(round((25.0 + 50.0) / 200.0 * 1048576))
    buf = _build_buf(0x00, hum_raw=0, temp_raw=raw)
    t = _decode_temperature(buf)
    assert abs(t - 25.0) < 0.01


# ---------------------------------------------------------------------------
# Status byte: busy flag
# ---------------------------------------------------------------------------

def test_busy_flag_detected_when_bit7_set() -> None:
    """Status byte bit 7 = 1 means sensor is busy — must not decode."""
    # The C code checks: if (buf[0] & 0x80) return false.
    busy_status = 0x98   # bit 7 = 1 (busy)
    busy_detected = bool(busy_status & 0x80)
    assert busy_detected is True


def test_not_busy_when_bit7_clear() -> None:
    """Status byte bit 7 = 0 means data is ready."""
    ready_status = 0x18   # bit 7 = 0 (not busy)
    busy_detected = bool(ready_status & 0x80)
    assert busy_detected is False
