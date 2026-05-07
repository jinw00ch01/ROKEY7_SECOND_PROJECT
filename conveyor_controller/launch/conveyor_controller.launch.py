import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = get_package_share_directory('conveyor_controller')
    default_config = os.path.join(
        package_share,
        'config',
        'conveyor_controller.yaml',
    )

    config_file = LaunchConfiguration('config_file')
    port = LaunchConfiguration('port')
    baudrate = LaunchConfiguration('baudrate')
    command_topic = LaunchConfiguration('command_topic')

    return LaunchDescription([
        DeclareLaunchArgument(
            'config_file',
            default_value=default_config,
            description='Path to conveyor controller parameter YAML file',
        ),
        DeclareLaunchArgument(
            'port',
            default_value='/dev/ttyACM0',
            description='Arduino UNO USB serial device path',
        ),
        DeclareLaunchArgument(
            'baudrate',
            default_value='115200',
            description='Arduino serial baudrate',
        ),
        DeclareLaunchArgument(
            'command_topic',
            default_value='/conveyor_cmd',
            description='ROS topic used for conveyor commands',
        ),
        Node(
            package='conveyor_controller',
            executable='conveyor_serial_node',
            name='conveyor_serial_node',
            output='screen',
            parameters=[
                config_file,
                {
                    'port': port,
                    'baudrate': ParameterValue(baudrate, value_type=int),
                    'command_topic': command_topic,
                },
            ],
        ),
    ])
