from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='cobot_voice',
            executable='voice_processing',
            name='voice_processing_node',
            output='screen',
        ),
        Node(
            package='cobot_voice',
            executable='command_parser',
            name='command_parser_node',
            output='screen',
        ),
        Node(
            package='cobot_voice',
            executable='firebase_state_bridge',
            name='firebase_state_bridge',
            output='screen',
        ),
        Node(
            package='cobot_safety',
            executable='safety_manager',
            name='safety_manager_node',
            output='screen',
        ),
    ])
