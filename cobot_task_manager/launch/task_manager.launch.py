"""Launch the cobot_task_manager node with config/task_manager.yaml."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("cobot_task_manager")
    default_config = os.path.join(pkg_share, "config", "task_manager.yaml")

    config_arg = DeclareLaunchArgument(
        "config",
        default_value=default_config,
        description="ROS2 parameter yaml.",
    )

    node = Node(
        package="cobot_task_manager",
        executable="task_manager_node",
        name="task_manager_node",
        output="screen",
        parameters=[LaunchConfiguration("config")],
    )

    return LaunchDescription([config_arg, node])
