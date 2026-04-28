"""Structural tests for the <ros2_control> block in biba.urdf.xacro.

These tests parse the xacro source as XML (xacro substitutions are
preserved) and assert the ros2_control hardware block declares the
expected plugin, joints, and command/state interfaces. We intentionally
avoid invoking xacro itself so the suite runs without a ROS install.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

URDF_PATH = (
    Path(__file__).resolve().parent.parent
    / "ros2_ws/src/biba_description/urdf/biba.urdf.xacro"
)


@pytest.fixture(scope="module")
def root() -> ET.Element:
    return ET.parse(URDF_PATH).getroot()


def _ros2_control(root: ET.Element) -> ET.Element:
    blocks = [c for c in root if c.tag.endswith("ros2_control")]
    assert len(blocks) == 1, f"expected exactly one <ros2_control>, got {len(blocks)}"
    return blocks[0]


def test_ros2_control_block_present(root: ET.Element) -> None:
    block = _ros2_control(root)
    assert block.attrib.get("type") == "system"
    assert block.attrib.get("name") == "BibaSystem"


def test_hardware_plugin_name(root: ET.Element) -> None:
    block = _ros2_control(root)
    plugin = block.find("hardware/plugin")
    assert plugin is not None
    assert plugin.text == "biba_hardware_stm32/BibaStm32SystemHardware"


def test_hardware_parameters(root: ET.Element) -> None:
    block = _ros2_control(root)
    params = {p.attrib["name"]: p.text for p in block.findall("hardware/param")}
    assert "spi_device" in params
    assert params["spi_device"] == "/dev/spidev0.0"
    assert "spi_speed_hz" in params
    assert params["spi_speed_hz"] == "1000000"
    assert "max_wheel_speed" in params
    assert "wheel_radius" in params


def test_joints_match_diff_drive_expectations(root: ET.Element) -> None:
    block = _ros2_control(root)
    joints = {j.attrib["name"]: j for j in block.findall("joint")}
    assert set(joints) == {"left_wheel_joint", "right_wheel_joint"}
    for j in joints.values():
        cmds = {c.attrib["name"] for c in j.findall("command_interface")}
        states = {s.attrib["name"] for s in j.findall("state_interface")}
        assert cmds == {"velocity"}
        assert states == {"position", "velocity"}
