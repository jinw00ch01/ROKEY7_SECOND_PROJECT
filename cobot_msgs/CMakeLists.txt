cmake_minimum_required(VERSION 3.8)
project(cobot_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/RobotCommand.msg"
  "msg/Policy.msg"
  "msg/DetectedObject.msg"
  "msg/DetectedObjectArray.msg"
  "msg/ObjectPose.msg"
  "msg/ObjectPoseArray.msg"
  "action/PickAndPlace.action"
  DEPENDENCIES std_msgs geometry_msgs
)

ament_package()
