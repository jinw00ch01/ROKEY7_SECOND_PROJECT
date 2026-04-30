from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='cobot_perception',
            executable='perception_transform',
            name='perception_transform_node',
            output='screen',
        ),
    ])
