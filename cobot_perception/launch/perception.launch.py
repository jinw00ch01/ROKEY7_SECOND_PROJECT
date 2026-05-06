"""Launch the cobot_perception transform node with config/perception.yaml."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("cobot_perception")
    default_config = os.path.join(pkg_share, "config", "perception.yaml")

    config_arg = DeclareLaunchArgument(
        "config",
        default_value=default_config,
        description="Path to ROS2 parameter yaml for perception_transform_node.",
    )

    node = Node(
        package="cobot_perception",
        executable="perception_transform_node",
        name="perception_transform_node",
        output="screen",
        parameters=[LaunchConfiguration("config")],
    )

    return LaunchDescription([config_arg, node])
