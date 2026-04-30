from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='cobot_policy',
            executable='policy_selector',
            name='policy_selector_node',
            output='screen',
        ),
        Node(
            package='cobot_task_manager',
            executable='task_manager',
            name='task_manager_node',
            output='screen',
        ),
        Node(
            package='cobot_robot_control',
            executable='robot_control',
            name='robot_control_node',
            output='screen',
        ),
    ])
