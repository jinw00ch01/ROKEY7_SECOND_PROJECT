# 한국어 요약:
#   cobot2 Supabase 연동 헬퍼. 두 개의 도메인만 다룬다.
#     1) 예외 로깅: cluster_push / verification_round 두 task에 한정
#     2) 재고: 원자적 차감/리필(RPC) + 단순 조회
#   .env 의 SUPABASE_URL, SUPABASE_KEY 를 읽고, 클라이언트는 lazy-init.
#   재고 차감은 반드시 update_inventory_atomic RPC 를 통해서만 한다
#   (UPDATE+INSERT 단일 트랜잭션, race-free).
"""Supabase wrapper for cobot2 exception logging and inventory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client


_VALID_TASKS = frozenset({"cluster_push", "verification_round"})
_VALID_NUTS = frozenset({"almond", "cashew", "pistachio", "walnut"})

# robot_session는 단일 행 운영. id='current' CHECK 제약과 일치.
_SESSION_TABLE = "robot_session"
_SESSION_ID = "current"


@dataclass(frozen=True)
class InventoryRow:
    nut_type: str
    current_stock: int


@dataclass(frozen=True)
class ExceptionLogRow:
    id: str
    created_at: str
    task_name: str
    state: str
    error_code: int
    error_msg: Optional[str]
    target_class: Optional[str]
    target_xyz: Optional[Dict[str, Any]]
    robot_pose: Optional[Dict[str, Any]]


class CobotDbManager:
    """Thin wrapper over supabase-py for the two domains we persist.

    The client is created on first use so that import-time failures
    (missing .env, network down) don't crash a ROS node at startup.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        env_path: Optional[str] = None,
    ) -> None:
        if env_path is not None:
            load_dotenv(env_path, override=False)
        else:
            load_dotenv(override=False)

        self._url = url or os.getenv("SUPABASE_URL", "")
        self._key = key or os.getenv("SUPABASE_KEY", "")
        self._client: Optional[Client] = None

    # ---- internals ---------------------------------------------------------

    @property
    def client(self) -> Client:
        if self._client is None:
            if not self._url or not self._key:
                raise RuntimeError(
                    "SUPABASE_URL and SUPABASE_KEY must be set "
                    "(via .env or constructor arguments)"
                )
            self._client = create_client(self._url, self._key)
        return self._client

    # ---- exception logs ----------------------------------------------------

    def log_robot_exception(
        self,
        *,
        task_name: str,
        state: str,
        error_code: int = 0,
        error_msg: Optional[str] = None,
        target_class: Optional[str] = None,
        target_xyz: Optional[Dict[str, Any]] = None,
        robot_pose: Optional[Dict[str, Any]] = None,
    ) -> ExceptionLogRow:
        """Insert one row into exception_logs.

        task_name must be one of the two flows we track:
          - 'cluster_push'        (군집 분산 동작 실패 / 진입 충돌 등)
          - 'verification_round'  (검증 루프 카운트 미스매치 / 보정 실패 등)

        target_xyz / robot_pose are passed through as JSONB. For target_xyz
        a {"x": ..., "y": ..., "z": ...} dict is conventional; for
        robot_pose a {"j1": ..., ..., "j6": ...} dict (or any debug JSON).
        """
        if task_name not in _VALID_TASKS:
            raise ValueError(
                f"task_name must be one of {sorted(_VALID_TASKS)}, "
                f"got {task_name!r}"
            )

        payload: Dict[str, Any] = {
            "task_name": task_name,
            "state": state,
            "error_code": int(error_code),
            "error_msg": error_msg,
            "target_class": target_class,
            "target_xyz": target_xyz,
            "robot_pose": robot_pose,
        }

        resp = self.client.table("exception_logs").insert(payload).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError("exception_logs insert returned no rows")
        return _exception_row(rows[0])

    # ---- inventory ---------------------------------------------------------

    def update_inventory(
        self,
        nut_type: str,
        amount: int,
        reason: str,
    ) -> InventoryRow:
        """Atomically apply a SIGNED change and append a log entry.

        amount semantics:
          -1, -2, ...  => deduction (e.g. successful pick)
          +N           => refill

        Implemented as a single SECURITY DEFINER RPC call so the
        UPDATE inventory + INSERT inventory_logs run in one transaction
        on the server. Two concurrent callers cannot race on
        current_stock; underflow (stock < 0) is rejected by the function.
        """
        if nut_type not in _VALID_NUTS:
            raise ValueError(
                f"nut_type must be one of {sorted(_VALID_NUTS)}, got {nut_type!r}"
            )
        if amount == 0:
            raise ValueError("amount must be non-zero")
        if not reason:
            raise ValueError("reason must be a non-empty string")

        resp = self.client.rpc(
            "update_inventory_atomic",
            {
                "p_nut_type": nut_type,
                "p_change_amount": int(amount),
                "p_reason": reason,
            },
        ).execute()

        rows = resp.data or []
        if not rows:
            raise RuntimeError(
                f"update_inventory_atomic returned no rows for {nut_type}"
            )
        # RPC returns the (nut_type, current_stock) tuple as the first row.
        row = rows[0]
        return InventoryRow(
            nut_type=str(row["nut_type"]),
            current_stock=int(row["current_stock"]),
        )

    def get_inventory(self) -> List[InventoryRow]:
        """Return the full inventory table as a list, ordered by nut_type."""
        resp = (
            self.client
            .table("inventory")
            .select("nut_type, current_stock")
            .order("nut_type")
            .execute()
        )
        return [
            InventoryRow(
                nut_type=str(r["nut_type"]),
                current_stock=int(r["current_stock"]),
            )
            for r in (resp.data or [])
        ]

    def get_stock(self, nut_type: str) -> int:
        """Convenience: current_stock for a single nut_type."""
        if nut_type not in _VALID_NUTS:
            raise ValueError(
                f"nut_type must be one of {sorted(_VALID_NUTS)}, got {nut_type!r}"
            )
        resp = (
            self.client
            .table("inventory")
            .select("current_stock")
            .eq("nut_type", nut_type)
            .single()
            .execute()
        )
        data = resp.data or {}
        return int(data.get("current_stock", 0))

    # ---- robot_session (interop with web + ROS bridges) -------------------

    def set_robot_state(self, state: str, **fields: Any) -> Dict[str, Any]:
        """Upsert robot_session.current with new robot_state and optional fields.

        Used by the ROS-side status bridge to mirror task progress to the
        single-row robot_session table the web subscribes to. updated_at is
        bumped server-side via the touch_updated_at trigger; we don't send
        it from the client.

        `fields` is forwarded as-is so callers can include target_class,
        last_result, error, etc. without this method needing to know the
        schema.
        """
        if not state:
            raise ValueError("state must be a non-empty string")

        payload: Dict[str, Any] = {
            "id": _SESSION_ID,
            "robot_state": state,
            **fields,
        }
        resp = (
            self.client
            .table(_SESSION_TABLE)
            .upsert(payload, on_conflict="id")
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else {}

    def read_robot_session(self) -> Optional[Dict[str, Any]]:
        """Return the current robot_session row, or None if not seeded yet.

        Uses limit(1) instead of single()/maybe_single() for portability across
        supabase-py releases (the helper renamed several times).
        """
        resp = (
            self.client
            .table(_SESSION_TABLE)
            .select("*")
            .eq("id", _SESSION_ID)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None


def _exception_row(row: Dict[str, Any]) -> ExceptionLogRow:
    return ExceptionLogRow(
        id=str(row.get("id", "")),
        created_at=str(row.get("created_at", "")),
        task_name=str(row.get("task_name", "")),
        state=str(row.get("state", "")),
        error_code=int(row.get("error_code", 0) or 0),
        error_msg=row.get("error_msg"),
        target_class=row.get("target_class"),
        target_xyz=row.get("target_xyz"),
        robot_pose=row.get("robot_pose"),
    )
