"""ROS2 node: bridges 2D OBB detections to base-frame grasp candidates.

Pipeline per /perception/detect_once call:
  1. read the latest /detection/objects message
  2. read the latest aligned-depth frame and intrinsics
  3. for each detection, look up median depth inside the OBB
  4. lift to camera frame using the pinhole model (mm)
  5. transform to robot base frame using base2gripper(TCP) @ gripper2camera(npy)
  6. compute grasp_yaw from OBB theta and (width, height)
  7. apply DEPTH_OFFSET / MIN_DEPTH_BASE clamps to z and emit DetectedObject

TCP pose source is selectable:
  - "fixed"  : use fixed_tcp_xyz_mm + fixed_tcp_zyz_deg (Phase A standalone)
  - "service": call cobot_robot_control's GetCurrentPose service
              (param `tcp_service_name`, default `/robot/get_current_pose`)
              to fetch the live TCP pose every detect_once. This is the
              default once cobot_robot_control is up.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image

from cobot_msgs.msg import DetectedObjectArray
from cobot_msgs.srv import DetectOnce, GetCurrentPose

from .depth_filter import median_inside_obb
from .grasp_pose_generator import yaw_from_obb
from .handeye_transform import (
    compose_base2camera,
    load_gripper2camera,
    tcp_to_base2gripper,
    transform_camera_to_base,
)


class PerceptionTransformNode(Node):
    def __init__(self) -> None:
        super().__init__("perception_transform_node")

        # Hand-eye + intrinsics + depth params
        self.declare_parameter(
            "gripper2camera_npy",
            "/home/choijinwoo/cobot_ws/src/cobot2/[lecture]pick_and_place_voice/resource/T_gripper2camera.npy",
        )
        self.declare_parameter("min_depth_camera_mm", 50.0)
        self.declare_parameter("max_depth_camera_mm", 1500.0)
        self.declare_parameter("depth_offset_mm", -5.0)      # lecture's z bias
        self.declare_parameter("min_depth_base_mm", 2.0)     # clamp on base z

        # TCP pose source
        self.declare_parameter("tcp_source", "fixed")        # fixed | service
        self.declare_parameter("fixed_tcp_xyz_mm", [400.0, 0.0, 400.0])
        self.declare_parameter("fixed_tcp_zyz_deg", [0.0, 180.0, 0.0])
        self.declare_parameter("tcp_service_name", "/robot/get_current_pose")
        self.declare_parameter("tcp_service_timeout_sec", 2.0)

        # Topics / service names
        self.declare_parameter("detection_topic", "/detection/objects")
        self.declare_parameter("depth_topic", "/camera/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("camera_info_topic", "/camera/camera/color/camera_info")
        self.declare_parameter("service_name", "/perception/detect_once")

        # Latest cached state
        self._detection: Optional[DetectedObjectArray] = None
        self._depth: Optional[np.ndarray] = None
        self._intrinsics: Optional[dict] = None

        # Hand-eye matrix
        npy_path = self.get_parameter("gripper2camera_npy").value
        self._gripper2cam = load_gripper2camera(npy_path)
        self.get_logger().info(f"Loaded gripper2camera from {npy_path}")

        # Subscribers
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=2,
        )
        cb_group = ReentrantCallbackGroup()
        self._bridge = CvBridge()
        self._detection_sub = self.create_subscription(
            DetectedObjectArray,
            self.get_parameter("detection_topic").value,
            self._on_detection,
            10,
            callback_group=cb_group,
        )
        self._depth_sub = self.create_subscription(
            Image,
            self.get_parameter("depth_topic").value,
            self._on_depth,
            sensor_qos,
            callback_group=cb_group,
        )
        self._info_sub = self.create_subscription(
            CameraInfo,
            self.get_parameter("camera_info_topic").value,
            self._on_camera_info,
            10,
            callback_group=cb_group,
        )

        # Service client for current robot pose (used when tcp_source == "service")
        self._tcp_client = self.create_client(
            GetCurrentPose,
            str(self.get_parameter("tcp_service_name").value),
            callback_group=cb_group,
        )

        # Service server
        self._service = self.create_service(
            DetectOnce,
            self.get_parameter("service_name").value,
            self._handle_detect_once,
            callback_group=cb_group,
        )
        self.get_logger().info(
            f"Service {self.get_parameter('service_name').value} ready"
        )

    # --- subscriber callbacks ---------------------------------------------

    def _on_detection(self, msg: DetectedObjectArray) -> None:
        self._detection = msg

    def _on_depth(self, msg: Image) -> None:
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        except Exception as exc:  # cv_bridge errors
            self.get_logger().warn(f"depth cv_bridge failed: {exc}")
            return
        self._depth = frame

    def _on_camera_info(self, msg: CameraInfo) -> None:
        # Avoid recomputing on every callback
        if (
            self._intrinsics is not None
            and self._intrinsics["k"] == tuple(msg.k)
        ):
            return
        self._intrinsics = {
            "fx": float(msg.k[0]),
            "fy": float(msg.k[4]),
            "ppx": float(msg.k[2]),
            "ppy": float(msg.k[5]),
            "k": tuple(msg.k),
        }

    # --- TCP pose source --------------------------------------------------

    def _current_tcp(self) -> Tuple[List[float], List[float]]:
        mode = self.get_parameter("tcp_source").value
        if mode == "fixed":
            xyz = list(self.get_parameter("fixed_tcp_xyz_mm").value)
            zyz = list(self.get_parameter("fixed_tcp_zyz_deg").value)
            return xyz, zyz
        if mode == "service":
            return self._current_tcp_via_service()
        raise NotImplementedError(f"unknown tcp_source={mode!r}")

    def _current_tcp_via_service(self) -> Tuple[List[float], List[float]]:
        timeout = float(self.get_parameter("tcp_service_timeout_sec").value)
        if not self._tcp_client.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(
                f"{self.get_parameter('tcp_service_name').value} not available"
            )
        future = self._tcp_client.call_async(GetCurrentPose.Request())
        deadline = time.time() + timeout
        while time.time() < deadline and not future.done():
            time.sleep(0.005)
        if not future.done():
            raise RuntimeError("get_current_pose call timed out")
        resp = future.result()
        if not resp.success:
            raise RuntimeError(f"get_current_pose failed: {resp.message}")
        xyz = [float(resp.xyz_mm.x), float(resp.xyz_mm.y), float(resp.xyz_mm.z)]
        zyz = [float(resp.zyz_deg[0]), float(resp.zyz_deg[1]), float(resp.zyz_deg[2])]
        return xyz, zyz

    # --- service handler --------------------------------------------------

    def _handle_detect_once(self, request, response):
        if self._detection is None:
            response.success = False
            response.message = "no detection received yet"
            return response
        if self._depth is None:
            response.success = False
            response.message = "no depth frame received yet"
            return response
        if self._intrinsics is None:
            response.success = False
            response.message = "no camera_info received yet"
            return response

        try:
            tcp_xyz, tcp_zyz = self._current_tcp()
        except (NotImplementedError, RuntimeError) as exc:
            response.success = False
            response.message = f"tcp source error: {exc}"
            return response
        except Exception as exc:  # noqa: BLE001
            response.success = False
            response.message = f"unexpected tcp error: {exc}"
            self.get_logger().error(response.message)
            return response

        base2gripper = tcp_to_base2gripper(tcp_xyz, tcp_zyz)
        base2cam = compose_base2camera(base2gripper, self._gripper2cam)

        fx = self._intrinsics["fx"]
        fy = self._intrinsics["fy"]
        ppx = self._intrinsics["ppx"]
        ppy = self._intrinsics["ppy"]

        min_depth_cam = float(self.get_parameter("min_depth_camera_mm").value)
        max_depth_cam = float(self.get_parameter("max_depth_camera_mm").value)
        depth_offset = float(self.get_parameter("depth_offset_mm").value)
        min_depth_base = float(self.get_parameter("min_depth_base_mm").value)

        depth = self._depth
        out = DetectedObjectArray()
        out.header = self._detection.header

        kept = 0
        for src in self._detection.objects:
            obj = src
            z_mm = median_inside_obb(
                depth,
                obj.cx,
                obj.cy,
                obj.width,
                obj.height,
                obj.theta,
                min_depth_mm=min_depth_cam,
                max_depth_mm=max_depth_cam,
            )
            if not np.isfinite(z_mm):
                obj.transform_valid = False
                out.objects.append(obj)
                continue

            X = (obj.cx - ppx) * z_mm / fx
            Y = (obj.cy - ppy) * z_mm / fy
            obj.camera_xyz.x = float(X)
            obj.camera_xyz.y = float(Y)
            obj.camera_xyz.z = float(z_mm)

            bx, by, bz = transform_camera_to_base(base2cam, (X, Y, z_mm))
            bz = max(bz + depth_offset, min_depth_base)
            obj.base_xyz.x = bx
            obj.base_xyz.y = by
            obj.base_xyz.z = bz

            obj.grasp_yaw = float(yaw_from_obb(obj.theta, obj.width, obj.height))

            # Physical OBB dimensions via pinhole at the measured depth.
            # Average fx and fy (typically ~equal on RealSense) for an
            # isotropic mm-per-pixel scale.
            mm_per_px = z_mm / ((fx + fy) / 2.0)
            short_px = min(obj.width, obj.height)
            long_px = max(obj.width, obj.height)
            obj.short_axis_mm = float(short_px * mm_per_px)
            obj.long_axis_mm = float(long_px * mm_per_px)

            obj.transform_valid = True
            out.objects.append(obj)
            kept += 1

        response.objects = out
        response.success = True
        response.message = f"transformed {kept}/{len(self._detection.objects)} detections"
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node: Optional[PerceptionTransformNode] = None
    try:
        node = PerceptionTransformNode()
        executor = MultiThreadedExecutor()
        executor.add_node(node)
        try:
            executor.spin()
        finally:
            executor.shutdown()
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
