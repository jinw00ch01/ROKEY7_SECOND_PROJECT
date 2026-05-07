# 한국어 요약:
#   cobot_task_manager의 진행 상황을 Firestore /robot_session/current 문서의
#   robot_state 필드로 미러링하는 노드. /task/status, /task/result,
#   /conveyor/place_ready 토픽을 구독하여 매핑 테이블을 통해 web UI용
#   상태값으로 변환한다. Firebase 미설치/네트워크 단절 시 silent no-op으로
#   처리하며, 로봇 파이프라인은 절대 블록하지 않는다.
"""Mirror cobot_task_manager progress to /robot_session/current in Firestore.

The web UI subscribes to /robot_session/current to render the demo. The
voice flow already populates ``display_state`` (idle, asking_state, ...,
completed). During the actual robot pickup, ``display_state`` stays at
``dispatching`` until the loop ends, so the dashboard had no way to show
per-pick progress.

This bridge node fills that gap:

  /task/status              std_msgs/String   "<state> [<info>]"
  /task/result              std_msgs/String   "<success|failure> [<info>]"
  /conveyor/place_ready     std_msgs/Bool     False -> True edge

are translated into Firestore writes via
``firebase_bridge.publish_robot_progress``, which lands in a separate
``robot_state`` field so the voice flow's ``display_state`` is left
alone.

Failure modes
-------------

* If Firebase credentials / firebase_admin / network are missing,
  ``firebase_bridge`` flips an internal flag and silently no-ops on
  every subsequent write. The bridge node keeps spinning; the robot
  pipeline is unaffected.
* If this node crashes outright, ``task_manager_node`` and
  ``robot_control_node`` keep running — they're separate processes.
* The launch arg ``enable_firebase_status_bridge`` (default true) lets
  operators skip the node entirely.

Granularity note
----------------

``pick_and_place`` covers approach -> grasp -> transit -> place inside
the action server. The bridge cannot distinguish those stages today
because only the final action result is observable from outside.
``placing`` is therefore inferred from the ``/conveyor/place_ready``
True edge (TCP at place point, gripper opening, conveyor about to
advance) — same edge that triggers ``conveyor_moving``. Both states
fire back-to-back through the firebase_bridge worker queue.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from cobot_voice.firebase_bridge import publish_robot_progress


# /task/status leading-token -> robot_state value
# task_manager의 내부 상태 토큰을 web UI가 이해하는 robot_state 값으로 매핑.
# action server가 stage별 진행을 외부로 노출하지 않으므로 토큰 단위로 추정한다.
_STATUS_TO_ROBOT_STATE = {
    "init": "detecting",
    "detect": "detecting",
    "select_target": "picking",
    "pick_and_place": "picking",
    "done": "task_done",
    "aborted": "error",
    "safety_stop": "error",
    # "idle" is intentionally not mirrored — voice flow handles idle.
}

# nut class names emitted by task_manager (single-token info field)
_NUT_CLASSES = frozenset({"almond", "cashew", "pistachio", "walnut"})


def parse_status(msg_data):
    """Split a /task/status message into (state_token, info_str).

    >>> parse_status("detect")
    ('detect', '')
    >>> parse_status("pick_and_place cashew")
    ('pick_and_place', 'cashew')
    >>> parse_status("aborted home_failed")
    ('aborted', 'home_failed')
    >>> parse_status("")
    ('', '')
    """
    text = (msg_data or "").strip()
    if not text:
        return "", ""
    parts = text.split(" ", 1)
    state = parts[0]
    info = parts[1].strip() if len(parts) > 1 else ""
    return state, info


def parse_result(msg_data):
    """Split a /task/result message into (outcome, info_str).

    >>> parse_result("success counts={'walnut': 1}")
    ('success', "counts={'walnut': 1}")
    >>> parse_result("failure home_failed")
    ('failure', 'home_failed')
    """
    text = (msg_data or "").strip()
    if not text:
        return "", ""
    parts = text.split(" ", 1)
    outcome = parts[0].lower()
    info = parts[1].strip() if len(parts) > 1 else ""
    return outcome, info


class FirebaseStatusBridge(Node):
    def __init__(self):
        super().__init__("firebase_status_bridge")

        self.declare_parameter("status_topic", "/task/status")
        self.declare_parameter("result_topic", "/task/result")
        self.declare_parameter("place_ready_topic", "/conveyor/place_ready")

        status_topic = str(self.get_parameter("status_topic").value)
        result_topic = str(self.get_parameter("result_topic").value)
        place_topic = str(self.get_parameter("place_ready_topic").value)

        self._target_class = ""
        self._last_place_ready = False

        self.create_subscription(String, status_topic, self._on_status, 10)
        self.create_subscription(String, result_topic, self._on_result, 10)
        self.create_subscription(Bool, place_topic, self._on_place_ready, 10)

        self.get_logger().info(
            "FirebaseStatusBridge active: %s + %s + %s -> /robot_session/current"
            % (status_topic, result_topic, place_topic)
        )
        self.get_logger().info(
            "Firestore writes are best-effort; robot pipeline is unaffected by Firebase outages."
        )

    # ----- subscriptions -----

    def _on_status(self, msg):
        state_token, info = parse_status(msg.data)
        if not state_token:
            return

        robot_state = _STATUS_TO_ROBOT_STATE.get(state_token)
        if robot_state is None:
            # unknown / not-mirrored (e.g. "idle"); no-op
            return

        fields = {}
        if info and info in _NUT_CLASSES:
            self._target_class = info
            fields["target_class"] = info
        elif robot_state == "error" and info:
            fields["error"] = info
        elif self._target_class and robot_state in {"picking", "placing"}:
            # carry the most-recent target through subsequent picking/placing updates
            fields["target_class"] = self._target_class

        self._publish(robot_state, **fields)

    def _on_result(self, msg):
        outcome, info = parse_result(msg.data)
        if not outcome:
            return

        if outcome == "failure":
            self._publish("error", last_result=msg.data, error=info or "task_failed")
            return

        # success: mirror as task_done; preserve target_class context.
        fields = {"last_result": msg.data}
        if self._target_class:
            fields["target_class"] = self._target_class
        self._publish("task_done", **fields)

    def _on_place_ready(self, msg):
        edge = bool(msg.data) and not self._last_place_ready
        self._last_place_ready = bool(msg.data)
        if not edge:
            return

        # PLACING and CONVEYOR_MOVING fire on the same edge in the current
        # architecture (see module docstring). Emit them back-to-back so
        # the web UI sees both.
        # action server가 placing/conveyor 진행을 별도 신호로 노출하지 않기에
        # /conveyor/place_ready의 False->True 에지 한 번에 두 상태를 연속 발행한다.
        fields = {}
        if self._target_class:
            fields["target_class"] = self._target_class
        self._publish("placing", **fields)
        self._publish("conveyor_moving", **fields)

    # ----- output -----

    def _publish(self, robot_state, **fields):
        # Logged so operators can see what we're sending without having
        # to subscribe to Firebase. Best-effort; never raises.
        log_kv = " ".join(f"{k}={v!r}" for k, v in fields.items())
        self.get_logger().info(
            f"firebase_status_bridge: robot_state={robot_state} {log_kv}".rstrip()
        )
        try:
            publish_robot_progress(robot_state, **fields)
        except Exception as exc:  # pragma: no cover - defensive
            # Firebase 측 예외는 경고만 남기고 노드는 계속 spin — 로봇 파이프라인 보호.
            self.get_logger().warning(
                f"firebase publish failed (continuing): {exc}"
            )


def main():
    rclpy.init()
    node = FirebaseStatusBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
