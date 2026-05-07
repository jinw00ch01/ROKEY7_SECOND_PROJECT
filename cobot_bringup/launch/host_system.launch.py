"""Host-side application stack: cobot_task_manager (and future cobot_safety).

Phase A: only task_manager_node. cobot_safety is added later (Phase A' entry).
cobot_voice / cobot_policy are out of scope for this scenario.

Launch args:
  config_task_manager       : path to cobot_task_manager yaml
  task_autostart            : "true"|"false". Set false to start the node
                              with its worker idle so a tester can trigger it
                              via /task/start.
  order_source              : "mock"|"db"|"file". Overrides yaml. Set "file"
                              to read cobot_voice's latest_order.json.
  file_order_path           : Absolute path to latest_order.json. Required
                              when order_source=file. Empty string means
                              the yaml's value is used.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    tm_share = get_package_share_directory("cobot_task_manager")

    args = [
        DeclareLaunchArgument(
            "config_task_manager",
            default_value=os.path.join(tm_share, "config", "task_manager.yaml"),
        ),
        DeclareLaunchArgument("task_autostart", default_value="true"),
        DeclareLaunchArgument(
            "order_source",
            default_value="mock",
            description="mock | db | file. Default mock.",
        ),
        DeclareLaunchArgument(
            "file_order_path",
            default_value="",
            description="Absolute path to latest_order.json. Required when order_source=file.",
        ),
    ]

    task_manager = Node(
        package="cobot_task_manager",
        executable="task_manager_node",
        name="task_manager_node",
        output="screen",
        parameters=[
            LaunchConfiguration("config_task_manager"),
            {
                "autostart": LaunchConfiguration("task_autostart"),
                "order_source": LaunchConfiguration("order_source"),
                "file_order_path": LaunchConfiguration("file_order_path"),
            },
        ],
    )

    return LaunchDescription(args + [task_manager])
