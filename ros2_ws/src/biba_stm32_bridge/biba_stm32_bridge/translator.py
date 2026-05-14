"""Pure (rclpy-free) translation logic for the BiBa STM32 bridge.

This module is intentionally free of ROS2 imports so it can be unit-tested
on a developer laptop. The :mod:`bridge_node` glue layer wires it into
``rclpy``.
"""

from __future__ import annotations

import math
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from stm32_link.protocol import Telemetry


__all__ = [
    "cmd_vel_to_setpoints",
    "telemetry_to_stm32_fields",
    "telemetry_to_crsf_fields",
]


def _is_finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def cmd_vel_to_setpoints(
    linear_x: float,
    angular_z: float,
    wheel_separation: float,
    max_wheel_speed: float,
) -> Tuple[float, float]:
    """Translate a ``geometry_msgs/Twist`` into normalised wheel setpoints.

    The STM32 firmware accepts a Q15-normalised setpoint in the range
    ``[-1.0, +1.0]`` per side via :func:`stm32_link.protocol.build_setpoint`.

    Returns a ``(left, right)`` tuple, both clipped to ``[-1.0, +1.0]``.
    Non-finite inputs (``NaN``/``inf``) are coerced to a safe stop ``(0, 0)``.
    """
    if wheel_separation <= 0.0:
        raise ValueError(f"wheel_separation must be > 0, got {wheel_separation}")
    if max_wheel_speed <= 0.0:
        raise ValueError(f"max_wheel_speed must be > 0, got {max_wheel_speed}")

    if not _is_finite(linear_x, angular_z):
        return (0.0, 0.0)

    half_track = wheel_separation / 2.0
    left_speed = linear_x - angular_z * half_track
    right_speed = linear_x + angular_z * half_track

    left = left_speed / max_wheel_speed
    right = right_speed / max_wheel_speed
    return (_clip_unit(left), _clip_unit(right))


def _clip_unit(value: float) -> float:
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return value


def telemetry_to_stm32_fields(tlm: "Telemetry") -> dict:
    """Map :class:`stm32_link.protocol.Telemetry` to ``biba_msgs/Stm32Telemetry`` fields.

    Returned dict carries primitive Python values; the ROS2 layer copies
    them into the actual message instance (which requires the generated
    Python module to be on ``PYTHONPATH``, available only inside the
    container).
    """
    return {
        "firmware_revision": 0,  # firmware does not expose a revision word yet
        "spi_link_uptime_ms": int(tlm.uptime_ms) & 0xFFFF,
        "mode": 0,  # reserved
        "flags": int(tlm.error_flags) & 0xFF,
        "vbat_volts": float(tlm.vbat_v),
        "left_current_amps": float(tlm.current_left_a),
        "right_current_amps": float(tlm.current_right_a),
        "mcu_temp_celsius": 0.0,  # not reported by current firmware
    }


def telemetry_to_crsf_fields(tlm: "Telemetry") -> dict:
    """Map telemetry CRSF link metrics to ``biba_msgs/CrsfStatus`` fields.

    ``failsafe`` is derived from ``error_flags`` bit-0 (firmware sets that
    bit when CRSF input goes stale or the receiver reports failsafe).
    """
    return {
        "rssi_dbm": int(tlm.crsf_rssi) & 0xFF,
        "link_quality": int(tlm.crsf_link_quality) & 0xFF,
        "snr_db": int(tlm.crsf_snr_db),
        "failsafe": bool(int(tlm.error_flags) & 0x01),
    }
