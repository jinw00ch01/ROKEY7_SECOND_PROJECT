"""Compose perception + robot + host_system into one launch.

All toggles flow down to the sub-launches via launch_arguments. Examples:

# Phase A virtual+mock e2e (no hardware)
  ros2 launch cobot_bringup full_system.launch.py \\
      enable_realsense:=false enable_dsr_bringup:=false task_autostart:=false

# Phase A' real-mode entry (with both hardware)
  ros2 launch cobot_bringup full_system.launch.py \\
      enable_realsense:=true enable_dsr_bringup:=true \\
      dsr_mode:=real dsr_host:=192.168.137.100 \\
      config_robot_control:=<share>/cobot_robot_control/config/robot_control.real.yaml
  #   cobot_perception:    tcp_source=service (once implemented)
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    pass_args = [
        # perception
        "enable_realsense",
        "config_object_detection",
        "config_perception",
        # robot
        "enable_dsr_bringup",
        "dsr_mode",
        "dsr_host",
        "dsr_port",
        "dsr_model",
        "dsr_namespace",
        "config_robot_control",
        # host
        "config_task_manager",
        "task_autostart",
        "order_source",
        "file_order_path",
        "enable_firebase_status_bridge",
    ]

    args = [
        DeclareLaunchArgument("enable_realsense", default_value="true"),
        DeclareLaunchArgument("enable_dsr_bringup", default_value="false"),
        DeclareLaunchArgument("dsr_mode", default_value="virtual"),
        DeclareLaunchArgument("dsr_host", default_value="192.168.1.100"),
        DeclareLaunchArgument("dsr_port", default_value="12345"),
        DeclareLaunchArgument("dsr_model", default_value="m0609"),
        DeclareLaunchArgument("dsr_namespace", default_value="dsr01"),
        DeclareLaunchArgument("task_autostart", default_value="true"),
        DeclareLaunchArgument(
            "order_source",
            default_value="mock",
            description="task_manager order source: mock | db | file",
        ),
        DeclareLaunchArgument(
            "file_order_path",
            default_value="",
            description="Absolute path to latest_order.json (when order_source=file)",
        ),
        DeclareLaunchArgument(
            "enable_firebase_status_bridge",
            default_value="true",
            description=(
                "Run firebase_status_bridge to mirror robot pipeline state to "
                "Firestore /robot_session/current.robot_state for the web UI. "
                "Set false to skip; no-ops anyway if Firebase creds missing."
            ),
        ),
        DeclareLaunchArgument(
            "config_object_detection",
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare("cobot_object_detection"),
                    "config",
                    "object_detection.yaml",
                ]
            ),
        ),
        DeclareLaunchArgument(
            "config_perception",
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare("cobot_perception"),
                    "config",
                    "perception.yaml",
                ]
            ),
        ),
        DeclareLaunchArgument(
            "config_robot_control",
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare("cobot_robot_control"),
                    "config",
                    "robot_control.yaml",
                ]
            ),
        ),
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
    ]

    def forward(name: str) -> tuple:
        return (name, LaunchConfiguration(name))

    perception = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("cobot_bringup"), "launch", "perception.launch.py"]
            )
        ),
        launch_arguments=[
            forward("enable_realsense"),
            forward("config_object_detection"),
            forward("config_perception"),
        ],
    )

    robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("cobot_bringup"), "launch", "robot.launch.py"]
            )
        ),
        launch_arguments=[
            forward("enable_dsr_bringup"),
            forward("dsr_mode"),
            forward("dsr_host"),
            forward("dsr_port"),
            forward("dsr_model"),
            forward("dsr_namespace"),
            forward("config_robot_control"),
        ],
    )

    host = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("cobot_bringup"), "launch", "host_system.launch.py"]
            )
        ),
        launch_arguments=[
            forward("config_task_manager"),
            forward("task_autostart"),
            forward("order_source"),
            forward("file_order_path"),
            forward("enable_firebase_status_bridge"),
        ],
    )

    return LaunchDescription(args + [perception, robot, host])
