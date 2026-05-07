"""Top-level orchestrator for the nut pick-and-place loop.

Calls /perception/detect_once for each detection cycle, picks the best
candidate via target_selector, and dispatches /robot/pick_and_place
actions until the order book is empty.

Order source is selected via the `order_source` parameter:
  - "mock" : MockOrderProvider with `mock_order_*` parameters
  - "db"   : DBOrderProvider against `db_service_name`

The actual loop runs in a worker thread so we can block on action/service
futures without freezing the executor that drives the subscriptions and
service callbacks.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from cobot_msgs.action import PickAndPlace
from cobot_msgs.srv import DetectOnce

from .order_provider import DBOrderProvider, FileOrderProvider, MockOrderProvider, OrderBook
from .retry_policy import FailureAction, RetryPolicy
from .target_selector import WorkspaceBox, choose_target
from .task_state import TaskState


class TaskManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("task_manager_node")

        # Parameters
        self.declare_parameter("order_source", "mock")          # mock | db | file
        self.declare_parameter("mock_order_almond", 2)
        self.declare_parameter("mock_order_cashew", 2)
        self.declare_parameter("mock_order_pistachio", 2)
        self.declare_parameter("mock_order_walnut", 2)
        self.declare_parameter("db_service_name", "/db/get_nut_order")
        # FileOrderProvider: reads cobot_voice/output/latest_order.json
        self.declare_parameter("file_order_path", "")
        self.declare_parameter("file_order_require_success", True)

        self.declare_parameter(
            "class_priority",
            ["almond", "cashew", "pistachio", "walnut"],
        )

        self.declare_parameter("conf_gate", 0.40)
        self.declare_parameter("min_depth_mm", 2.0)

        self.declare_parameter("workspace_xmin_mm", 200.0)
        self.declare_parameter("workspace_xmax_mm", 700.0)
        self.declare_parameter("workspace_ymin_mm", -300.0)
        self.declare_parameter("workspace_ymax_mm", 300.0)
        self.declare_parameter("workspace_zmin_mm", 0.0)
        self.declare_parameter("workspace_zmax_mm", 500.0)

        self.declare_parameter("return_xyz_mm", [367.0, -150.0, 340.0])
        self.declare_parameter("return_zyz_deg", [168.0, 179.0, 168.0])

        # Pre-grasp width = candidate.short_axis_mm + margin, clamped.
        # Setting margin <= 0 also disables pre-positioning at the action server.
        self.declare_parameter("pre_grasp_margin_mm", 8.0)
        self.declare_parameter("pre_grasp_min_mm", 15.0)
        self.declare_parameter("pre_grasp_max_mm", 80.0)

        # Per-class fine-tune offset added to grasp_xyz.z (mm). Negative =
        # grip deeper (good for nuts that slip). Mirrors PER_CLASS_Z_OFFSET
        # in scripts/pick_all.py so both code paths yield identical motion.
        self.declare_parameter("per_class_z_offset_almond_mm", 0.0)
        self.declare_parameter("per_class_z_offset_cashew_mm", 0.0)
        self.declare_parameter("per_class_z_offset_pistachio_mm", 0.0)
        self.declare_parameter("per_class_z_offset_walnut_mm", -1.0)

        self.declare_parameter("perception_service_name", "/perception/detect_once")
        self.declare_parameter("pick_action_name", "/robot/pick_and_place")
        self.declare_parameter("home_service_name", "/robot/home")

        self.declare_parameter("max_detect_misses", 2)
        self.declare_parameter("max_grasp_failures", 2)
        self.declare_parameter("service_timeout_sec", 10.0)
        self.declare_parameter("action_timeout_sec", 60.0)

        # Settle delay between a completed pick and the next detect_once.
        # The pick action's "home" stage returns when the move command
        # completes, but the camera buffer may still hold frames from
        # mid-motion. Without this delay perception can read a stale
        # detection paired with the post-motion TCP pose, projecting nuts
        # onto wrong base coords (observed: y-shift of 50-100mm). Mirrors
        # pick_all.py's --inter-pick-delay (default 0.5s).
        self.declare_parameter("inter_pick_delay_sec", 0.5)

        self.declare_parameter("autostart", True)

        # Build order provider
        order_source = str(self.get_parameter("order_source").value)
        if order_source == "mock":
            self._order_provider = MockOrderProvider({
                "almond": int(self.get_parameter("mock_order_almond").value),
                "cashew": int(self.get_parameter("mock_order_cashew").value),
                "pistachio": int(self.get_parameter("mock_order_pistachio").value),
                "walnut": int(self.get_parameter("mock_order_walnut").value),
            })
        elif order_source == "db":
            self._order_provider = DBOrderProvider(
                node=self,
                service_name=str(self.get_parameter("db_service_name").value),
                timeout_sec=float(self.get_parameter("service_timeout_sec").value),
            )
        elif order_source == "file":
            file_path = str(self.get_parameter("file_order_path").value)
            if not file_path:
                raise ValueError(
                    "order_source='file' requires file_order_path parameter"
                )
            self._order_provider = FileOrderProvider(
                file_path=file_path,
                require_success=bool(
                    self.get_parameter("file_order_require_success").value
                ),
            )
            self.get_logger().info(f"FileOrderProvider reading {file_path}")
        else:
            raise ValueError(f"unknown order_source={order_source!r}")

        # Workspace + selector params
        self._workspace = WorkspaceBox(
            xmin_mm=float(self.get_parameter("workspace_xmin_mm").value),
            xmax_mm=float(self.get_parameter("workspace_xmax_mm").value),
            ymin_mm=float(self.get_parameter("workspace_ymin_mm").value),
            ymax_mm=float(self.get_parameter("workspace_ymax_mm").value),
            zmin_mm=float(self.get_parameter("workspace_zmin_mm").value),
            zmax_mm=float(self.get_parameter("workspace_zmax_mm").value),
        )
        self._conf_gate = float(self.get_parameter("conf_gate").value)
        self._min_depth_mm = float(self.get_parameter("min_depth_mm").value)
        self._priority = list(self.get_parameter("class_priority").value)
        self._return_xyz_mm = list(self.get_parameter("return_xyz_mm").value)
        self._return_zyz_deg = list(self.get_parameter("return_zyz_deg").value)
        self._pre_grasp_margin_mm = float(self.get_parameter("pre_grasp_margin_mm").value)
        self._pre_grasp_min_mm = float(self.get_parameter("pre_grasp_min_mm").value)
        self._pre_grasp_max_mm = float(self.get_parameter("pre_grasp_max_mm").value)
        self._service_timeout_sec = float(self.get_parameter("service_timeout_sec").value)
        self._action_timeout_sec = float(self.get_parameter("action_timeout_sec").value)
        self._inter_pick_delay_sec = float(self.get_parameter("inter_pick_delay_sec").value)
        self._per_class_z_offset_mm = {
            "almond": float(self.get_parameter("per_class_z_offset_almond_mm").value),
            "cashew": float(self.get_parameter("per_class_z_offset_cashew_mm").value),
            "pistachio": float(self.get_parameter("per_class_z_offset_pistachio_mm").value),
            "walnut": float(self.get_parameter("per_class_z_offset_walnut_mm").value),
        }

        self._retry = RetryPolicy(
            max_detect_misses=int(self.get_parameter("max_detect_misses").value),
            max_grasp_failures=int(self.get_parameter("max_grasp_failures").value),
        )

        # ROS interfaces
        cb_group = ReentrantCallbackGroup()
        self._detect_client = self.create_client(
            DetectOnce,
            str(self.get_parameter("perception_service_name").value),
            callback_group=cb_group,
        )
        self._home_client = self.create_client(
            Trigger,
            str(self.get_parameter("home_service_name").value),
            callback_group=cb_group,
        )
        self._pick_client = ActionClient(
            self,
            PickAndPlace,
            str(self.get_parameter("pick_action_name").value),
            callback_group=cb_group,
        )

        self._status_pub = self.create_publisher(String, "/task/status", 10)
        self._result_pub = self.create_publisher(String, "/task/result", 10)

        self._state = TaskState.IDLE
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        # Service to trigger the worker manually (when autostart=False).
        # Useful when downstream nodes (perception YOLO load, camera) need
        # time to come up before the order loop should fire its first
        # detect_once. A caller (e.g., voice_order_flow) waits for the
        # system to be ready, then calls /task/start.
        self._start_service = self.create_service(
            Trigger, "/task/start", self._handle_start, callback_group=cb_group
        )

        if bool(self.get_parameter("autostart").value):
            self.start_worker()

    def _handle_start(self, _req, resp):
        if self._worker is not None and self._worker.is_alive():
            resp.success = False
            resp.message = "task already running"
        else:
            self.start_worker()
            resp.success = True
            resp.message = "task started"
        return resp

    # ----- worker control ------------------------------------------------

    def start_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop_worker(self) -> None:
        self._stop_event.set()

    # ----- helpers -------------------------------------------------------

    def _set_state(self, state: TaskState, info: str = "") -> None:
        self._state = state
        msg = String()
        msg.data = f"{state.value}{(' ' + info) if info else ''}"
        self._status_pub.publish(msg)
        self.get_logger().info(f"[state] {msg.data}")

    def _publish_result(self, success: bool, info: str = "") -> None:
        msg = String()
        msg.data = f"{'success' if success else 'failure'} {info}".strip()
        self._result_pub.publish(msg)

    def _wait_service(self, client, name: str) -> bool:
        if client.wait_for_service(timeout_sec=self._service_timeout_sec):
            return True
        self.get_logger().error(f"service {name} not available")
        return False

    def _call_home(self) -> bool:
        if not self._wait_service(self._home_client, "home"):
            return False
        future = self._home_client.call_async(Trigger.Request())
        if not self._await_future(future, self._service_timeout_sec):
            return False
        resp = future.result()
        if not resp.success:
            self.get_logger().error(f"home service failed: {resp.message}")
            return False
        return True

    def _detect_once(self):
        if not self._wait_service(self._detect_client, "detect_once"):
            return None
        future = self._detect_client.call_async(DetectOnce.Request())
        if not self._await_future(future, self._service_timeout_sec):
            return None
        resp = future.result()
        if not resp.success:
            self.get_logger().warn(f"detect_once not ready: {resp.message}")
            return None
        return resp.objects

    def _await_future(self, future, timeout_sec: float) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline and not future.done():
            if self._stop_event.is_set():
                return False
            time.sleep(0.05)
        return future.done()

    def _send_pick_goal(self, target_class: str, candidate, return_xyz, return_zyz_deg):
        if not self._pick_client.wait_for_server(timeout_sec=self._service_timeout_sec):
            self.get_logger().error("pick_and_place action server not available")
            return None

        # Pre-grasp width: short axis + margin, clamped. <=0 disables pre-position.
        pre_grasp_width_mm = 0.0
        if candidate.short_axis_mm > 0.0 and self._pre_grasp_margin_mm >= 0.0:
            pre_grasp_width_mm = candidate.short_axis_mm + self._pre_grasp_margin_mm
            pre_grasp_width_mm = max(self._pre_grasp_min_mm, min(self._pre_grasp_max_mm, pre_grasp_width_mm))

        goal = PickAndPlace.Goal()
        goal.target_class = target_class
        goal.grasp_xyz.x = float(candidate.base_xyz.x)
        goal.grasp_xyz.y = float(candidate.base_xyz.y)
        goal.grasp_xyz.z = float(candidate.base_xyz.z) + self._per_class_z_offset_mm.get(target_class, 0.0)
        goal.grasp_yaw = float(candidate.grasp_yaw)
        goal.pre_grasp_width_mm = float(pre_grasp_width_mm)
        goal.return_xyz.x = float(return_xyz[0])
        goal.return_xyz.y = float(return_xyz[1])
        goal.return_xyz.z = float(return_xyz[2])
        goal.return_zyz_deg = [float(return_zyz_deg[0]), float(return_zyz_deg[1]), float(return_zyz_deg[2])]

        send_future = self._pick_client.send_goal_async(goal)
        if not self._await_future(send_future, self._service_timeout_sec):
            return None
        goal_handle = send_future.result()
        if not goal_handle.accepted:
            self.get_logger().error("pick goal rejected")
            return None
        result_future = goal_handle.get_result_async()
        if not self._await_future(result_future, self._action_timeout_sec):
            self.get_logger().error("pick action timed out")
            return None
        return result_future.result().result

    # ----- main loop -----------------------------------------------------

    def _run(self) -> None:
        self._set_state(TaskState.INIT)
        try:
            order: OrderBook = self._order_provider.fetch()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"order fetch failed: {exc}")
            self._set_state(TaskState.ABORTED, "order_fetch_failed")
            self._publish_result(False, "order_fetch_failed")
            return

        if not self._call_home():
            self._set_state(TaskState.ABORTED, "home_failed")
            self._publish_result(False, "home_failed")
            return

        while order.has_remaining() and not self._stop_event.is_set():
            self._set_state(TaskState.DETECT)
            target_class = order.next_class(self._priority)
            if target_class is None:
                break

            objects_msg = self._detect_once()
            if objects_msg is None:
                misses = order.record_detect_miss(target_class)
                if self._retry.on_detect_miss(misses) is FailureAction.SKIP_CLASS:
                    self.get_logger().warn(f"skip class {target_class}: detect unavailable")
                    order.mark_skipped(target_class)
                continue

            self._set_state(TaskState.SELECT_TARGET, target_class)
            candidate = choose_target(
                objects_msg.objects,
                target_class,
                self._workspace,
                conf_gate=self._conf_gate,
                min_depth_mm=self._min_depth_mm,
            )
            if candidate is None:
                misses = order.record_detect_miss(target_class)
                action = self._retry.on_detect_miss(misses)
                self.get_logger().warn(
                    f"no candidate for {target_class} (miss #{misses}) -> {action.value}"
                )
                if action is FailureAction.SKIP_CLASS:
                    order.mark_skipped(target_class)
                continue

            self._set_state(TaskState.PICK_AND_PLACE, target_class)
            self.get_logger().info(
                f"picking {target_class} at base=({candidate.base_xyz.x:.1f},"
                f"{candidate.base_xyz.y:.1f},{candidate.base_xyz.z:.1f}) "
                f"yaw={candidate.grasp_yaw:.3f} conf={candidate.confidence:.2f} "
                f"area={candidate.width * candidate.height:.0f} "
                f"short_axis={candidate.short_axis_mm:.1f}mm"
            )

            result = self._send_pick_goal(
                target_class, candidate,
                self._return_xyz_mm, self._return_zyz_deg,
            )
            if result is None:
                self._set_state(TaskState.ABORTED, "action_failure")
                self._publish_result(False, "action_failure")
                return

            if result.success:
                order.consume_one(target_class)
                self.get_logger().info(
                    f"{target_class} ok, remaining={order.counts[target_class]}"
                )
                # Settle before next detect: camera frames published mid-
                # motion are still in perception_transform_node's buffer;
                # without this delay the next detect_once pairs a stale
                # detection with the post-motion TCP pose, projecting nuts
                # to wrong base coords. Mirrors pick_all.py behavior.
                if self._inter_pick_delay_sec > 0.0:
                    time.sleep(self._inter_pick_delay_sec)
                continue

            grasp_misses = order.record_grasp_failure(target_class)
            decision = self._retry.on_action_failure(int(result.failure_code), grasp_misses)
            self.get_logger().warn(
                f"pick failed code={result.failure_code} ({result.message}) -> {decision.value}"
            )
            if decision is FailureAction.SKIP_CLASS:
                order.mark_skipped(target_class)
            elif decision is FailureAction.ABORT:
                self._set_state(TaskState.ABORTED, f"failure_code={result.failure_code}")
                self._publish_result(False, f"failure_code={result.failure_code}")
                return
            # RETRY_PICK / RETRY_DETECT: just loop and try again

        if self._stop_event.is_set():
            self._set_state(TaskState.SAFETY_STOP)
            self._publish_result(False, "safety_stop")
            return

        self._set_state(TaskState.DONE)
        self._publish_result(order.all_done(), f"counts={order.counts} skipped={list(order.skipped)}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node: Optional[TaskManagerNode] = None
    try:
        node = TaskManagerNode()
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
            node.stop_worker()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
