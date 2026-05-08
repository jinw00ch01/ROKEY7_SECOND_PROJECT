"""Launch the cobot_robot_control node.

The node is placed under the robot namespace (default: dsr01) so DSR_ROBOT2
can find the right ROS topics. The default config uses mock backends; pass
config:=.../robot_control.real.yaml only when real Doosan + RG2 hardware is
intentionally available.
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
            description=(
                "ROS2 parameter yaml. Defaults to mock-safe robot_control.yaml; "
                "use robot_control.real.yaml for real hardware."
            ),
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
