# 한국어 요약:
#   firebase_status_bridge의 Supabase 포트.
#   /task/status, /task/result, /conveyor/place_ready를 구독해서 robot_state
#   필드를 robot_session.current 행에 미러링한다. CobotDbManager가 lazy 클라이언트
#   생성 + .env 로딩 + 에러 swallow를 담당한다 — 따라서 여기에는 Supabase 관련
#   import이나 try/except가 거의 없다.
"""Mirror cobot_task_manager progress to robot_session.current in Supabase.

Functional twin of cobot_voice.firebase_status_bridge — same subscriptions,
same _STATUS_TO_ROBOT_STATE mapping, same parse functions. Only the write
backend differs: Supabase upsert via cobot_db.CobotDbManager instead of
firebase_admin.

Failure modes
-------------

* If cobot_db is not importable (e.g. supabase-py missing), the node
  starts and silently no-ops on every write. The robot pipeline is
  unaffected.
* If credentials are missing (.env / SUPABASE_URL / SUPABASE_KEY),
  CobotDbManager init succeeds but the first write raises; we catch and
  warn, then keep spinning.
* The launch arg ``enable_supabase_status_bridge`` (default true) lets
  operators skip the node entirely.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

try:
    from cobot_db import CobotDbManager  # type: ignore
except ImportError:
    CobotDbManager = None  # type: ignore


# /task/status leading-token -> robot_state value.
# task_manager의 내부 상태 토큰을 web UI가 이해하는 robot_state 값으로 매핑.
# firebase_status_bridge와 1:1 동일 — web 쪽 표시 의미가 그대로다.
_STATUS_TO_ROBOT_STATE = {
    "init": "detecting",
    "detect": "detecting",
    "select_target": "picking",
    "pick_and_place": "picking",
    "done": "task_done",
    "aborted": "error",
    "safety_stop": "error",
    # "idle"은 의도적으로 미러링하지 않는다 — voice flow가 idle을 직접 관리.
}

_NUT_CLASSES = frozenset({"almond", "cashew", "pistachio", "walnut"})


def parse_status(msg_data):
    """Split a /task/status message into (state_token, info_str).

    >>> parse_status("detect")
    ('detect', '')
    >>> parse_status("pick_and_place cashew")
    ('pick_and_place', 'cashew')
    """
    text = (msg_data or "").strip()
    if not text:
        return "", ""
    parts = text.split(" ", 1)
    state = parts[0]
    info = parts[1].strip() if len(parts) > 1 else ""
    return state, info


def parse_result(msg_data):
    """Split a /task/result message into (outcome, info_str)."""
    text = (msg_data or "").strip()
    if not text:
        return "", ""
    parts = text.split(" ", 1)
    outcome = parts[0].lower()
    info = parts[1].strip() if len(parts) > 1 else ""
    return outcome, info


class SupabaseStatusBridge(Node):
    def __init__(self):
        super().__init__("supabase_status_bridge")

        self.declare_parameter("status_topic", "/task/status")
        self.declare_parameter("result_topic", "/task/result")
        self.declare_parameter("place_ready_topic", "/conveyor/place_ready")
        # db_env_path 빈 문자열이면 노드 실행 디렉터리의 .env 사용 (cobot_db 기본).
        self.declare_parameter("db_env_path", "")

        status_topic = str(self.get_parameter("status_topic").value)
        result_topic = str(self.get_parameter("result_topic").value)
        place_topic = str(self.get_parameter("place_ready_topic").value)

        self._target_class = ""
        self._last_place_ready = False

        # CobotDbManager 인스턴스 lazy init: import 실패도, env 누락도, 로봇
        # 파이프라인에 영향 주면 안 된다. None이면 _publish가 silent no-op.
        self._db = None
        if CobotDbManager is None:
            self.get_logger().warn(
                "cobot_db not importable; supabase_status_bridge will no-op. "
                "Install with `pip install supabase python-dotenv`."
            )
        else:
            env_path = (
                str(self.get_parameter("db_env_path").value).strip() or None
            )
            try:
                self._db = CobotDbManager(env_path=env_path)
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn(
                    f"CobotDbManager init failed ({exc}); bridge will no-op"
                )

        self.create_subscription(String, status_topic, self._on_status, 10)
        self.create_subscription(String, result_topic, self._on_result, 10)
        self.create_subscription(Bool, place_topic, self._on_place_ready, 10)

        self.get_logger().info(
            "SupabaseStatusBridge active: %s + %s + %s -> robot_session.current"
            % (status_topic, result_topic, place_topic)
        )
        self.get_logger().info(
            "Supabase writes are best-effort; robot pipeline is unaffected by outages."
        )

    # ----- subscriptions -----

    def _on_status(self, msg):
        state_token, info = parse_status(msg.data)
        if not state_token:
            return

        robot_state = _STATUS_TO_ROBOT_STATE.get(state_token)
        if robot_state is None:
            return

        fields = {}
        if info and info in _NUT_CLASSES:
            self._target_class = info
            fields["robot_target_class"] = info
        elif robot_state == "error" and info:
            fields["error"] = info
        elif self._target_class and robot_state in {"picking", "placing"}:
            # carry the most-recent target through subsequent picking/placing updates.
            fields["robot_target_class"] = self._target_class

        self._publish(robot_state, **fields)

    def _on_result(self, msg):
        outcome, info = parse_result(msg.data)
        if not outcome:
            return

        if outcome == "failure":
            self._publish("error", error=info or "task_failed")
            return

        # success: mirror as task_done; preserve target context.
        fields = {}
        if self._target_class:
            fields["robot_target_class"] = self._target_class
        self._publish("task_done", **fields)

    def _on_place_ready(self, msg):
        edge = bool(msg.data) and not self._last_place_ready
        self._last_place_ready = bool(msg.data)
        if not edge:
            return

        # PLACING과 CONVEYOR_MOVING이 동일 에지에서 같이 발화 — firebase 버전과 동일.
        fields = {}
        if self._target_class:
            fields["robot_target_class"] = self._target_class
        self._publish("placing", **fields)
        self._publish("conveyor_moving", **fields)

    # ----- output -----

    def _publish(self, robot_state, **fields):
        log_kv = " ".join(f"{k}={v!r}" for k, v in fields.items())
        self.get_logger().info(
            f"supabase_status_bridge: robot_state={robot_state} {log_kv}".rstrip()
        )
        if self._db is None:
            return
        try:
            self._db.set_robot_state(robot_state, **fields)
        except Exception as exc:  # noqa: BLE001
            # 모든 Supabase 측 예외를 swallow — 로봇 파이프라인 보호.
            self.get_logger().warning(
                f"supabase publish failed (continuing): {exc}"
            )


def main():
    rclpy.init()
    node = SupabaseStatusBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
