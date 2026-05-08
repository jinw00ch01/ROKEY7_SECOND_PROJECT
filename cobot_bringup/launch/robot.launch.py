"""Robot subsystem: dsr_bringup2 + cobot_robot_control.

dsr_bringup2 is included so the Doosan TCP/IP communication is established
before our DSR_ROBOT2 wrapper imports. With `enable_dsr_bringup:=false`
(the default for mock testing) we just launch our node and skip Doosan
entirely. The default cobot_robot_control yaml uses mock backends; use
robot_control.real.yaml only with `enable_dsr_bringup:=true` and real hardware.

Launch args:
  enable_dsr_bringup        : "true"|"false"
  dsr_mode                  : virtual | real
  dsr_host                  : robot controller IP (real mode)
  dsr_port                  : robot controller port (default 12345)
  dsr_model                 : robot model (default m0609)
  dsr_namespace             : ROS2 namespace (default dsr01)
  config_robot_control      : path to cobot_robot_control yaml
                              default is mock-safe robot_control.yaml
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument("enable_dsr_bringup", default_value="false"),
        DeclareLaunchArgument("dsr_mode", default_value="virtual"),
        DeclareLaunchArgument("dsr_host", default_value="192.168.1.100"),
        DeclareLaunchArgument("dsr_port", default_value="12345"),
        DeclareLaunchArgument("dsr_model", default_value="m0609"),
        DeclareLaunchArgument("dsr_namespace", default_value="dsr01"),
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
    ]

    dsr_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("dsr_bringup2"),
                "launch",
                "dsr_bringup2_rviz.launch.py",
            ])
        ),
        launch_arguments={
            "name": LaunchConfiguration("dsr_namespace"),
            "host": LaunchConfiguration("dsr_host"),
            "port": LaunchConfiguration("dsr_port"),
            "mode": LaunchConfiguration("dsr_mode"),
            "model": LaunchConfiguration("dsr_model"),
            "gui": "false",
        }.items(),
        condition=IfCondition(LaunchConfiguration("enable_dsr_bringup")),
    )

    robot_control = Node(
        package="cobot_robot_control",
        executable="robot_control_node",
        name="robot_control_node",
        namespace=LaunchConfiguration("dsr_namespace"),
        output="screen",
        parameters=[LaunchConfiguration("config_robot_control")],
    )

    return LaunchDescription(args + [dsr_bringup, robot_control])
