"""SPI ↔ ROS2 bridge поверх biba-controller/stm32_link/.

Pure-Python translator logic lives in :mod:`.translator` and is unit-tested
without rclpy. The rclpy node lives in :mod:`.bridge_node` and is exercised
inside the ROS2 container.
"""

from . import translator  # noqa: F401

