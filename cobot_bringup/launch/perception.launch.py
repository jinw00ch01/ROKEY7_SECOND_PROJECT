"""Perception subsystem: RealSense + YOLO-OBB + transform node.

Topics published (defaults):
  /camera/camera/color/image_raw
  /camera/camera/aligned_depth_to_color/image_raw
  /camera/camera/color/camera_info
  /detection/objects                 (cobot_msgs/DetectedObjectArray)
Service:
  /perception/detect_once            (cobot_msgs/srv/DetectOnce)

Launch args:
  enable_realsense          : "true"|"false". Set false to feed detections
                              from a rosbag or another source.
  config_object_detection   : path to cobot_object_detection yaml
  config_perception         : path to cobot_perception yaml
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
        DeclareLaunchArgument("enable_realsense", default_value="true"),
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
    ]

    realsense = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("realsense2_camera"),
                "launch",
                "rs_launch.py",
            ])
        ),
        # Profiles + flags chosen to match the bootcamp course command:
        #   ros2 launch realsense2_camera rs_align_depth_launch.py
        #     depth_module.depth_profile:=848x480x30
        #     rgb_camera.color_profile:=1280x720x30
        #     initial_reset:=true align_depth.enable:=true
        #     enable_rgbd:=true pointcloud.enable:=true
        # rs_align_depth_launch.py is not present in our realsense2_camera
        # install (newer version), so we forward the same args to rs_launch.py.
        launch_arguments={
            "enable_color": "true",
            "enable_depth": "true",
            "rgb_camera.color_profile": "1280x720x30",
            "depth_module.depth_profile": "848x480x30",
            "initial_reset": "true",
            "align_depth.enable": "true",
            "enable_rgbd": "true",
            "pointcloud.enable": "true",
        }.items(),
        condition=IfCondition(LaunchConfiguration("enable_realsense")),
    )

    # NOTE: object_detection_node는 더 이상 launch에 포함하지 않는다.
    # perception_transform_node가 trigger 시점에만 직접 YOLO 추론을 수행하도록
    # 통합되어 stream cache의 frame-TCP 미스매치를 제거했다. 디버깅용으로 별도
    # 실행하고 싶다면 `ros2 run cobot_object_detection object_detection_node`로
    # 수동 기동 가능 (config_object_detection arg는 호환을 위해 남겨둠).

    perception_transform = Node(
        package="cobot_perception",
        executable="perception_transform_node",
        name="perception_transform_node",
        output="screen",
        parameters=[LaunchConfiguration("config_perception")],
    )

    return LaunchDescription(args + [realsense, perception_transform])
