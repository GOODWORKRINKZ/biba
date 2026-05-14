"""Structural tests for biba_bringup composition-C ros2_control bringup.

Verifies the diff_drive_controller.yaml and control.launch.py files are
internally consistent and align with the URDF joint names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "ros2_ws/src/biba_bringup/config/diff_drive_controller.yaml"
LAUNCH = REPO / "ros2_ws/src/biba_bringup/launch/control.launch.py"
URDF = REPO / "ros2_ws/src/biba_description/urdf/biba.urdf.xacro"


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def test_controller_manager_declares_required_controllers(cfg: dict) -> None:
    cm = cfg["controller_manager"]["ros__parameters"]
    assert cm["update_rate"] == 50
    assert cm["joint_state_broadcaster"]["type"] == \
        "joint_state_broadcaster/JointStateBroadcaster"
    assert cm["diff_drive_controller"]["type"] == \
        "diff_drive_controller/DiffDriveController"


def test_diff_drive_wheel_names_match_urdf(cfg: dict) -> None:
    dd = cfg["diff_drive_controller"]["ros__parameters"]
    assert dd["left_wheel_names"] == ["left_wheel_joint"]
    assert dd["right_wheel_names"] == ["right_wheel_joint"]
    urdf_text = URDF.read_text()
    assert 'name="left_wheel_joint"' in urdf_text
    assert 'name="right_wheel_joint"' in urdf_text


def test_diff_drive_geometry_matches_urdf(cfg: dict) -> None:
    dd = cfg["diff_drive_controller"]["ros__parameters"]
    urdf_text = URDF.read_text()
    sep = re.search(r'wheel_separation"\s+value="([\d.]+)"', urdf_text)
    rad = re.search(r'wheel_radius"\s+value="([\d.]+)"', urdf_text)
    assert sep and rad
    assert float(sep.group(1)) == pytest.approx(dd["wheel_separation"])
    assert float(rad.group(1)) == pytest.approx(dd["wheel_radius"])


def test_diff_drive_open_loop_and_timeout(cfg: dict) -> None:
    dd = cfg["diff_drive_controller"]["ros__parameters"]
    # No encoders on the wheels — must be open-loop.
    assert dd["open_loop"] is True
    # Watchdog when /cmd_vel goes silent.
    assert dd["cmd_vel_timeout"] > 0.0
    assert dd["base_frame_id"] == "base_link"
    assert dd["odom_frame_id"] == "odom"


def test_launch_loads_urdf_and_controllers_yaml() -> None:
    text = LAUNCH.read_text()
    assert 'package="controller_manager"' in text
    assert 'executable="ros2_control_node"' in text
    assert "diff_drive_controller.yaml" in text
    assert "biba.urdf.xacro" in text
    # Both spawners present.
    assert "joint_state_broadcaster" in text
    assert "diff_drive_controller" in text


def test_launch_starts_robot_state_publisher() -> None:
    text = LAUNCH.read_text()
    assert 'package="robot_state_publisher"' in text
    assert 'executable="robot_state_publisher"' in text
