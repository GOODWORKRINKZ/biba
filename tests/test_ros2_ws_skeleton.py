"""Structural smoke tests for the ros2_ws/ skeleton (composition C)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WS = REPO_ROOT / "ros2_ws"
SRC = WS / "src"

CORE_PACKAGES = [
    "biba_description",
    "biba_msgs",
    "biba_stm32_bridge",
    "biba_hardware_stm32",
    "biba_bringup",
]

HOOK_POINTS = [
    "biba_manipulator",
    "biba_uwb_follow",
    "biba_remote_bridge",
    "biba_camera",
    "biba_autonomy",
]


def test_workspace_root_exists() -> None:
    assert WS.is_dir(), "ros2_ws/ must exist"
    assert SRC.is_dir(), "ros2_ws/src/ must exist"
    assert (WS / ".gitignore").is_file()
    assert (WS / "README.md").is_file()


@pytest.mark.parametrize("pkg", CORE_PACKAGES)
def test_core_package_has_package_xml(pkg: str) -> None:
    pkg_dir = SRC / pkg
    assert pkg_dir.is_dir(), f"{pkg} directory must exist"
    package_xml = pkg_dir / "package.xml"
    assert package_xml.is_file(), f"{pkg}/package.xml must exist"
    text = package_xml.read_text(encoding="utf-8")
    assert f"<name>{pkg}</name>" in text


def test_biba_msgs_has_msg_files() -> None:
    msg_dir = SRC / "biba_msgs" / "msg"
    assert msg_dir.is_dir()
    expected = {"CrsfStatus.msg", "Stm32Telemetry.msg", "MotorAudio.msg"}
    actual = {p.name for p in msg_dir.glob("*.msg")}
    assert expected <= actual, f"missing: {expected - actual}"


def test_biba_stm32_bridge_is_ament_python() -> None:
    pkg_dir = SRC / "biba_stm32_bridge"
    assert (pkg_dir / "setup.py").is_file()
    assert (pkg_dir / "setup.cfg").is_file()
    assert (pkg_dir / "biba_stm32_bridge" / "__init__.py").is_file()
    assert (pkg_dir / "resource" / "biba_stm32_bridge").is_file()


def test_biba_hardware_stm32_is_cmake() -> None:
    pkg_dir = SRC / "biba_hardware_stm32"
    cmake = pkg_dir / "CMakeLists.txt"
    assert cmake.is_file()
    assert "biba_hardware_stm32" in cmake.read_text(encoding="utf-8")


def test_biba_bringup_has_launch_dir() -> None:
    assert (SRC / "biba_bringup" / "launch").is_dir()


@pytest.mark.parametrize("hook", HOOK_POINTS)
def test_hook_point_is_colcon_ignored(hook: str) -> None:
    hook_dir = SRC / hook
    assert hook_dir.is_dir(), f"{hook} hook-point directory must exist"
    assert (hook_dir / "COLCON_IGNORE").is_file(), (
        f"{hook}/COLCON_IGNORE must exist so colcon skips empty hook-points"
    )
    assert (hook_dir / "README.md").is_file(), (
        f"{hook}/README.md must explain the future package"
    )
