"""Launch ros2_control + diff_drive_controller for BiBa composition C.

This is the composition-C replacement for the Python biba_stm32_bridge:
the C++ hardware plugin (biba_hardware_stm32::BibaStm32SystemHardware)
becomes the sole owner of /dev/spidev0.0, and diff_drive_controller
drives /cmd_vel directly through it.

Stack started by this launch:
  - robot_state_publisher (URDF -> /robot_description, TF)
  - controller_manager (ros2_control_node) loaded with the URDF + the
    diff_drive_controller.yaml controller config
  - joint_state_broadcaster spawner
  - diff_drive_controller spawner

The actual /cmd_vel arbitration is handled separately by twist_mux
(twist_mux.launch.py); this file assumes /cmd_vel is already produced.
"""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    description_pkg = FindPackageShare("biba_description")
    bringup_pkg = FindPackageShare("biba_bringup")

    urdf_path = PathJoinSubstitution(
        [description_pkg, "urdf", "biba.urdf.xacro"]
    )
    controllers_path = PathJoinSubstitution(
        [bringup_pkg, "config", "diff_drive_controller.yaml"]
    )

    use_sim_time_arg = DeclareLaunchArgument(
        "use_sim_time", default_value="false"
    )
    use_sim_time = LaunchConfiguration("use_sim_time")

    robot_description_content = Command(
        [FindExecutable(name="xacro"), " ", urdf_path]
    )
    robot_description = {"robot_description": robot_description_content}

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[robot_description, {"use_sim_time": use_sim_time}],
    )

    controller_manager = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_description, controllers_path],
        output="screen",
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "--controller-manager",
                   "/controller_manager"],
        output="screen",
    )

    diff_drive_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["diff_drive_controller", "--controller-manager",
                   "/controller_manager"],
        output="screen",
    )

    # Ensure joint_state_broadcaster is up before spawning the diff drive
    # controller so that the URDF state interfaces are claimed in order.
    delay_diff_drive = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[diff_drive_spawner],
        )
    )

    return LaunchDescription([
        use_sim_time_arg,
        robot_state_publisher,
        controller_manager,
        joint_state_broadcaster_spawner,
        delay_diff_drive,
    ])
