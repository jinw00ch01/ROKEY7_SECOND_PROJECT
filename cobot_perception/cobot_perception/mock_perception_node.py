# 한국어 요약:
#   가상 e2e 테스트용 mock perception 노드.
#   /perception/detect_once 호출 시 base 프레임으로 이미 변환된 8개의 너트
#   detection(4 클래스 x 2 인스턴스)을 항상 반환한다.
#   클래스별로 OBB 면적이 다른 두 인스턴스를 두어 target_selector가 큰 것을
#   먼저 고르는 동작을 검증할 수 있다. RealSense / DSR_ROBOT2 없이 task_manager
#   루프 전체를 시연 가능하도록 transform_valid=True로 발행한다.
"""Mock perception node for virtual e2e testing.

Provides /perception/detect_once with a hardcoded scene of 8 nut detections
(4 classes x 2 instances) already transformed to the robot base frame.
Use with cobot_robot_control's mock backends to exercise the full
task_manager loop without RealSense or DSR_ROBOT2.

Design:
- Always returns the full 8-object scene, transform_valid=true.
- Two instances per class differ in OBB area so target_selector can prove
  it's picking the larger one first.
- A small per-call counter is logged so it's easy to count detection
  cycles in the captured log.
"""

from __future__ import annotations

import math
from typing import List, Optional

import rclpy
from rclpy.node import Node

from cobot_msgs.msg import DetectedObject, DetectedObjectArray
from cobot_msgs.srv import DetectOnce


def _make_object(
    class_name: str,
    base_x: float,
    base_y: float,
    base_z: float,
    width: float,
    height: float,
    confidence: float,
    grasp_yaw: float = 0.0,
    short_axis_mm: float = 12.0,
    long_axis_mm: float = 18.0,
) -> DetectedObject:
    obj = DetectedObject()
    obj.class_name = class_name
    obj.confidence = float(confidence)
    obj.cx = 320.0
    obj.cy = 240.0
    obj.width = float(width)
    obj.height = float(height)
    obj.theta = 0.0
    obj.camera_xyz.x = 0.0
    obj.camera_xyz.y = 0.0
    obj.camera_xyz.z = float(base_z)
    obj.base_xyz.x = float(base_x)
    obj.base_xyz.y = float(base_y)
    obj.base_xyz.z = float(base_z)
    obj.grasp_yaw = float(grasp_yaw)
    obj.short_axis_mm = float(short_axis_mm)
    obj.long_axis_mm = float(long_axis_mm)
    obj.transform_valid = True
    return obj


def _build_scene() -> List[DetectedObject]:
    # 4 classes x 2 instances, inside the active workspace box defined
    # in cobot_task_manager/config/task_manager.yaml. The z gate was
    # tightened to the observed nut-top range (40..80 mm) for real-
    # hardware safety; mock z must mirror that or the target_selector
    # filters every detection. Different OBB areas so target_selector
    # prefers the larger instance.
    return [
        _make_object("almond",    base_x=350.0, base_y=-50.0, base_z=63.0, width=50.0, height=40.0, confidence=0.95),
        _make_object("almond",    base_x=350.0, base_y= 50.0, base_z=63.0, width=45.0, height=35.0, confidence=0.92),
        _make_object("cashew",    base_x=400.0, base_y=-50.0, base_z=63.0, width=55.0, height=40.0, confidence=0.96, grasp_yaw=math.radians(15)),
        _make_object("cashew",    base_x=400.0, base_y= 50.0, base_z=63.0, width=50.0, height=38.0, confidence=0.93, grasp_yaw=math.radians(20)),
        _make_object("pistachio", base_x=450.0, base_y=-50.0, base_z=63.0, width=45.0, height=40.0, confidence=0.94),
        _make_object("pistachio", base_x=450.0, base_y= 50.0, base_z=63.0, width=42.0, height=35.0, confidence=0.91),
        _make_object("walnut",    base_x=500.0, base_y=-50.0, base_z=63.0, width=60.0, height=50.0, confidence=0.97, grasp_yaw=math.radians(-10)),
        _make_object("walnut",    base_x=500.0, base_y= 50.0, base_z=63.0, width=55.0, height=45.0, confidence=0.93, grasp_yaw=math.radians(-5)),
    ]


class MockPerceptionNode(Node):
    def __init__(self) -> None:
        super().__init__("mock_perception_node")
        self.declare_parameter("service_name", "/perception/detect_once")
        self._scene = _build_scene()
        self._call_count = 0

        service_name = str(self.get_parameter("service_name").value)
        self._service = self.create_service(
            DetectOnce, service_name, self._handle_detect_once
        )
        self.get_logger().info(
            f"mock_perception_node ready ({service_name}, "
            f"{len(self._scene)} fake detections)"
        )

    def _handle_detect_once(self, _request, response):
        # 호출 횟수를 로그에 남겨 캡처된 로그에서 detection cycle을 셀 수 있도록 한다.
        self._call_count += 1
        out = DetectedObjectArray()
        out.header.frame_id = "camera_color_optical_frame"
        for obj in self._scene:
            # publish a fresh copy each time so consumers cannot mutate
            # internal state by accident.
            out.objects.append(_clone(obj))
        response.objects = out
        response.success = True
        response.message = f"mock cycle #{self._call_count}: {len(self._scene)} objects"
        self.get_logger().info(response.message)
        return response


def _clone(obj: DetectedObject) -> DetectedObject:
    return _make_object(
        class_name=obj.class_name,
        base_x=obj.base_xyz.x,
        base_y=obj.base_xyz.y,
        base_z=obj.base_xyz.z,
        width=obj.width,
        height=obj.height,
        confidence=obj.confidence,
        grasp_yaw=obj.grasp_yaw,
        short_axis_mm=obj.short_axis_mm,
        long_axis_mm=obj.long_axis_mm,
    )


def main(args=None) -> None:
    rclpy.init(args=args)
    node: Optional[MockPerceptionNode] = None
    try:
        node = MockPerceptionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
