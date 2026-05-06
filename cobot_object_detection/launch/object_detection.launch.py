"""Launch the cobot_object_detection node with config/object_detection.yaml."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("cobot_object_detection")
    default_config = os.path.join(pkg_share, "config", "object_detection.yaml")

    config_arg = DeclareLaunchArgument(
        "config",
        default_value=default_config,
        description="Path to ROS2 parameter yaml for object_detection_node.",
    )

    node = Node(
        package="cobot_object_detection",
        executable="object_detection_node",
        name="object_detection_node",
        output="screen",
        parameters=[LaunchConfiguration("config")],
    )

    return LaunchDescription([config_arg, node])
