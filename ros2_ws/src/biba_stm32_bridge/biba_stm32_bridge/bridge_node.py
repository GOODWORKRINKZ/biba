"""ROS2 bridge node between geometry_msgs/Twist and STM32 SPI link.

Lives at the boundary: pulls in :mod:`rclpy` and the generated
``biba_msgs`` Python modules; reuses the pure logic from
:mod:`biba_stm32_bridge.translator` and the SPI client from
``stm32_link.client`` (vendored from ``biba-controller/``).

This module is intentionally untested by the CPU-only test suite — it is
exercised end-to-end inside the ROS2 container on the robot.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from std_srvs.srv import SetBool

from biba_msgs.msg import CrsfStatus, Stm32Telemetry  # type: ignore[import]

from biba_stm32_bridge import translator

# stm32_link/ ships with biba-controller/. The container layer mounts that
# directory into the Python path; on the robot it is also the canonical
# location used by main.py. Keep the import lazy-friendly.
try:
    from stm32_link.client import STM32Link, STM32LinkConfig
    from stm32_link.protocol import Telemetry, TelemetryFrame  # noqa: F401
except ImportError:  # pragma: no cover - container packaging issue
    _BIBA_CONTROLLER = Path(os.environ.get("BIBA_CONTROLLER_PATH", "/biba-controller"))
    if _BIBA_CONTROLLER.exists():
        sys.path.insert(0, str(_BIBA_CONTROLLER))
    from stm32_link.client import STM32Link, STM32LinkConfig
    from stm32_link.protocol import Telemetry, TelemetryFrame  # noqa: F401


log = logging.getLogger(__name__)


class Stm32BridgeNode(Node):
    """Forward /cmd_vel to the STM32 and re-publish telemetry as ROS2 topics.

    Topics:
        - subscribes ``/cmd_vel`` (``geometry_msgs/Twist``)
        - publishes ``/biba/stm32/telemetry`` (``biba_msgs/Stm32Telemetry``)
        - publishes ``/biba/crsf/status`` (``biba_msgs/CrsfStatus``)

    Services:
        - ``/biba/arm`` (``std_srvs/SetBool``) — arms (data=True) or disarms.

    Parameters:
        - ``wheel_separation`` (double, default 0.30 m)
        - ``max_wheel_speed`` (double, default 1.0 m/s — used as the
          normalisation factor; mapping to physical speed is calibrated
          downstream by ``biba_hardware_stm32``)
        - ``setpoint_rate_hz`` (double, default 50.0)
        - ``telemetry_rate_hz`` (double, default 20.0)
        - ``cmd_vel_timeout_sec`` (double, default 0.5) — auto-stop when
          no Twist message arrives within this window.
    """

    def __init__(self, link: Optional[STM32Link] = None) -> None:
        super().__init__("biba_stm32_bridge")

        self.declare_parameter("wheel_separation", 0.30)
        self.declare_parameter("max_wheel_speed", 1.0)
        self.declare_parameter("setpoint_rate_hz", 50.0)
        self.declare_parameter("telemetry_rate_hz", 20.0)
        self.declare_parameter("cmd_vel_timeout_sec", 0.5)

        self._wheel_sep = float(self.get_parameter("wheel_separation").value)
        self._max_speed = float(self.get_parameter("max_wheel_speed").value)
        self._cmd_vel_timeout = float(self.get_parameter("cmd_vel_timeout_sec").value)

        self._link = link if link is not None else STM32Link(STM32LinkConfig())

        self._last_cmd: tuple[float, float] = (0.0, 0.0)
        self._last_cmd_stamp = self.get_clock().now()

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._tlm_pub = self.create_publisher(Stm32Telemetry, "/biba/stm32/telemetry", qos)
        self._crsf_pub = self.create_publisher(CrsfStatus, "/biba/crsf/status", qos)
        self._cmd_sub = self.create_subscription(Twist, "/cmd_vel", self._on_cmd_vel, qos)
        self._arm_srv = self.create_service(SetBool, "/biba/arm", self._on_arm)

        sp_hz = float(self.get_parameter("setpoint_rate_hz").value)
        tlm_hz = float(self.get_parameter("telemetry_rate_hz").value)
        self._setpoint_timer = self.create_timer(1.0 / sp_hz, self._tick_setpoint)
        self._telemetry_timer = self.create_timer(1.0 / tlm_hz, self._tick_telemetry)

        self.get_logger().info(
            f"biba_stm32_bridge ready: wheel_sep={self._wheel_sep}m, "
            f"max_speed={self._max_speed}m/s, sp_rate={sp_hz}Hz, tlm_rate={tlm_hz}Hz"
        )

    # ------------------------------------------------------------------ subs

    def _on_cmd_vel(self, msg: Twist) -> None:
        try:
            left, right = translator.cmd_vel_to_setpoints(
                linear_x=msg.linear.x,
                angular_z=msg.angular.z,
                wheel_separation=self._wheel_sep,
                max_wheel_speed=self._max_speed,
            )
        except ValueError as exc:
            self.get_logger().warning(f"invalid cmd_vel geometry: {exc}")
            return
        self._last_cmd = (left, right)
        self._last_cmd_stamp = self.get_clock().now()

    # ------------------------------------------------------------------ srv

    def _on_arm(self, request: SetBool.Request, response: SetBool.Response):
        try:
            self._link.arm(bool(request.data))
        except Exception as exc:  # noqa: BLE001
            response.success = False
            response.message = f"arm({request.data}) failed: {exc}"
            self.get_logger().error(response.message)
            return response
        response.success = True
        response.message = "armed" if request.data else "disarmed"
        return response

    # ------------------------------------------------------------------ timers

    def _tick_setpoint(self) -> None:
        now = self.get_clock().now()
        age = (now - self._last_cmd_stamp).nanoseconds * 1e-9
        if age > self._cmd_vel_timeout:
            left, right = 0.0, 0.0
        else:
            left, right = self._last_cmd
        try:
            self._link.set_setpoint(left, right)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning(f"set_setpoint failed: {exc}")

    def _tick_telemetry(self) -> None:
        try:
            frame = self._link.ping()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning(f"telemetry ping failed: {exc}")
            return
        self._publish_telemetry(frame.telemetry)

    # ------------------------------------------------------------------ pubs

    def _publish_telemetry(self, tlm: Telemetry) -> None:
        stamp = self.get_clock().now().to_msg()

        stm = Stm32Telemetry()
        stm.header.stamp = stamp
        stm.header.frame_id = "stm32"
        for k, v in translator.telemetry_to_stm32_fields(tlm).items():
            setattr(stm, k, v)
        self._tlm_pub.publish(stm)

        crsf = CrsfStatus()
        crsf.header.stamp = stamp
        crsf.header.frame_id = "crsf"
        for k, v in translator.telemetry_to_crsf_fields(tlm).items():
            setattr(crsf, k, v)
        self._crsf_pub.publish(crsf)

    # ------------------------------------------------------------------ shutdown

    def destroy_node(self) -> bool:
        try:
            self._link.set_setpoint(0.0, 0.0)
            self._link.arm(False)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._link.close()
        except Exception:  # noqa: BLE001
            pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Stm32BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":  # pragma: no cover
    main()
