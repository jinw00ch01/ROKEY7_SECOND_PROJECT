"""Robot subsystem: dsr_bringup2 + cobot_robot_control.

dsr_bringup2 is included so the Doosan TCP/IP communication is established
before our DSR_ROBOT2 wrapper imports. With `enable_dsr_bringup:=false`
(the default for mock testing) we just launch our node and skip Doosan
entirely; the cobot_robot_control yaml should set `motion_backend: mock`.

Launch args:
  enable_dsr_bringup        : "true"|"false"
  dsr_mode                  : virtual | real
  dsr_host                  : robot controller IP (real mode)
  dsr_port                  : robot controller port (default 12345)
  dsr_model                 : robot model (default m0609)
  dsr_namespace             : ROS2 namespace (default dsr01)
  config_robot_control      : path to cobot_robot_control yaml
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    rc_share = get_package_share_directory("cobot_robot_control")
    dsr_share = get_package_share_directory("dsr_bringup2")

    args = [
        DeclareLaunchArgument("enable_dsr_bringup", default_value="false"),
        DeclareLaunchArgument("dsr_mode", default_value="virtual"),
        DeclareLaunchArgument("dsr_host", default_value="192.168.1.100"),
        DeclareLaunchArgument("dsr_port", default_value="12345"),
        DeclareLaunchArgument("dsr_model", default_value="m0609"),
        DeclareLaunchArgument("dsr_namespace", default_value="dsr01"),
        DeclareLaunchArgument(
            "config_robot_control",
            default_value=os.path.join(rc_share, "config", "robot_control.yaml"),
        ),
    ]

    dsr_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(dsr_share, "launch", "dsr_bringup2_rviz.launch.py")
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
