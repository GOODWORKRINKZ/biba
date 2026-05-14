"""Tests for biba_stm32_bridge translator (pure logic, no rclpy required)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Add ros2_ws/src/biba_stm32_bridge to sys.path so the package imports without
# a colcon-built install/. Also expose biba-controller for stm32_link reuse.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws" / "src" / "biba_stm32_bridge"))
sys.path.insert(0, str(ROOT / "biba-controller"))

from biba_stm32_bridge import translator  # noqa: E402
from stm32_link.protocol import Telemetry  # noqa: E402


# ---------------------------------------------------------------------------
# cmd_vel_to_setpoints
# ---------------------------------------------------------------------------


def test_cmd_vel_zero_yields_zero_setpoints() -> None:
    left, right = translator.cmd_vel_to_setpoints(
        linear_x=0.0, angular_z=0.0, wheel_separation=0.3, max_wheel_speed=1.0
    )
    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)


def test_cmd_vel_pure_forward_drives_both_wheels_equally() -> None:
    left, right = translator.cmd_vel_to_setpoints(
        linear_x=0.5, angular_z=0.0, wheel_separation=0.3, max_wheel_speed=1.0
    )
    assert left == pytest.approx(0.5)
    assert right == pytest.approx(0.5)


def test_cmd_vel_pure_rotation_yields_opposite_setpoints() -> None:
    # ω = 1 rad/s, wheel_sep = 0.3 → wheel speed ±0.15 m/s.
    # Normalised by max_wheel_speed = 0.3 → ±0.5.
    left, right = translator.cmd_vel_to_setpoints(
        linear_x=0.0, angular_z=1.0, wheel_separation=0.3, max_wheel_speed=0.3
    )
    assert left == pytest.approx(-0.5)
    assert right == pytest.approx(0.5)


def test_cmd_vel_clips_setpoints_to_unit_interval() -> None:
    left, right = translator.cmd_vel_to_setpoints(
        linear_x=10.0, angular_z=0.0, wheel_separation=0.3, max_wheel_speed=1.0
    )
    assert left == pytest.approx(1.0)
    assert right == pytest.approx(1.0)

    left, right = translator.cmd_vel_to_setpoints(
        linear_x=-10.0, angular_z=0.0, wheel_separation=0.3, max_wheel_speed=1.0
    )
    assert left == pytest.approx(-1.0)
    assert right == pytest.approx(-1.0)


def test_cmd_vel_handles_nan_and_inf_gracefully() -> None:
    left, right = translator.cmd_vel_to_setpoints(
        linear_x=float("nan"), angular_z=0.0, wheel_separation=0.3, max_wheel_speed=1.0
    )
    assert left == 0.0 and right == 0.0

    left, right = translator.cmd_vel_to_setpoints(
        linear_x=0.0, angular_z=math.inf, wheel_separation=0.3, max_wheel_speed=1.0
    )
    assert left == 0.0 and right == 0.0


def test_cmd_vel_rejects_invalid_geometry() -> None:
    with pytest.raises(ValueError):
        translator.cmd_vel_to_setpoints(0.5, 0.0, wheel_separation=0.0, max_wheel_speed=1.0)
    with pytest.raises(ValueError):
        translator.cmd_vel_to_setpoints(0.5, 0.0, wheel_separation=0.3, max_wheel_speed=0.0)


# ---------------------------------------------------------------------------
# telemetry_to_stm32_fields / telemetry_to_crsf_fields
# ---------------------------------------------------------------------------


def _sample_telemetry() -> Telemetry:
    return Telemetry(
        setpoint_left=0.25,
        setpoint_right=-0.25,
        current_left_a=1.5,
        current_right_a=-1.5,
        vbat_v=12.6,
        rail_12v_v=11.9,
        gyro_x_dps=10.0,
        gyro_y_dps=-5.0,
        gyro_z_dps=2.5,
        accel_x_g=0.1,
        accel_y_g=-0.2,
        accel_z_g=0.98,
        crsf_rssi=120,
        crsf_link_quality=99,
        crsf_snr_db=-3,
        error_flags=0x05,
        uptime_ms=123_456,
    )


def test_telemetry_to_stm32_fields_maps_values_unmodified() -> None:
    tlm = _sample_telemetry()
    out = translator.telemetry_to_stm32_fields(tlm)
    assert out["vbat_volts"] == pytest.approx(12.6)
    assert out["left_current_amps"] == pytest.approx(1.5)
    assert out["right_current_amps"] == pytest.approx(-1.5)
    assert out["spi_link_uptime_ms"] == 123_456 & 0xFFFF
    assert out["flags"] == 0x05
    # Mode is reserved/zero for now (firmware does not expose it yet).
    assert out["mode"] == 0
    # mcu_temp_celsius is reserved (not in Telemetry struct).
    assert out["mcu_temp_celsius"] == pytest.approx(0.0)


def test_telemetry_to_crsf_fields_maps_link_metrics() -> None:
    tlm = _sample_telemetry()
    out = translator.telemetry_to_crsf_fields(tlm)
    # CRSF RSSI is stored unsigned by firmware (UAR is two's-complement-as-uint).
    # Translator interprets as signed dBm: 120 stays positive.
    assert out["rssi_dbm"] == 120
    assert out["link_quality"] == 99
    assert out["snr_db"] == -3
    # failsafe is decoded from error_flags bit-0 by convention.
    assert out["failsafe"] is True


def test_telemetry_to_crsf_fields_failsafe_low_when_bit_clear() -> None:
    tlm = _sample_telemetry()
    tlm.error_flags = 0x00
    out = translator.telemetry_to_crsf_fields(tlm)
    assert out["failsafe"] is False
