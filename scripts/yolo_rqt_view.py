#!/usr/bin/env python3
"""Standalone YOLO viewer for rqt_image_view.

Subscribes to a RealSense color topic, runs YOLO (OBB) inference, and
publishes an annotated image (ultralytics' built-in plot) on a separate
topic so it can be viewed in rqt_image_view. Does not interfere with
the production object_detection_node pipeline.
"""

import argparse
import os
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from ultralytics import YOLO

from cobot_object_detection.model_paths import resolve_model_path

INPUT_TOPIC = "/camera/camera/color/image_raw"
OUTPUT_TOPIC = "/yolo/annotated"
CONF = 0.40
IOU = 0.50


class YoloRqtView(Node):
    def __init__(self, weights: str):
        super().__init__("yolo_rqt_view")
        self.get_logger().info(f"Loading weights: {weights}")
        self.model = YOLO(weights)
        self.bridge = CvBridge()
        self.busy = False

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=2,
        )
        self.create_subscription(Image, INPUT_TOPIC, self.cb, sensor_qos)
        self.pub = self.create_publisher(Image, OUTPUT_TOPIC, 1)
        self.get_logger().info(f"sub={INPUT_TOPIC} -> pub={OUTPUT_TOPIC}")

    def cb(self, msg: Image) -> None:
        if self.busy:
            return
        self.busy = True
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            results = self.model(frame, conf=CONF, iou=IOU, verbose=False)
            annotated = results[0].plot()
            out = self.bridge.cv2_to_imgmsg(annotated, "bgr8")
            out.header = msg.header
            self.pub.publish(out)
        except Exception as exc:
            self.get_logger().warn(f"inference/publish failed: {exc}")
        finally:
            self.busy = False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weights",
        default=os.environ.get("YOLO_WEIGHTS", ""),
        help=(
            "Path to YOLO weights. Empty defaults to packaged "
            "cobot_object_detection/models/best.pt or the source-tree "
            "fallback. Also reads YOLO_WEIGHTS env var."
        ),
    )
    args = parser.parse_args()

    try:
        weights = resolve_model_path(args.weights)
    except FileNotFoundError as exc:
        print(f"yolo_rqt_view: {exc}", file=sys.stderr)
        sys.exit(1)

    rclpy.init()
    node = YoloRqtView(weights)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
