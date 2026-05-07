"""Action server + utility services for the Doosan + RG2 stack.

Exposes:
  - Action  : /robot/pick_and_place        (cobot_msgs/PickAndPlace)
  - Service : /robot/home                  (std_srvs/Trigger)
  - Service : /robot/stop                  (std_srvs/Trigger)

Backends are selected via parameters so this node can run in three flavors
without code changes:
  motion_backend  : real | mock
  gripper_backend : modbus | mock | tool_dio
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

from cobot_msgs.action import PickAndPlace
from cobot_msgs.srv import GetCurrentPose

from .doosan_motion_client import make_motion_client
from .gripper_controller import make_gripper, wait_until_idle
from .motion_sequence import MotionConfig, execute_pick_and_place


class RobotControlNode(Node):
    def __init__(self) -> None:
        # Robot ID is the namespace per Doosan convention - declare without
        # namespace here, then the launch file places this node in the right
        # namespace using the `namespace` argument.
        super().__init__("robot_control_node")

        # ----- parameters ----------------------------------------------------
        self.declare_parameter("robot_id", "dsr01")
        self.declare_parameter("robot_model", "m0609")
        self.declare_parameter("motion_backend", "mock")     # real | mock
        self.declare_parameter("gripper_backend", "mock")    # modbus | mock | tool_dio
        self.declare_parameter("gripper_ip", "192.168.1.1")
        self.declare_parameter("gripper_port", 502)
        self.declare_parameter("gripper_force_x10", 200)     # 1/10 N units (200 = 20 N)
        self.declare_parameter("gripper_open_width_x10", 1100)  # 1/10 mm (1100 = 110 mm)

        self.declare_parameter("home_joints_deg", [0.0, 0.0, 90.0, 0.0, 90.0, 0.0])
        self.declare_parameter("approach_offset_z_mm", 80.0)
        self.declare_parameter("velocity", 60.0)
        self.declare_parameter("acceleration", 60.0)
        self.declare_parameter("velocity_slow", 30.0)
        self.declare_parameter("acceleration_slow", 30.0)
        self.declare_parameter("grip_settle_timeout_sec", 5.0)
        self.declare_parameter("grasp_local_offset_xy_mm", [0.0, 0.0])

        self.declare_parameter("action_name", "/robot/pick_and_place")
        self.declare_parameter("home_service_name", "/robot/home")
        self.declare_parameter("stop_service_name", "/robot/stop")
        self.declare_parameter("pose_service_name", "/robot/get_current_pose")
        self.declare_parameter("doosan_pose_service", "/dsr01/system/get_current_pose")
        self.declare_parameter("pose_passthrough_timeout_sec", 2.0)
        self.declare_parameter("place_ready_topic", "/conveyor/place_ready")
        self.declare_parameter("place_y_margin_mm", 3.0)
        self.declare_parameter("place_ready_publish_period_sec", 0.1)

        # ----- backends ------------------------------------------------------
        motion_backend = str(self.get_parameter("motion_backend").value)
        gripper_backend = str(self.get_parameter("gripper_backend").value)
        robot_id = str(self.get_parameter("robot_id").value)
        robot_model = str(self.get_parameter("robot_model").value)

        if motion_backend == "real":
            self.get_logger().info(
                f"Initializing DSR_ROBOT2 (id={robot_id}, model={robot_model})"
            )
            self._motion = make_motion_client(
                "real",
                ros_node=self,
                robot_id=robot_id,
                robot_model=robot_model,
                velocity=float(self.get_parameter("velocity").value),
                acceleration=float(self.get_parameter("acceleration").value),
            )
        else:
            self.get_logger().warn(
                f"Using MOCK motion backend ({motion_backend!r})"
            )
            self._motion = make_motion_client(
                "mock",
                velocity=float(self.get_parameter("velocity").value),
                acceleration=float(self.get_parameter("acceleration").value),
            )

        if gripper_backend == "modbus":
            self.get_logger().info(
                f"Initializing Modbus RG2 at "
                f"{self.get_parameter('gripper_ip').value}:"
                f"{self.get_parameter('gripper_port').value} "
                f"(force={int(self.get_parameter('gripper_force_x10').value)/10}N)"
            )
            self._gripper = make_gripper(
                "modbus",
                ip=str(self.get_parameter("gripper_ip").value),
                port=int(self.get_parameter("gripper_port").value),
                force_x10=int(self.get_parameter("gripper_force_x10").value),
                max_width_x10=int(self.get_parameter("gripper_open_width_x10").value),
            )
        else:
            self.get_logger().warn(
                f"Using MOCK gripper backend ({gripper_backend!r})"
            )
            self._gripper = make_gripper("mock")

        # ----- motion config -------------------------------------------------
        self._cfg = MotionConfig(
            home_joints_deg=list(self.get_parameter("home_joints_deg").value),
            approach_offset_z_mm=float(self.get_parameter("approach_offset_z_mm").value),
            velocity=float(self.get_parameter("velocity").value),
            acceleration=float(self.get_parameter("acceleration").value),
            velocity_slow=float(self.get_parameter("velocity_slow").value),
            acceleration_slow=float(self.get_parameter("acceleration_slow").value),
            grip_settle_timeout_sec=float(self.get_parameter("grip_settle_timeout_sec").value),
            grasp_local_offset_xy_mm=list(self.get_parameter("grasp_local_offset_xy_mm").value),
            place_y_margin_mm=float(self.get_parameter("place_y_margin_mm").value),
        )

        # ----- ROS interfaces ------------------------------------------------
        service_cb_group = ReentrantCallbackGroup()

        self._stop_event = threading.Event()
        self._busy_lock = threading.Lock()
        self._place_ready_lock = threading.Lock()
        self._place_ready = False

        self._place_ready_pub = self.create_publisher(
            Bool,
            str(self.get_parameter("place_ready_topic").value),
            10,
        )
        self._place_ready_timer = self.create_timer(
            float(self.get_parameter("place_ready_publish_period_sec").value),
            self._publish_place_ready,
        )

        # Action server lives on a dedicated node + executor so its goal
        # acceptance and execution are not gated by traffic on the main
        # node's executor (DSR_ROBOT2 init creates many subscribers and
        # clients on the main node). Reentrant group + busy_lock guards
        # against concurrent goals while letting goal_callback run while
        # an execute_callback is in flight.
        # `use_global_arguments=False` prevents this helper node from
        # inheriting the launch file's `__node:=robot_control_node`
        # remap, which would otherwise rename it to `robot_control_node`
        # and break service routing.
        self._action_node = Node(
            "robot_action_helper",
            namespace=self.get_namespace(),
            use_global_arguments=False,
        )
        action_cb_group = ReentrantCallbackGroup()
        self._action_server = ActionServer(
            self._action_node,
            PickAndPlace,
            str(self.get_parameter("action_name").value),
            execute_callback=self._execute_pick_and_place,
            goal_callback=self._on_goal,
            cancel_callback=self._on_cancel,
            callback_group=action_cb_group,
        )
        self._action_executor = MultiThreadedExecutor(num_threads=4)
        self._action_executor.add_node(self._action_node)
        self._action_thread = threading.Thread(
            target=self._action_executor.spin,
            daemon=True,
        )
        self._action_thread.start()

        self._home_service = self.create_service(
            Trigger,
            str(self.get_parameter("home_service_name").value),
            self._handle_home,
            callback_group=service_cb_group,
        )
        self._stop_service = self.create_service(
            Trigger,
            str(self.get_parameter("stop_service_name").value),
            self._handle_stop,
            callback_group=service_cb_group,
        )
        # Pose passthrough lives on a dedicated node + executor so that
        # DSR_ROBOT2 traffic during pick_and_place (which churns ros2 service
        # clients on the main node) doesn't starve this callback queue.
        # Symptom we're avoiding: after the first /robot/pick_and_place
        # action completes, the main node's executor stops dispatching
        # /robot/get_current_pose, causing perception's detect_once to
        # time out.
        from dsr_msgs2.srv import GetCurrentPose as DoosanGetCurrentPose
        self._doosan_get_pose_type = DoosanGetCurrentPose

        self._pose_node = Node(
            "robot_pose_helper",
            namespace=self.get_namespace(),
            use_global_arguments=False,
        )
        # Use a reentrant callback group so the service handler can block
        # waiting for the doosan client response while the executor's other
        # thread processes that response.
        pose_cb_group = ReentrantCallbackGroup()
        self._doosan_pose_client = self._pose_node.create_client(
            DoosanGetCurrentPose,
            str(self.get_parameter("doosan_pose_service").value),
            callback_group=pose_cb_group,
        )
        self._pose_service = self._pose_node.create_service(
            GetCurrentPose,
            str(self.get_parameter("pose_service_name").value),
            self._handle_get_current_pose,
            callback_group=pose_cb_group,
        )
        # MultiThreaded with >= 2 workers: one for the service handler, one
        # for the client response. SingleThreadedExecutor would deadlock
        # because the handler blocks waiting for the response and there is
        # no second worker to dispatch it.
        self._pose_executor = MultiThreadedExecutor(num_threads=2)
        self._pose_executor.add_node(self._pose_node)
        self._pose_thread = threading.Thread(
            target=self._pose_executor.spin,
            daemon=True,
        )
        self._pose_thread.start()
        self.get_logger().info(
            f"robot_control_node ready (action={self.get_parameter('action_name').value})"
        )

    # ----- action lifecycle --------------------------------------------------

    def _on_goal(self, _goal_request) -> GoalResponse:
        if self._busy_lock.locked():
            self.get_logger().warn("Reject pick_and_place: another goal is in progress")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _on_cancel(self, _goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    def _execute_pick_and_place(self, goal_handle):
        result_msg = PickAndPlace.Result()
        if not self._busy_lock.acquire(blocking=False):
            result_msg.success = False
            result_msg.failure_code = 3
            result_msg.message = "robot busy"
            goal_handle.abort()
            return result_msg

        try:
            self._stop_event.clear()
            goal = goal_handle.request

            def feedback_cb(stage: str) -> None:
                fb = PickAndPlace.Feedback()
                fb.stage = stage
                goal_handle.publish_feedback(fb)
                self.get_logger().info(f"[stage] {stage}")

            def place_ready_cb(ready: bool, reason: str) -> None:
                self._set_place_ready(ready, reason)

            def is_cancelled() -> bool:
                return goal_handle.is_cancel_requested or self._stop_event.is_set()

            success, code, message = execute_pick_and_place(
                motion=self._motion,
                gripper=self._gripper,
                cfg=self._cfg,
                grasp_xyz_mm=[goal.grasp_xyz.x, goal.grasp_xyz.y, goal.grasp_xyz.z],
                grasp_yaw_rad=float(goal.grasp_yaw),
                return_xyz_mm=[goal.return_xyz.x, goal.return_xyz.y, goal.return_xyz.z],
                return_zyz_deg=[
                    float(goal.return_zyz_deg[0]),
                    float(goal.return_zyz_deg[1]),
                    float(goal.return_zyz_deg[2]),
                ],
                pre_grasp_width_mm=float(goal.pre_grasp_width_mm),
                feedback_cb=feedback_cb,
                place_ready_cb=place_ready_cb,
                is_cancelled=is_cancelled,
            )

            result_msg.success = success
            result_msg.failure_code = int(code)
            result_msg.message = message
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
            elif success:
                goal_handle.succeed()
            else:
                goal_handle.abort()
            return result_msg
        finally:
            self._set_place_ready(False, "pick_and_place_finished")
            self._busy_lock.release()

    # ----- services ----------------------------------------------------------

    def _handle_home(self, _request, response):
        try:
            self._motion.move_joint(self._cfg.home_joints_deg)
            response.success = True
            response.message = "moved to home"
        except Exception as exc:  # noqa: BLE001
            response.success = False
            response.message = f"home failed: {exc}"
        return response

    def _handle_stop(self, _request, response):
        self._stop_event.set()
        self._set_place_ready(False, "stop")
        try:
            self._gripper.open()
            wait_until_idle(self._gripper, timeout_sec=2.0)
            response.success = True
            response.message = "stop signaled"
        except Exception as exc:  # noqa: BLE001
            response.success = False
            response.message = f"stop partial: {exc}"
        return response

    def _set_place_ready(self, ready: bool, reason: str = "") -> None:
        with self._place_ready_lock:
            changed = self._place_ready != bool(ready)
            self._place_ready = bool(ready)
        if changed:
            suffix = f" ({reason})" if reason else ""
            self.get_logger().info(f"[place_ready] {self._place_ready}{suffix}")
        self._publish_place_ready()

    def _publish_place_ready(self) -> None:
        msg = Bool()
        with self._place_ready_lock:
            msg.data = bool(self._place_ready)
        self._place_ready_pub.publish(msg)

    def _handle_get_current_pose(self, _request, response):
        log = self.get_logger()
        log.info("[pose] handler entered")
        try:
            timeout = float(self.get_parameter("pose_passthrough_timeout_sec").value)
            log.info(f"[pose] timeout={timeout}")
            log.info("[pose] checking service availability...")
            if not self._doosan_pose_client.service_is_ready():
                # Avoid wait_for_service since it has been observed to hang
                # under load. We just check ready once.
                log.warn("[pose] doosan service not ready (service_is_ready=False)")
                response.success = False
                response.message = (
                    f"{self.get_parameter('doosan_pose_service').value} not ready"
                )
                return response
            log.info("[pose] service ready, calling call_async")
            req = self._doosan_get_pose_type.Request()
            req.space_type = 1  # ROBOT_SPACE_TASK -> TCP posx
            future = self._doosan_pose_client.call_async(req)
            log.info("[pose] call_async returned, polling future.done")

            # Poll instead of add_done_callback: rclpy.task.Future's
            # done-callback can race silently when the future is set in
            # one thread and the callback is registered in another, even
            # though the callback API is supposed to handle it. Polling
            # `.done()` is what perception_transform_node uses too.
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not future.done():
                time.sleep(0.01)
            log.info(f"[pose] poll done, future.done={future.done()}")
            if not future.done():
                response.success = False
                response.message = "doosan get_current_pose call timed out"
                return response
            doosan_resp = future.result()
            log.info(f"[pose] response received: success={doosan_resp.success}")
            if not doosan_resp.success:
                response.success = False
                response.message = "doosan get_current_pose returned failure"
                return response
            posx = list(doosan_resp.pos)
            if len(posx) < 6:
                response.success = False
                response.message = f"unexpected posx: {posx!r}"
                return response
            response.xyz_mm.x = float(posx[0])
            response.xyz_mm.y = float(posx[1])
            response.xyz_mm.z = float(posx[2])
            response.zyz_deg = [float(posx[3]), float(posx[4]), float(posx[5])]
            response.success = True
            response.message = ""
            log.info(f"[pose] OK posx={posx}")
        except Exception as exc:  # noqa: BLE001
            response.success = False
            response.message = f"get_current_pose failed: {exc}"
            log.error(f"[pose] exception: {exc}")
        return response

    def shutdown(self) -> None:
        try:
            self._action_executor.shutdown()
        except Exception:
            pass
        try:
            self._action_node.destroy_node()
        except Exception:
            pass
        try:
            self._pose_executor.shutdown()
        except Exception:
            pass
        try:
            self._pose_node.destroy_node()
        except Exception:
            pass
        try:
            self._gripper.shutdown()
        except Exception:
            pass
        try:
            self._motion.shutdown()
        except Exception:
            pass


def main(args=None) -> None:
    rclpy.init(args=args)
    node: Optional[RobotControlNode] = None
    try:
        node = RobotControlNode()
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
            node.shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
