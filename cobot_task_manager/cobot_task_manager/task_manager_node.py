# 한국어 요약:
#   너트 pick-and-place 루프의 최상위 오케스트레이터 노드이다.
#   detect_once 서비스로 인지를 받아 target_selector로 후보를 고르고
#   /robot/pick_and_place 액션을 디스패치한다. 실제 루프는 worker thread에서
#   돌리고, executor는 서비스/구독만 처리하도록 분리해 future 대기로 인한
#   freeze를 막는다. order_source 파라미터로 mock/db/file provider를 선택한다.
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
from typing import Dict, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from cobot_msgs.action import PickAndPlace
from cobot_msgs.srv import DetectOnce

from .cluster_policy import choose_cluster_plan
from .order_provider import DBOrderProvider, FileOrderProvider, MockOrderProvider, OrderBook
from .pick_offsets import load_pick_offsets
from .retry_policy import FailureAction, RetryPolicy
from .target_selector import WorkspaceBox, choose_target
from .task_state import TaskState

# 한국어: robot_control_node와 합의된 sentinel. PickAndPlace 액션을 closed-
# gripper push로 재해석하기 위한 target_class 약속. 변경 시 robot_control_node
# CLUSTER_PUSH_TARGET_CLASS도 같이 갱신해야 한다.
CLUSTER_PUSH_TARGET_CLASS = "__cluster_push__"


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

        # Per-class fine-tune offset added to grasp_xyz.z (mm). Loaded from
        # the shared cobot_config/config/pick_offsets.yaml so the /task/start
        # path and any direct caller (scripts/pick_*.py) share one source of
        # truth. Empty path -> resolver searches env var, ament-share, then
        # source-tree fallback.
        self.declare_parameter("pick_offsets_path", "")

        self.declare_parameter("perception_service_name", "/perception/detect_once")
        self.declare_parameter("pick_action_name", "/robot/pick_and_place")
        self.declare_parameter("home_service_name", "/robot/home")

        # Cluster handling — see docs/05_clustered_nuts_handling.md.
        self.declare_parameter("cluster_enabled", True)
        self.declare_parameter("cluster_dist_threshold_mm", 35.0)
        self.declare_parameter("cluster_candidate_offset_mm", 10.0)
        self.declare_parameter("cluster_push_scale", 1.5)
        # push z = grasp z + cluster_push_z_offset_mm (양수 = grasp보다 위).
        self.declare_parameter("cluster_push_z_offset_mm", 2.0)
        self.declare_parameter("max_cluster_pushes_per_class", 2)

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

        # Post-run verification. 사이클 마무리에서 홈→detect→remaining 계산→
        # 부족분 픽을 반복. 라운드별 보정 픽 성공 시 다음 라운드 detect에서
        # remaining=0 되어 자동 break.
        self.declare_parameter("verification_enabled", True)
        self.declare_parameter("max_verification_rounds", 5)

        self.declare_parameter("autostart", True)

        # worker thread 종료 신호용 Event. _await_future polling 루프에서도
        # 매 0.05s마다 검사하여 안전하게 빠져나오게 한다.
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

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
                should_stop=self._stop_event.is_set,
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
        self._verification_enabled = bool(self.get_parameter("verification_enabled").value)
        self._max_verification_rounds = int(self.get_parameter("max_verification_rounds").value)
        self._cluster_enabled = bool(self.get_parameter("cluster_enabled").value)
        self._cluster_dist_threshold_mm = float(
            self.get_parameter("cluster_dist_threshold_mm").value
        )
        self._cluster_candidate_offset_mm = float(
            self.get_parameter("cluster_candidate_offset_mm").value
        )
        self._cluster_push_scale = float(self.get_parameter("cluster_push_scale").value)
        self._cluster_push_z_offset_mm = float(
            self.get_parameter("cluster_push_z_offset_mm").value
        )
        self._max_cluster_pushes_per_class = int(
            self.get_parameter("max_cluster_pushes_per_class").value
        )
        # 사이클 동안 클래스별 cluster push 횟수 추적. 같은 클래스에서 push가
        # 반복되어 무한 루프에 빠지는 것을 막는 용도.
        self._cluster_push_counts: Dict[str, int] = {}
        explicit_offsets_path = (
            str(self.get_parameter("pick_offsets_path").value).strip() or None
        )
        self._per_class_z_offset_mm = load_pick_offsets(explicit_offsets_path)
        self.get_logger().info(
            "Per-class z offsets (mm): "
            + ", ".join(
                f"{k}={v:+.2f}"
                for k, v in sorted(self._per_class_z_offset_mm.items())
            )
        )

        self._retry = RetryPolicy(
            max_detect_misses=int(self.get_parameter("max_detect_misses").value),
            max_grasp_failures=int(self.get_parameter("max_grasp_failures").value),
        )

        # ROS interfaces
        # ReentrantCallbackGroup: 서비스/액션 콜백을 동시에 처리 가능하게 한다.
        # MultiThreadedExecutor와 결합해 worker thread에서 future를 polling하는
        # 동안에도 다른 콜백(예: /task/start 서비스)이 막히지 않게 한다.
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

    # ----- verification helpers ------------------------------------------

    def _count_detected_objects(self, objects_msg) -> Dict[str, int]:
        # detect_once 결과를 클래스별로 카운트. target_selector와 동일한 게이트
        # (conf, transform_valid, depth, workspace)를 적용해 verification 수치가
        # 실제 픽 가능 후보와 일치하도록 한다.
        counts = {cls: 0 for cls in self._priority}
        for obj in getattr(objects_msg, "objects", []):
            cls = str(getattr(obj, "class_name", ""))
            if cls not in counts:
                continue
            if float(getattr(obj, "confidence", 0.0)) < self._conf_gate:
                continue
            if not bool(getattr(obj, "transform_valid", True)):
                continue
            base_xyz = getattr(obj, "base_xyz", None)
            if base_xyz is None:
                continue
            if float(base_xyz.z) <= self._min_depth_mm:
                continue
            if not (
                self._workspace.xmin_mm <= float(base_xyz.x) <= self._workspace.xmax_mm
                and self._workspace.ymin_mm <= float(base_xyz.y) <= self._workspace.ymax_mm
                and self._workspace.zmin_mm <= float(base_xyz.z) <= self._workspace.zmax_mm
            ):
                continue
            counts[cls] += 1
        return counts

    def _detect_counts_from_home(self, label: str) -> Optional[Dict[str, int]]:
        # 홈 자세로 이동 후 settle delay를 두고 detect_once 호출.
        # 검증 라운드 시작 시점마다 호출되어 일관된 관측 조건을 보장.
        if not self._call_home():
            return None
        if self._inter_pick_delay_sec > 0.0:
            time.sleep(self._inter_pick_delay_sec)
        objects_msg = self._detect_once()
        if objects_msg is None:
            return None
        counts = self._count_detected_objects(objects_msg)
        self.get_logger().info(f"{label} detected counts: {counts}")
        return counts

    def _remaining_from_verification(
        self,
        ordered_counts: Dict[str, int],
        initial_counts: Dict[str, int],
        final_counts: Dict[str, int],
    ) -> Dict[str, int]:
        # remaining = ordered - (initial - final). initial-final이 "이번 사이클에
        # 옮긴 추정 수량". ordered보다 더 옮긴 건 0으로 clamp (over-pick 방지).
        remaining: Dict[str, int] = {}
        for cls in self._priority:
            ordered = max(0, int(ordered_counts.get(cls, 0)))
            initial = max(0, int(initial_counts.get(cls, 0)))
            final = max(0, int(final_counts.get(cls, 0)))
            moved_estimated = initial - final
            remaining[cls] = min(ordered, max(0, ordered - moved_estimated))
        return remaining

    def _await_future(self, future, timeout_sec: float) -> bool:
        # done-callback 대신 polling을 쓰는 이유:
        # worker thread에서 spin_until_future_complete를 호출하면 executor와
        # 충돌(이미 spin 중이라 reentrancy 문제)이 생기므로, executor는 main
        # thread에서 돌리고 worker는 주기적으로 future.done()만 검사한다.
        # stop_event 검사도 함께 수행해 종료 신호에 즉시 반응한다.
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
        # OBB의 짧은 축(너트 폭)에 margin을 더해 pre-grasp width를 산출한다.
        # min/max로 clamp해 그리퍼 물리 한계와 충돌을 방지한다. short_axis가
        # 0이거나 margin이 음수면 0으로 두어 액션 서버가 pre-position 단계를
        # 건너뛰도록 한다.
        pre_grasp_width_mm = 0.0
        if candidate.short_axis_mm > 0.0 and self._pre_grasp_margin_mm >= 0.0:
            pre_grasp_width_mm = candidate.short_axis_mm + self._pre_grasp_margin_mm
            pre_grasp_width_mm = max(self._pre_grasp_min_mm, min(self._pre_grasp_max_mm, pre_grasp_width_mm))

        z_offset_mm = self._per_class_z_offset_mm.get(target_class, 0.0)
        grasp_z = float(candidate.base_xyz.z) + z_offset_mm
        self.get_logger().info(
            f"pick goal: nut_type={target_class} base_z={candidate.base_xyz.z:.1f} "
            f"z_offset={z_offset_mm:+.2f} -> grasp_z={grasp_z:.1f}"
        )

        goal = PickAndPlace.Goal()
        goal.target_class = target_class
        goal.grasp_xyz.x = float(candidate.base_xyz.x)
        goal.grasp_xyz.y = float(candidate.base_xyz.y)
        goal.grasp_xyz.z = grasp_z
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

    def _send_cluster_push_goal(self, plan) -> Optional[object]:
        # 한국어: cluster_policy가 만든 ClusterPlan을 PickAndPlace 액션 goal로
        # 변환해 송출. target_class=CLUSTER_PUSH_TARGET_CLASS sentinel,
        # grasp_xyz=진입점, return_xyz=푸시 종점, grasp_yaw=진입→푸시 방향
        # (closed gripper의 회전 방향). pre_grasp_width_mm=0으로 두어 액션
        # 서버가 pre-position 단계를 건너뛰게 하고, 대신 push 첫 단계에서
        # gripper.close()를 직접 호출한다.
        if not self._pick_client.wait_for_server(timeout_sec=self._service_timeout_sec):
            self.get_logger().error("pick_and_place action server not available (cluster push)")
            return None

        ex, ey, ez = plan.entry_xyz_mm
        pex, pey, pez = plan.push_end_xyz_mm
        # push yaw: entry→push_end 방향. 닫힌 그리퍼가 회전 정렬되어 있으면
        # 이웃 너트와의 충돌 가능성을 좀 더 줄일 수 있다. atan2(dy, dx).
        import math as _math
        push_yaw = _math.atan2(pey - ey, pex - ex)

        goal = PickAndPlace.Goal()
        goal.target_class = CLUSTER_PUSH_TARGET_CLASS
        goal.grasp_xyz.x = float(ex)
        goal.grasp_xyz.y = float(ey)
        goal.grasp_xyz.z = float(ez)
        goal.grasp_yaw = float(push_yaw)
        goal.pre_grasp_width_mm = 0.0
        goal.return_xyz.x = float(pex)
        goal.return_xyz.y = float(pey)
        goal.return_xyz.z = float(pez)
        # return_zyz_deg는 cluster push에서 사용되지 않지만 메시지 필드는
        # 채워줘야 한다. 현재 yaml의 return_zyz_deg를 그대로 전달.
        goal.return_zyz_deg = [
            float(self._return_zyz_deg[0]),
            float(self._return_zyz_deg[1]),
            float(self._return_zyz_deg[2]),
        ]

        send_future = self._pick_client.send_goal_async(goal)
        if not self._await_future(send_future, self._service_timeout_sec):
            return None
        goal_handle = send_future.result()
        if not goal_handle.accepted:
            self.get_logger().error("cluster push goal rejected")
            return None
        result_future = goal_handle.get_result_async()
        if not self._await_future(result_future, self._action_timeout_sec):
            self.get_logger().error("cluster push action timed out")
            return None
        return result_future.result().result

    # ----- order book processing -----------------------------------------

    def _process_order_book(self, order: OrderBook, phase: str) -> bool:
        # 한 OrderBook을 끝까지 처리. primary와 verify 라운드 모두 이 메서드를
        # 공유한다. phase 문자열은 로그/state info용 (예: "primary", "verify1").
        # ABORT/safety_stop이면 False, 정상 완주(또는 주문 소진)면 True.
        while order.has_remaining() and not self._stop_event.is_set():
            self._set_state(TaskState.DETECT, phase)
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

            # 한국어: cluster check — candidate가 군집 상태면 closed-gripper
            # push로 분산시킨 뒤 continue하여 재관측. cluster_enabled=False
            # 면 건너뛰고 일반 pick으로 진행. 같은 클래스에서 push 횟수
            # 상한 초과 시 일반 pick으로 fallback (push 후에도 군집이 유지
            # 되는 케이스 무한루프 방지).
            if (
                self._cluster_enabled
                and self._cluster_push_counts.get(target_class, 0)
                < self._max_cluster_pushes_per_class
            ):
                # 한국어: push z = grasp z + cluster_push_z_offset_mm.
                # grasp z = base_z + per_class_z_offset (pick_offsets.yaml).
                # 두 보정을 합쳐 cluster_policy에 전달하면 plan.entry/push_end
                # 의 z가 곧바로 절대 push 높이가 된다.
                push_z_total_offset = (
                    self._per_class_z_offset_mm.get(target_class, 0.0)
                    + self._cluster_push_z_offset_mm
                )
                cluster_plan = choose_cluster_plan(
                    objects_msg.objects,
                    candidate,
                    self._workspace,
                    cluster_dist_threshold_mm=self._cluster_dist_threshold_mm,
                    candidate_offset_mm=self._cluster_candidate_offset_mm,
                    push_scale=self._cluster_push_scale,
                    push_z_offset_mm=push_z_total_offset,
                    conf_gate=self._conf_gate,
                    min_depth_mm=self._min_depth_mm,
                )
                if cluster_plan is not None:
                    self._cluster_push_counts[target_class] = (
                        self._cluster_push_counts.get(target_class, 0) + 1
                    )
                    self._set_state(
                        TaskState.CLUSTER_PUSH,
                        f"{target_class} dist={cluster_plan.neighbor_distance_mm:.1f}mm "
                        f"#{self._cluster_push_counts[target_class]}",
                    )
                    self.get_logger().info(
                        f"cluster push for {target_class}: "
                        f"target=({candidate.base_xyz.x:.1f},{candidate.base_xyz.y:.1f}) "
                        f"neighbor_dist={cluster_plan.neighbor_distance_mm:.1f}mm "
                        f"entry={cluster_plan.entry_xyz_mm} "
                        f"push_end={cluster_plan.push_end_xyz_mm}"
                    )
                    push_result = self._send_cluster_push_goal(cluster_plan)
                    if push_result is None:
                        # push 자체가 실패(서버 미가용/타임아웃)이면 ABORT로
                        # 처리. workspace 위반 등은 cluster_policy에서 사전
                        # 차단되므로 여기 도달하면 보통 인프라 문제.
                        self._set_state(TaskState.ABORTED, "cluster_push_failure")
                        self._publish_result(False, "cluster_push_failure")
                        return False
                    if not push_result.success:
                        # push가 motion fail 등으로 실패한 경우, 일반 pick으로
                        # fallback. cluster 카운트는 이미 증가했으므로 다음
                        # 루프에서 같은 target에 push가 반복되지는 않는다.
                        self.get_logger().warn(
                            f"cluster push failed code={push_result.failure_code} "
                            f"({push_result.message}) — fall through to pick"
                        )
                    else:
                        # push 성공 시 settle 후 재관측 사이클로.
                        if self._inter_pick_delay_sec > 0.0:
                            time.sleep(self._inter_pick_delay_sec)
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
                return False

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

            # failure_code 매핑: 2=grasp_not_detected -> RETRY_PICK 또는
            # SKIP_CLASS, 3=motion / 5=workspace / 1=approach -> ABORT,
            # 4=safety_stop -> ABORT (자세한 정책은 retry_policy.py 참고).
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
                return False
            # RETRY_PICK / RETRY_DETECT: just loop and try again

        if self._stop_event.is_set():
            self._set_state(TaskState.SAFETY_STOP)
            self._publish_result(False, "safety_stop")
            return False
        return True

    # ----- main loop -----------------------------------------------------

    def _run(self) -> None:
        self._set_state(TaskState.INIT)
        # 사이클 시작 시 cluster push 카운터 리셋 — 이전 사이클 상태가
        # 누적되어 새 주문 처리에서 push가 차단되는 것을 방지.
        self._cluster_push_counts = {}
        try:
            order: OrderBook = self._order_provider.fetch()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"order fetch failed: {exc}")
            self._set_state(TaskState.ABORTED, "order_fetch_failed")
            self._publish_result(False, "order_fetch_failed")
            return

        # 원래 주문 수량을 보존해 verification 라운드의 remaining 계산에 사용.
        ordered_counts = dict(order.counts)

        if not self._call_home():
            self._set_state(TaskState.ABORTED, "home_failed")
            self._publish_result(False, "home_failed")
            return
        if self._inter_pick_delay_sec > 0.0:
            time.sleep(self._inter_pick_delay_sec)

        # 사이클 시작 시점의 검출 카운트. verification이 켜져 있으면 사용.
        initial_counts: Optional[Dict[str, int]] = None
        if self._verification_enabled:
            objects_msg = self._detect_once()
            if objects_msg is None:
                self._set_state(TaskState.ABORTED, "initial_verify_detect_failed")
                self._publish_result(False, "initial_verify_detect_failed")
                return
            initial_counts = self._count_detected_objects(objects_msg)
            self.get_logger().info(f"initial detected counts: {initial_counts}")

        # Primary round — 주문 그대로 처리.
        if not self._process_order_book(order, "primary"):
            return

        # Verification rounds — 홈→detect→remaining 계산→부족분 픽을 반복.
        # 각 라운드 진입 시 _detect_counts_from_home이 홈 이동 + detect_once 수행.
        # remaining=0 즉시 break하여 불필요한 라운드 회피.
        final_counts: Optional[Dict[str, int]] = None
        correction_order: Optional[OrderBook] = None
        if self._verification_enabled and initial_counts is not None:
            for round_index in range(max(0, self._max_verification_rounds)):
                self._set_state(TaskState.VERIFY, f"round={round_index + 1}")
                final_counts = self._detect_counts_from_home(
                    f"final round {round_index + 1}"
                )
                if final_counts is None:
                    self._set_state(TaskState.ABORTED, "final_verify_detect_failed")
                    self._publish_result(False, "final_verify_detect_failed")
                    return

                remaining_counts = self._remaining_from_verification(
                    ordered_counts, initial_counts, final_counts
                )
                self.get_logger().info(
                    "verification remaining counts: "
                    f"ordered={ordered_counts} initial={initial_counts} "
                    f"final={final_counts} remaining={remaining_counts}"
                )
                correction_order = OrderBook(counts=remaining_counts)
                if not correction_order.has_remaining():
                    break
                if not self._process_order_book(
                    correction_order, f"verify{round_index + 1}"
                ):
                    return

        self._set_state(TaskState.DONE)
        if correction_order is not None and correction_order.has_remaining():
            # max_verification_rounds 다 돌아도 보정 실패한 부족분 보고.
            self._publish_result(
                False,
                f"counts={order.counts} correction={correction_order.counts} "
                f"skipped={list(correction_order.skipped)}",
            )
        else:
            self._publish_result(
                order.all_done(),
                f"counts={order.counts} final_counts={final_counts} "
                f"skipped={list(order.skipped)}",
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node: Optional[TaskManagerNode] = None
    try:
        node = TaskManagerNode()
        # MultiThreadedExecutor를 쓰는 이유: worker thread가 future를 polling
        # 하는 동안에도 ReentrantCallbackGroup의 다른 콜백(서비스/액션 응답,
        # /task/start 트리거 등)이 별도 thread에서 동시에 디스패치되어야 한다.
        # SingleThreadedExecutor면 worker가 sleep 중일 때 콜백이 막혀 future가
        # 영원히 done이 되지 않는다.
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
