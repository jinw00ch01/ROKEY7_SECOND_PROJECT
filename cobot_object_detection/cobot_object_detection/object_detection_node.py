# 한국어 요약:
#   RealSense color 스트림 위에서 YOLOv8-OBB 너트 검출을 수행하는 ROS2 노드.
#   color 토픽을 구독해 OBB 추론 후 단기 윈도우 융합으로 안정화하여
#   /detection/objects (cobot_msgs/DetectedObjectArray)에 발행한다.
#   깊이 lookup, hand-eye 변환, grasp_yaw 계산은 cobot_perception이 담당하므로
#   transform_valid는 항상 false로 채워 보낸다.
"""ROS2 node: YOLOv8-OBB nut detection over a RealSense color stream.

Subscribes to a color image topic and publishes fused 2D OBB detections on
`/detection/objects` (cobot_msgs/DetectedObjectArray). Downstream
`cobot_perception` is responsible for depth lookup, hand-eye transform,
and grasp_yaw computation.

`transform_valid` is left false on every published entry so the perception
node knows it must populate camera_xyz, base_xyz, and grasp_yaw.
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Image
from cv_bridge import CvBridge

from cobot_msgs.msg import DetectedObject, DetectedObjectArray

from .yolo_detector import YoloObbDetector
from .detection_postprocess import DetectionAggregator
from .model_paths import resolve_model_path


class ObjectDetectionNode(Node):
    def __init__(self) -> None:
        super().__init__("object_detection_node")

        # 추론 모델 / 임계값 — yaml·launch 에서 조정. 'device' 는 빈 문자열일 때
        # ultralytics 가 CUDA/CPU 를 자동 선택하도록 아래에서 None 으로 변환된다.
        self.declare_parameter("model_path", "")
        self.declare_parameter(
            "class_names",
            ["almond", "cashew", "pistachio", "walnut"],
        )
        self.declare_parameter("imgsz", 800)
        self.declare_parameter("conf_threshold", 0.40)
        self.declare_parameter("iou_threshold", 0.50)
        self.declare_parameter("device", "")
        # 단기 윈도우 융합 파라미터 — window_sec 동안 cluster 거리(px) 안에 들어오는
        # 같은 클래스 검출을 묶어 평균을 publish, 한 프레임짜리 깜빡임을 억제한다.
        self.declare_parameter("multi_frame_window_sec", 0.5)
        self.declare_parameter("cluster_distance_threshold_px", 30.0)
        # I/O 토픽 + 빈 결과 publish 정책. publish_when_empty=False 면
        # downstream(detect_once 서비스)이 latched 캐시에 의존할 수 있으므로 주의.
        self.declare_parameter("color_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("output_topic", "/detection/objects")
        self.declare_parameter("publish_when_empty", True)

        model_path = resolve_model_path(self.get_parameter("model_path").value)
        class_names = list(self.get_parameter("class_names").value)
        imgsz = int(self.get_parameter("imgsz").value)
        conf = float(self.get_parameter("conf_threshold").value)
        iou = float(self.get_parameter("iou_threshold").value)
        device_param = self.get_parameter("device").value
        # 빈 문자열은 ultralytics 의 자동 디바이스 선택을 의미하므로 None 으로 정규화.
        device = device_param if device_param else None

        window_sec = float(self.get_parameter("multi_frame_window_sec").value)
        cluster_dist = float(
            self.get_parameter("cluster_distance_threshold_px").value
        )
        color_topic = self.get_parameter("color_topic").value
        output_topic = self.get_parameter("output_topic").value
        self._publish_when_empty = bool(
            self.get_parameter("publish_when_empty").value
        )

        self.get_logger().info(
            f"Loading YOLO-OBB model: {model_path} (imgsz={imgsz}, conf={conf}, iou={iou})"
        )
        self._detector = YoloObbDetector(
            model_path=model_path,
            class_names=class_names,
            imgsz=imgsz,
            conf_threshold=conf,
            iou_threshold=iou,
            device=device,
        )
        self._aggregator = DetectionAggregator(
            window_sec=window_sec,
            cluster_distance_px=cluster_dist,
        )
        self._bridge = CvBridge()

        # 카메라 스트림은 최신성 우선이므로 BEST_EFFORT + KEEP_LAST=2로 큐를 최소화.
        # 추론이 늦어져도 오래된 프레임이 쌓이지 않게 하여 latency를 일정하게 유지한다.
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=2,
        )
        self._publisher = self.create_publisher(
            DetectedObjectArray, output_topic, 10
        )
        self._color_sub = self.create_subscription(
            Image, color_topic, self._on_color, sensor_qos
        )

        # color image msg.header.frame_id 가 비어 들어올 때만 사용하는 폴백.
        # RealSense2 driver 는 보통 'camera_color_optical_frame' 을 채워 보낸다.
        self._frame_id = "camera_color_optical_frame"
        self._processing = False
        self.get_logger().info(
            f"Subscribed to {color_topic}, publishing on {output_topic}"
        )

    def _on_color(self, msg: Image) -> None:
        # 추론은 프레임 주기보다 느릴 수 있으므로 _processing 플래그로 backpressure를
        # 적용하여 콜백 중첩과 큐 적체를 방지한다.
        if self._processing:
            return
        self._processing = True
        try:
            try:
                frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            except Exception as exc:
                self.get_logger().warn(f"cv_bridge failed: {exc}")
                return

            t_inf_start = time.time()
            detections = self._detector.infer(frame)
            t_inf = time.time() - t_inf_start

            # add() 로 윈도우에 누적하고 fuse() 가 만료된 항목을 제거한 뒤
            # 같은 클래스/근접 픽셀 검출을 클러스터링한 평균 OBB 를 돌려준다.
            now = time.time()
            self._aggregator.add(detections, now)
            fused = self._aggregator.fuse()

            if not fused and not self._publish_when_empty:
                return

            out = DetectedObjectArray()
            # 카메라 원본 stamp/frame_id 를 그대로 전달 — perception 측에서 같은
            # 프레임의 align_depth 와 TF 를 시점 기준으로 매칭할 때 필요하다.
            # now() 로 덮어쓰면 perception 깊이 lookup 의 stale 검사가 어긋난다.
            out.header.stamp = msg.header.stamp
            out.header.frame_id = msg.header.frame_id or self._frame_id

            for d in fused:
                obj = DetectedObject()
                obj.class_name = d.class_name
                obj.confidence = float(d.confidence)
                obj.cx = float(d.cx)
                obj.cy = float(d.cy)
                obj.width = float(d.width)
                obj.height = float(d.height)
                obj.theta = float(d.theta)
                # camera_xyz / base_xyz / grasp_yaw left zero on initial publish.
                # perception_transform_node가 깊이/hand-eye 변환 후 채워 넣는다.
                obj.transform_valid = False
                out.objects.append(obj)

            self._publisher.publish(out)
            self.get_logger().debug(
                f"raw={len(detections)} fused={len(fused)} infer={t_inf*1000:.1f}ms"
            )
        finally:
            self._processing = False


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ObjectDetectionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
