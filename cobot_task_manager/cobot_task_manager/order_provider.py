"""Order book for pending nut picks.

Tracks per-class remaining counts plus retry/skip bookkeeping. Three providers
share the `OrderBook` data class:
  - MockOrderProvider returns a fixed dict (Phase A test setup: 2 of each)
  - DBOrderProvider calls cobot_msgs/srv/GetNutOrder (Phase B, server pending)
  - FileOrderProvider reads cobot_voice's latest_order.json (Phase A')
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Protocol


_NUT_CLASSES = frozenset({"almond", "cashew", "pistachio", "walnut"})


@dataclass
class OrderBook:
    counts: Dict[str, int]
    consecutive_detect_misses: Dict[str, int] = field(default_factory=dict)
    consecutive_grasp_failures: Dict[str, int] = field(default_factory=dict)
    skipped: set = field(default_factory=set)

    def has_remaining(self) -> bool:
        return any(
            count > 0 and cls not in self.skipped
            for cls, count in self.counts.items()
        )

    def all_done(self) -> bool:
        return all(
            count == 0 or cls in self.skipped
            for cls, count in self.counts.items()
        )

    def next_class(self, priority: Iterable[str]) -> Optional[str]:
        for cls in priority:
            if cls in self.counts and self.counts[cls] > 0 and cls not in self.skipped:
                return cls
        for cls, count in self.counts.items():
            if count > 0 and cls not in self.skipped:
                return cls
        return None

    def consume_one(self, cls: str) -> None:
        if self.counts.get(cls, 0) > 0:
            self.counts[cls] -= 1
        self.consecutive_detect_misses[cls] = 0
        self.consecutive_grasp_failures[cls] = 0

    def record_detect_miss(self, cls: str) -> int:
        self.consecutive_detect_misses[cls] = self.consecutive_detect_misses.get(cls, 0) + 1
        return self.consecutive_detect_misses[cls]

    def record_grasp_failure(self, cls: str) -> int:
        self.consecutive_grasp_failures[cls] = self.consecutive_grasp_failures.get(cls, 0) + 1
        return self.consecutive_grasp_failures[cls]

    def mark_skipped(self, cls: str) -> None:
        self.skipped.add(cls)


class OrderProvider(Protocol):
    def fetch(self) -> OrderBook: ...


class MockOrderProvider:
    """Hardcoded picks for Phase A test (2 of each)."""

    def __init__(self, counts: Optional[Dict[str, int]] = None) -> None:
        self._counts = dict(counts) if counts else {
            "almond": 2,
            "cashew": 2,
            "pistachio": 2,
            "walnut": 2,
        }

    def fetch(self) -> OrderBook:
        return OrderBook(counts=dict(self._counts))


class DBOrderProvider:
    """Phase B: read GetNutOrder service for the same OrderBook shape.

    Kept as a thin shell so the task_manager wiring is identical between
    Phase A (mock) and Phase B (collaborator DB). The actual service client
    construction happens at the call site so we can pass the rclpy node in.
    """

    def __init__(
        self,
        node,
        service_name: str = "/db/get_nut_order",
        timeout_sec: float = 5.0,
        should_stop: Optional[Callable[[], bool]] = None,
        service_type=None,
        poll_sec: float = 0.05,
    ) -> None:
        if service_type is None:
            from cobot_msgs.srv import GetNutOrder  # type: ignore

            service_type = GetNutOrder

        self._client = node.create_client(service_type, service_name)
        self._req_type = service_type.Request
        self._timeout = float(timeout_sec)
        self._service_name = service_name
        self._should_stop = should_stop or (lambda: False)
        self._poll_sec = float(poll_sec)

    def _await_future(self, future) -> bool:
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline and not future.done():
            if self._should_stop():
                return False
            time.sleep(self._poll_sec)
        return future.done()

    def fetch(self) -> OrderBook:
        if not self._client.wait_for_service(timeout_sec=self._timeout):
            raise RuntimeError(f"{self._service_name} not available")
        future = self._client.call_async(self._req_type())
        if not self._await_future(future):
            raise RuntimeError(f"{self._service_name} call timed out")
        resp = future.result()
        if not getattr(resp, "success", False):
            raise RuntimeError(
                f"{self._service_name} returned failure: {getattr(resp, 'message', '')}"
            )
        return OrderBook(counts={
            "almond": int(resp.almond),
            "cashew": int(resp.cashew),
            "pistachio": int(resp.pistachio),
            "walnut": int(resp.walnut),
        })


class FileOrderProvider:
    """Read a cobot_voice latest_order.json and convert to OrderBook.

    Contract (matches cobot_voice/keyword_extractor.py):
        {
          "request_id": "...",
          "recognized_text": "...",
          "combo": [{"nut": "cashew", "count": 3}, ...],
          "success": true,
          ...
        }

    Refuses if success=false or combo is empty so a failed STT/recognition
    does not trigger the robot. Tracks request_id to avoid replaying the
    same order twice — the second fetch() with the same id raises until a
    new file (different request_id) appears.
    """

    def __init__(self, file_path: str, require_success: bool = True) -> None:
        self._path = Path(file_path).expanduser()
        self._require_success = bool(require_success)
        self._last_request_id: Optional[str] = None

    def fetch(self) -> OrderBook:
        if not self._path.is_file():
            raise RuntimeError(f"order file not found: {self._path}")
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"order file is not valid JSON: {exc}") from exc

        if self._require_success and not data.get("success", False):
            raise RuntimeError(
                f"order success=false (text: {data.get('recognized_text', '')!r})"
            )

        request_id = str(data.get("request_id", ""))
        if request_id and request_id == self._last_request_id:
            raise RuntimeError(
                f"order request_id {request_id!r} already processed; "
                "save a new latest_order.json before re-fetching"
            )

        combo = data.get("combo")
        if not isinstance(combo, list) or not combo:
            raise RuntimeError("order has empty or missing 'combo'")

        counts: Dict[str, int] = {}
        for item in combo:
            if not isinstance(item, dict):
                continue
            nut = item.get("nut")
            try:
                n = int(item.get("count", 0))
            except (TypeError, ValueError):
                continue
            if nut not in _NUT_CLASSES or n <= 0:
                continue
            counts[nut] = counts.get(nut, 0) + n

        if not counts:
            raise RuntimeError(f"order combo has no valid items: {combo!r}")

        if request_id:
            self._last_request_id = request_id
        return OrderBook(counts=counts)
