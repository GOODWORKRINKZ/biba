"""Launch the twist_mux node for BiBa composition C.

Loads parameters from share/biba_bringup/config/twist_mux.yaml and
remaps the output topic `cmd_vel_out` to `/cmd_vel`, which is what
biba_stm32_bridge subscribes to.
"""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    config_path = PathJoinSubstitution(
        [FindPackageShare("biba_bringup"), "config", "twist_mux.yaml"]
    )

    config_arg = DeclareLaunchArgument(
        "config_file",
        default_value=config_path,
        description="Path to twist_mux YAML config (override for testing).",
    )

    twist_mux_node = Node(
        package="twist_mux",
        executable="twist_mux",
        name="twist_mux",
        output="screen",
        parameters=[LaunchConfiguration("config_file")],
        remappings=[("cmd_vel_out", "/cmd_vel")],
    )

    return LaunchDescription([config_arg, twist_mux_node])
