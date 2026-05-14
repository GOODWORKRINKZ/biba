"""Launch file for robot_state_publisher fed by the biba xacro.

Usage:
    ros2 launch biba_description robot_state_publisher.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    use_sim_time = LaunchConfiguration("use_sim_time")
    xacro_path = PathJoinSubstitution(
        [FindPackageShare("biba_description"), "urdf", "biba.urdf.xacro"]
    )
    robot_description = {
        "robot_description": Command([FindExecutable(name="xacro"), " ", xacro_path]),
        "use_sim_time": use_sim_time,
    }

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="false",
                description="Use simulation (Gazebo) clock if true",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                output="screen",
                parameters=[robot_description],
            ),
        ]
    )
