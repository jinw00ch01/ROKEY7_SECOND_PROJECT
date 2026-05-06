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


class ObjectDetectionNode(Node):
    def __init__(self) -> None:
        super().__init__("object_detection_node")

        self.declare_parameter(
            "model_path",
            "/home/choijinwoo/cobot_ws/src/cobot2/cobot_OD_obb_nano/"
            "train_phase2_20260504_173049/weights/best.pt",
        )
        self.declare_parameter(
            "class_names",
            ["almond", "cashew", "pistachio", "walnut"],
        )
        self.declare_parameter("imgsz", 800)
        self.declare_parameter("conf_threshold", 0.40)
        self.declare_parameter("iou_threshold", 0.50)
        self.declare_parameter("device", "")
        self.declare_parameter("multi_frame_window_sec", 0.5)
        self.declare_parameter("cluster_distance_threshold_px", 30.0)
        self.declare_parameter("color_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("output_topic", "/detection/objects")
        self.declare_parameter("publish_when_empty", True)

        model_path = self.get_parameter("model_path").value
        class_names = list(self.get_parameter("class_names").value)
        imgsz = int(self.get_parameter("imgsz").value)
        conf = float(self.get_parameter("conf_threshold").value)
        iou = float(self.get_parameter("iou_threshold").value)
        device_param = self.get_parameter("device").value
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

        self._frame_id = "camera_color_optical_frame"
        self._processing = False
        self.get_logger().info(
            f"Subscribed to {color_topic}, publishing on {output_topic}"
        )

    def _on_color(self, msg: Image) -> None:
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

            now = time.time()
            self._aggregator.add(detections, now)
            fused = self._aggregator.fuse()

            if not fused and not self._publish_when_empty:
                return

            out = DetectedObjectArray()
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
