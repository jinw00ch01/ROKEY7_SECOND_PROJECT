# 한국어 요약:
#   추천이 성공한 주문에 대해 cobot_task_manager의 /task/start 서비스를 호출해
#   로봇 픽업을 트리거하는 dispatch_callback 모듈. ROS 노드로 만들지 않기 위해
#   subprocess.run으로 `ros2 service call`을 실행하며, order의 success=False면
#   호출을 거부한다. 응답 stdout에서 "success=True" 문자열을 검색해 성공 여부를 판정한다.
"""Trigger cobot_task_manager's /task/start after a successful recommendation.

Designed as a `dispatch_callback` for `voice_order_flow.run_recommendation_flow`.
Refuses to dispatch if the order's success flag is false. Calls the service
via `ros2 service call` so this module does not need to be a ROS node.

Phase 3 of the voice -> robot integration. The task_manager must already be
running with `order_source=file` and `file_order_path` pointing at the same
latest_order.json that the voice flow just wrote.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

START_SERVICE = "/task/start"
SERVICE_TYPE = "std_srvs/srv/Trigger"


def dispatch_to_task_manager(
    order: Optional[Mapping] = None, timeout_sec: float = 5.0
) -> bool:
    """Call /task/start so task_manager fetches the latest order and picks.

    Returns True only if the service responded with success=True. Returns
    False (logs warning) for an absent/failed order or a service error;
    never raises.
    """
    if order is None or not order.get("success"):
        # 추천 실패 주문은 로봇 트리거 거부 — 잘못된 픽업 방지.
        logger.warning(
            "dispatch_to_task_manager: order missing or success=false; "
            "not triggering /task/start"
        )
        return False

    try:
        # 이 모듈을 ROS 노드로 만들지 않기 위해 외부 CLI(`ros2 service call`)를 사용.
        result = subprocess.run(
            ["ros2", "service", "call", START_SERVICE, SERVICE_TYPE, "{}"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"{START_SERVICE} call timed out after {timeout_sec}s")
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error(f"{START_SERVICE} call error: {exc}")
        return False

    if result.returncode != 0:
        logger.error(
            f"{START_SERVICE} call failed (rc={result.returncode}): "
            f"stderr={result.stderr!r}"
        )
        return False

    # ros2 service call output looks like:
    #   response:
    #   std_srvs.srv.Trigger_Response(success=True, message='task started')
    # stdout 텍스트에서 "success=True" 부분 문자열을 찾아 성공 여부를 판정한다.
    if "success=True" in result.stdout:
        logger.info(f"{START_SERVICE} accepted (request_id={order.get('request_id', '')!r})")
        return True

    logger.error(
        f"{START_SERVICE} did not return success=True. stdout={result.stdout!r}"
    )
    return False
