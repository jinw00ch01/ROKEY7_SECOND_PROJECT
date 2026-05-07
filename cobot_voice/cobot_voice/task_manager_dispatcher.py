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
        logger.warning(
            "dispatch_to_task_manager: order missing or success=false; "
            "not triggering /task/start"
        )
        return False

    try:
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
    if "success=True" in result.stdout:
        logger.info(f"{START_SERVICE} accepted (request_id={order.get('request_id', '')!r})")
        return True

    logger.error(
        f"{START_SERVICE} did not return success=True. stdout={result.stdout!r}"
    )
    return False
