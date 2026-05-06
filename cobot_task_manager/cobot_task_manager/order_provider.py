"""Order book for pending nut picks.

Tracks per-class remaining counts plus retry/skip bookkeeping. Two providers
share the `OrderBook` data class:
  - MockOrderProvider returns a fixed dict (Phase A test setup: 2 of each)
  - DBOrderProvider calls cobot_msgs/srv/GetNutOrder (Phase B)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Protocol


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

    def __init__(self, node, service_name: str = "/db/get_nut_order", timeout_sec: float = 5.0) -> None:
        from cobot_msgs.srv import GetNutOrder  # type: ignore

        self._node = node
        self._client = node.create_client(GetNutOrder, service_name)
        self._req_type = GetNutOrder.Request
        self._timeout = float(timeout_sec)
        self._service_name = service_name

    def fetch(self) -> OrderBook:
        if not self._client.wait_for_service(timeout_sec=self._timeout):
            raise RuntimeError(f"{self._service_name} not available")
        future = self._client.call_async(self._req_type())
        # The caller node must be spun externally; we just wait on the future.
        import rclpy
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout)
        if not future.done():
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
