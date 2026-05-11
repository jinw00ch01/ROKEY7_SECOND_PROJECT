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

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument(
            "config_task_manager",
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare("cobot_task_manager"),
                    "config",
                    "task_manager.yaml",
                ]
            ),
        ),
        DeclareLaunchArgument("task_autostart", default_value="true"),
        DeclareLaunchArgument(
            "order_source",
            default_value="mock",
            description="mock | db | file | firestore | supabase. Default mock.",
        ),
        DeclareLaunchArgument(
            "file_order_path",
            default_value="",
            description="Absolute path to latest_order.json. Required when order_source=file.",
        ),
        DeclareLaunchArgument(
            "enable_firebase_status_bridge",
            default_value="false",
            description=(
                "Legacy Firestore status bridge. Default false after the "
                "Supabase migration; set true only if you've kept the web "
                "app on Firestore."
            ),
        ),
        DeclareLaunchArgument(
            "enable_supabase_status_bridge",
            default_value="true",
            description=(
                "Run cobot_voice supabase_status_bridge alongside task_manager. "
                "Mirrors /task/status, /task/result, /conveyor/place_ready into "
                "robot_session.current.robot_state for the web UI. No-ops when "
                "cobot_db / SUPABASE_KEY are missing; never blocks the robot."
            ),
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

    firebase_status_bridge = Node(
        package="cobot_voice",
        executable="firebase_status_bridge",
        name="firebase_status_bridge",
        output="screen",
        condition=IfCondition(LaunchConfiguration("enable_firebase_status_bridge")),
    )

    supabase_status_bridge = Node(
        package="cobot_voice",
        executable="supabase_status_bridge",
        name="supabase_status_bridge",
        output="screen",
        condition=IfCondition(LaunchConfiguration("enable_supabase_status_bridge")),
    )

    return LaunchDescription(
        args + [task_manager, firebase_status_bridge, supabase_status_bridge]
    )
