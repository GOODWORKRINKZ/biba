"""Structural tests for biba_description URDF/xacro.

These do not require ROS2 to be installed at runtime — we shell out to
``xacro`` only when it is available, otherwise we fall back to plain XML
parsing of the xacro source (which still validates well-formedness and
the presence of expected links/joints by name).
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


PKG_DIR = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "biba_description"
URDF_XACRO = PKG_DIR / "urdf" / "biba.urdf.xacro"
LAUNCH_FILE = PKG_DIR / "launch" / "robot_state_publisher.launch.py"


REQUIRED_LINKS = {
    "base_footprint",
    "base_link",
    "left_wheel_link",
    "right_wheel_link",
    "imu_link",
    "stm32_link",
}

REQUIRED_JOINTS = {
    ("base_footprint_to_base_link", "fixed"),
    ("left_wheel_joint", "continuous"),
    ("right_wheel_joint", "continuous"),
    ("base_to_imu", "fixed"),
    ("base_to_stm32", "fixed"),
}


def _expand_xacro(src: Path) -> ET.Element:
    """Return the parsed URDF root.

    If ``xacro`` is on PATH, expand properly. Otherwise parse the xacro
    file as XML directly — sufficient for structural assertions because
    we name links/joints with literal strings (no xacro:property in their
    names).
    """
    if shutil.which("xacro"):
        out = subprocess.check_output(["xacro", str(src)], text=True)
        return ET.fromstring(out)
    return ET.parse(src).getroot()


def test_urdf_xacro_file_exists() -> None:
    assert URDF_XACRO.is_file(), f"missing {URDF_XACRO}"


def test_robot_state_publisher_launch_exists() -> None:
    assert LAUNCH_FILE.is_file(), f"missing {LAUNCH_FILE}"


def test_urdf_parses_successfully() -> None:
    root = _expand_xacro(URDF_XACRO)
    assert root.tag.endswith("robot")
    name = root.attrib.get("name", "")
    assert name == "biba", f"expected robot name 'biba', got {name!r}"


@pytest.mark.parametrize("link_name", sorted(REQUIRED_LINKS))
def test_urdf_contains_required_link(link_name: str) -> None:
    root = _expand_xacro(URDF_XACRO)
    names = {link.attrib.get("name") for link in root.iter() if link.tag.endswith("link")}
    assert link_name in names, f"link {link_name!r} missing; have {sorted(n for n in names if n)}"


@pytest.mark.parametrize("joint_name,joint_type", sorted(REQUIRED_JOINTS))
def test_urdf_contains_required_joint(joint_name: str, joint_type: str) -> None:
    root = _expand_xacro(URDF_XACRO)
    joints = {
        j.attrib.get("name"): j.attrib.get("type")
        for j in root.iter()
        if j.tag.endswith("joint")
    }
    assert joint_name in joints, f"joint {joint_name!r} missing"
    # When xacro is not available we cannot reliably resolve joint types
    # (they can come from xacro:property), so only assert when the value
    # is concrete.
    declared = joints[joint_name]
    if declared and not declared.startswith("$"):
        assert declared == joint_type, (
            f"joint {joint_name!r} expected type {joint_type!r}, got {declared!r}"
        )
