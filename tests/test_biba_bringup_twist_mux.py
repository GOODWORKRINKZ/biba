"""Structural tests for biba_bringup twist_mux config and launch.

We don't run ROS2 in pytest (heavy + needs rclpy). Instead these tests
pin the public contract — topic names, priorities, output topic — so
silent regressions are caught on CI without a colcon build.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import yaml


PKG = Path("ros2_ws/src/biba_bringup")
CONFIG = PKG / "config" / "twist_mux.yaml"
LAUNCH = PKG / "launch" / "twist_mux.launch.py"


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_config_file_exists() -> None:
    assert CONFIG.is_file(), f"missing {CONFIG}"


def test_config_uses_twist_mux_node_namespace(cfg: dict) -> None:
    # twist_mux loads parameters under /twist_mux/ros__parameters; YAML
    # must follow that exact shape.
    assert "twist_mux" in cfg
    assert "ros__parameters" in cfg["twist_mux"]


def test_config_declares_expected_topic_inputs(cfg: dict) -> None:
    params = cfg["twist_mux"]["ros__parameters"]
    assert "topics" in params
    names = set(params["topics"].keys())
    # CRSF is enforced on STM32 directly, so SBC twist_mux arbitrates
    # only SBC-side sources. Names mirror docs/plans.
    assert {"teleop", "uwb_follow", "autonomy"} <= names


def test_config_priorities_are_strictly_ordered(cfg: dict) -> None:
    topics = cfg["twist_mux"]["ros__parameters"]["topics"]
    # Higher priority wins. Operator teleop must outrank autonomy.
    assert topics["teleop"]["priority"] > topics["uwb_follow"]["priority"]
    assert topics["uwb_follow"]["priority"] > topics["autonomy"]["priority"]


def test_config_topics_have_required_fields(cfg: dict) -> None:
    topics = cfg["twist_mux"]["ros__parameters"]["topics"]
    for name, spec in topics.items():
        assert "topic" in spec, f"{name} missing 'topic'"
        assert "timeout" in spec, f"{name} missing 'timeout'"
        assert "priority" in spec, f"{name} missing 'priority'"
        # Sanity: timeouts measured in seconds, must be small but
        # non-zero so a stalled publisher releases the lock.
        assert 0.0 < float(spec["timeout"]) <= 2.0


def test_config_has_estop_lock(cfg: dict) -> None:
    params = cfg["twist_mux"]["ros__parameters"]
    assert "locks" in params
    locks = params["locks"]
    assert "estop" in locks
    # E-stop priority must outrank every twist input.
    topics = params["topics"]
    max_topic_priority = max(t["priority"] for t in topics.values())
    assert locks["estop"]["priority"] > max_topic_priority


def test_launch_file_exists_and_loads_config() -> None:
    assert LAUNCH.is_file(), f"missing {LAUNCH}"
    text = LAUNCH.read_text(encoding="utf-8")
    # The launch must reference both the package and the config file by
    # name so package install respects share/biba_bringup/config/.
    assert "biba_bringup" in text
    assert "twist_mux.yaml" in text
    # Output must remap to /cmd_vel which biba_stm32_bridge subscribes to.
    assert "cmd_vel_out" in text and "cmd_vel" in text


def test_cmake_installs_config_directory() -> None:
    cmake = (PKG / "CMakeLists.txt").read_text(encoding="utf-8")
    # Both launch and config dirs must be installed to the package share.
    assert "DIRECTORY launch config" in cmake or (
        "DIRECTORY config" in cmake and "DIRECTORY launch" in cmake
    )


def test_package_xml_declares_twist_mux_dep() -> None:
    pkg_xml = (PKG / "package.xml").read_text(encoding="utf-8")
    assert "<exec_depend>twist_mux</exec_depend>" in pkg_xml
