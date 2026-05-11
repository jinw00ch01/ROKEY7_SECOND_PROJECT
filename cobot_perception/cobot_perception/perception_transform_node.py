# 한국어 요약:
#   detect_once 트리거식 perception 노드.
#   서비스 호출 시점부터 새로 들어오는 color frame N장을 모아 YOLO-OBB 추론을
#   실행하고, 같은 시점의 depth/intrinsics/TCP를 묶어 base 프레임으로 변환한다.
#   stream/cache 방식의 frame-TCP 미스매치를 원천 차단한다.
"""ROS2 node: trigger-based detect_once that owns YOLO + transform end-to-end.

Pipeline per /perception/detect_once call:
  1. record trigger time
  2. wait for `num_capture_frames` color frames whose header.stamp is newer than trigger
  3. run YOLO-OBB on each captured frame, fuse with the aggregator
  4. read latest aligned-depth + camera_info + TCP (all sampled inside the same
     stationary window as the color frames)
  5. for each fused detection, look up median depth inside the OBB
  6. lift to camera frame using the pinhole model (mm)
  7. transform to robot base frame using base2gripper(TCP) @ gripper2camera(npy)
  8. compute grasp_yaw from OBB theta and (width, height)
  9. apply DEPTH_OFFSET / MIN_DEPTH_BASE clamps to z and emit DetectedObject

TCP pose source is selectable:
  - "fixed"  : use fixed_tcp_xyz_mm + fixed_tcp_zyz_deg (Phase A standalone)
  - "service": call cobot_robot_control's GetCurrentPose service (default)
"""

from __future__ import annotations

from pathlib import Path
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

from cobot_msgs.msg import DetectedObject, DetectedObjectArray
from cobot_msgs.srv import DetectOnce, GetCurrentPose

from cobot_object_detection.detection_postprocess import DetectionAggregator
from cobot_object_detection.model_paths import resolve_model_path
from cobot_object_detection.yolo_detector import YoloObbDetector

from .depth_filter import median_inside_obb
from .grasp_pose_generator import yaw_from_obb
from .handeye_transform import (
    compose_base2camera,
    load_gripper2camera,
    tcp_to_base2gripper,
    transform_camera_to_base,
)


def _stamp_tuple(stamp) -> Tuple[int, int]:
    return int(stamp.sec), int(stamp.nanosec)


class PerceptionTransformNode(Node):
    def __init__(self) -> None:
        super().__init__("perception_transform_node")

        # Hand-eye + intrinsics + depth params
        self.declare_parameter("gripper2camera_npy", "")
        self.declare_parameter("min_depth_camera_mm", 50.0)
        self.declare_parameter("max_depth_camera_mm", 1500.0)
        # depth_offset_mm: 깊이 측정 편향(bias) 보정용 z 오프셋. 강의 노트 기준값.
        # min_depth_base_mm: 변환 후 base z를 클램프하여 그리퍼가 바닥(테이블) 아래로
        # 내려가는 것을 방지하는 안전 하한.
        self.declare_parameter("depth_offset_mm", -5.0)
        self.declare_parameter("min_depth_base_mm", 2.0)

        # TCP pose source
        self.declare_parameter("tcp_source", "fixed")        # fixed | service
        self.declare_parameter("fixed_tcp_xyz_mm", [400.0, 0.0, 400.0])
        self.declare_parameter("fixed_tcp_zyz_deg", [0.0, 180.0, 0.0])
        self.declare_parameter("tcp_service_name", "/robot/get_current_pose")
        self.declare_parameter("tcp_service_timeout_sec", 5.0)

        # YOLO inference (이전 object_detection_node 책임을 통합)
        self.declare_parameter("model_path", "")
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

        # Trigger 캡처 정책: 트리거 시점 이후로 들어오는 color frame을
        # num_capture_frames장 모을 때까지 capture_timeout_sec 한도 내에서 대기.
        self.declare_parameter("num_capture_frames", 5)
        self.declare_parameter("capture_timeout_sec", 2.0)

        # Topics / service names
        self.declare_parameter("color_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("depth_topic", "/camera/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("camera_info_topic", "/camera/camera/color/camera_info")
        self.declare_parameter("service_name", "/perception/detect_once")

        # Latest cached state
        self._latest_color: Optional[Image] = None
        self._latest_depth: Optional[np.ndarray] = None
        self._intrinsics: Optional[dict] = None

        # Hand-eye matrix
        # 캘리브레이션 누락은 mis-config로 간주하여 startup에서 즉시 raise.
        npy_path = str(self.get_parameter("gripper2camera_npy").value or "").strip()
        if not npy_path:
            raise RuntimeError(
                "gripper2camera_npy is required. Provide the calibrated "
                "T_gripper2camera.npy path in cobot_perception/config/perception.yaml "
                "or as a ROS parameter override."
            )
        npy_path = str(Path(npy_path).expanduser())
        self._gripper2cam = load_gripper2camera(npy_path)
        self.get_logger().info(f"Loaded gripper2camera from {npy_path}")

        # YOLO detector + aggregator (perception 내부 소유)
        model_path = resolve_model_path(self.get_parameter("model_path").value)
        device_param = self.get_parameter("device").value
        self.get_logger().info(
            f"Loading YOLO-OBB model: {model_path} "
            f"(imgsz={self.get_parameter('imgsz').value}, "
            f"conf={self.get_parameter('conf_threshold').value}, "
            f"iou={self.get_parameter('iou_threshold').value})"
        )
        self._detector = YoloObbDetector(
            model_path=model_path,
            class_names=list(self.get_parameter("class_names").value),
            imgsz=int(self.get_parameter("imgsz").value),
            conf_threshold=float(self.get_parameter("conf_threshold").value),
            iou_threshold=float(self.get_parameter("iou_threshold").value),
            device=device_param if device_param else None,
        )
        self._aggregator_window_sec = float(
            self.get_parameter("multi_frame_window_sec").value
        )
        self._aggregator_cluster_px = float(
            self.get_parameter("cluster_distance_threshold_px").value
        )

        # Subscribers
        # RealSense color/depth publisher가 RELIABLE이며 cyclonedds 환경에서 BE
        # 단독 subscriber는 메시지가 전달되지 않는 패턴이 있어 RELIABLE로 매칭.
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        cb_group = ReentrantCallbackGroup()
        self._bridge = CvBridge()
        self._color_sub = self.create_subscription(
            Image,
            self.get_parameter("color_topic").value,
            self._on_color,
            sensor_qos,
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
            f"Service {self.get_parameter('service_name').value} ready (trigger-based)"
        )

    # --- subscriber callbacks ---------------------------------------------

    def _on_color(self, msg: Image) -> None:
        # 원본 메시지를 저장 (header.stamp으로 freshness 판정).
        self._latest_color = msg

    def _on_depth(self, msg: Image) -> None:
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        except Exception as exc:  # cv_bridge errors
            self.get_logger().warn(f"depth cv_bridge failed: {exc}")
            return
        self._latest_depth = frame

    def _on_camera_info(self, msg: CameraInfo) -> None:
        # K가 동일하면 dict 재구성 생략 (camera_info는 매 프레임 재발행됨).
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
        # 서비스 핸들러(detect_once) 내부에서 호출되므로 add_done_callback 대신
        # short-poll으로 결과를 기다린다.
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

    # --- trigger capture --------------------------------------------------

    def _capture_and_infer(self) -> Tuple[Optional[list], Optional[Image]]:
        """트리거 시점 이후의 color frame을 모아 YOLO 추론하고 fuse.

        Returns: (fused_detections, last_color_msg) — capture 실패시 (None, None).
        """
        n_frames = int(self.get_parameter("num_capture_frames").value)
        timeout = float(self.get_parameter("capture_timeout_sec").value)

        # 트리거 시점 이전의 stale frame을 배제하기 위해 현재 시각을 기록.
        # ROS clock(노드)이 아닌 system clock과 비교해야 하지만, header.stamp는
        # 카메라 publish 시점의 ROS 시계를 따르므로 self.get_clock().now()와
        # 직접 비교 가능.
        trigger_now = self.get_clock().now()
        trigger_stamp = trigger_now.to_msg()
        trigger_tuple = (int(trigger_stamp.sec), int(trigger_stamp.nanosec))

        aggregator = DetectionAggregator(
            window_sec=self._aggregator_window_sec,
            cluster_distance_px=self._aggregator_cluster_px,
        )

        last_processed: Optional[Tuple[int, int]] = None
        last_msg: Optional[Image] = None
        collected = 0
        deadline = time.monotonic() + timeout
        while collected < n_frames and time.monotonic() < deadline:
            msg = self._latest_color
            if msg is None:
                time.sleep(0.005)
                continue
            stamp = _stamp_tuple(msg.header.stamp)
            # 트리거 시점보다 오래된 프레임은 motion 잔재일 수 있어 배제.
            if stamp <= trigger_tuple:
                time.sleep(0.005)
                continue
            # 같은 메시지를 다시 추론하지 않도록 중복 체크.
            if last_processed is not None and stamp == last_processed:
                time.sleep(0.005)
                continue
            last_processed = stamp
            last_msg = msg
            try:
                frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            except Exception as exc:  # cv_bridge errors
                self.get_logger().warn(f"color cv_bridge failed: {exc}")
                continue
            detections = self._detector.infer(frame)
            aggregator.add(detections, time.time())
            collected += 1

        if collected == 0:
            return None, None
        return aggregator.fuse(), last_msg

    # --- service handler --------------------------------------------------

    def _handle_detect_once(self, _request, response):
        if self._intrinsics is None:
            response.success = False
            response.message = "no camera_info received yet"
            return response

        # 트리거: fresh color frame을 수집하면서 YOLO 추론 동시 진행.
        fused_objects, last_color_msg = self._capture_and_infer()
        if fused_objects is None or last_color_msg is None:
            response.success = False
            response.message = "no fresh color frames within capture_timeout_sec"
            return response

        # depth는 수집 윈도우 마지막 시점의 latest를 사용. color 캡처와 동일한
        # 정지 구간에서 publish된 frame이므로 같은 장면을 반영.
        depth = self._latest_depth
        if depth is None:
            response.success = False
            response.message = "no depth frame received yet"
            return response

        # TCP는 색 캡처 직후에 1회만 조회. 픽 사이클 home에서 정지 상태이므로
        # capture window와 같은 robot pose를 반영.
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

        # base ← gripper ← camera 동차변환 체인 구성.
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

        out = DetectedObjectArray()
        out.header = last_color_msg.header
        # frame_id는 카메라 광학좌표계 기준.
        if not out.header.frame_id:
            out.header.frame_id = "camera_color_optical_frame"

        kept = 0
        for d in fused_objects:
            obj = DetectedObject()
            obj.class_name = d.class_name
            obj.confidence = float(d.confidence)
            obj.cx = float(d.cx)
            obj.cy = float(d.cy)
            obj.width = float(d.width)
            obj.height = float(d.height)
            obj.theta = float(d.theta)

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

            # pinhole 모델로 픽셀 좌표 (cx,cy)와 깊이 z_mm을 카메라 프레임 X,Y로 복원.
            X = (obj.cx - ppx) * z_mm / fx
            Y = (obj.cy - ppy) * z_mm / fy
            obj.camera_xyz.x = float(X)
            obj.camera_xyz.y = float(Y)
            obj.camera_xyz.z = float(z_mm)

            bx, by, bz = transform_camera_to_base(base2cam, (X, Y, z_mm))
            # depth_offset_mm로 측정 편향 보정 후 min_depth_base_mm 하한을 적용.
            bz = max(bz + depth_offset, min_depth_base)
            obj.base_xyz.x = bx
            obj.base_xyz.y = by
            obj.base_xyz.z = bz

            obj.grasp_yaw = float(yaw_from_obb(obj.theta, obj.width, obj.height))

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
        response.message = f"transformed {kept}/{len(fused_objects)} detections"
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
