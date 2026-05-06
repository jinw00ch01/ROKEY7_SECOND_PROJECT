"""Launch the cobot_robot_control node.

The node is placed under the robot namespace (default: dsr01) so DSR_ROBOT2
can find the right ROS topics. Override `namespace` to match your robot.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("cobot_robot_control")
    default_config = os.path.join(pkg_share, "config", "robot_control.yaml")

    args = [
        DeclareLaunchArgument(
            "config",
            default_value=default_config,
            description="ROS2 parameter yaml.",
        ),
        DeclareLaunchArgument(
            "namespace",
            default_value="dsr01",
            description="ROS2 namespace (must match robot_id).",
        ),
    ]

    node = Node(
        package="cobot_robot_control",
        executable="robot_control_node",
        name="robot_control_node",
        namespace=LaunchConfiguration("namespace"),
        output="screen",
        parameters=[LaunchConfiguration("config")],
    )

    return LaunchDescription(args + [node])
