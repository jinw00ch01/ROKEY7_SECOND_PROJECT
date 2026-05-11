# 한국어 요약:
#   cobot_task_manager의 두 흐름(Cluster Push / Verification Loop)에서
#   CobotDbManager를 어떻게 호출하면 되는지 보여주는 standalone 예제.
#
#   실제 ROS 노드 없이도 동작하도록 perception/action을 fake 객체로 만들고,
#   주요 분기(성공/실패)에서 어디에 log_robot_exception / update_inventory를
#   끼우는지 인라인 코멘트로 표시한다.
#
#   실행:
#     1) sql/init.sql 을 Supabase SQL Editor에서 한 번 실행
#     2) cp .env.example .env  &&  실제 SUPABASE_URL / SUPABASE_KEY 채우기
#     3) pip install supabase python-dotenv
#     4) python -m cobot_db.integration_example
"""Integration walkthrough: where CobotDbManager calls slot into the pick loop.

Mirrors the structure of cobot_task_manager.task_manager_node._process_order_book
+ verification rounds, but stripped down so it runs without ROS.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from .cobot_db_manager import CobotDbManager


# ---- Stand-ins for the real perception / action interfaces -----------------
# The real code uses cobot_msgs/Detection and PickAndPlace action results.
# Here we fake just the fields the example branches on.

@dataclass
class FakeDetection:
    cls: str
    base_xyz: tuple   # (x, y, z) mm
    short_axis_mm: float = 18.0


@dataclass
class FakePickResult:
    success: bool
    error_msg: str = ""
    final_pose: Optional[Dict[str, float]] = None  # joints when failed


# ---- 1) Cluster Push integration -------------------------------------------

def handle_cluster_push(
    db: CobotDbManager,
    target: FakeDetection,
    cluster_plan,
    push_action_result: FakePickResult,
    push_count_before: int,
) -> bool:
    """Wraps the cluster-push branch of task_manager_node._process_order_book.

    Returns True if the caller should continue (re-detect after dispersal),
    False if the cluster handling itself failed and the caller should fall
    back to a normal pick attempt or skip the class.
    """

    # Case A: the cluster_policy returned None — neighboring nut is in our
    # own bbox or no clean push direction exists. We log this so we can
    # measure how often the planner has to give up.
    if cluster_plan is None:
        db.log_robot_exception(
            task_name="cluster_push",
            state="ENTRY_HIT",            # entry would intersect another nut
            error_code=1,
            error_msg="no clean push direction (entry inside another bbox)",
            target_class=target.cls,
            target_xyz={
                "x": target.base_xyz[0],
                "y": target.base_xyz[1],
                "z": target.base_xyz[2],
            },
            robot_pose=None,
        )
        return False  # caller should fall back to a regular pick

    # Case B: push goal sent but the action server reported failure
    # (e.g., motion planning failed, or the push reached its end pose
    # but the gripper hit something).
    if not push_action_result.success:
        db.log_robot_exception(
            task_name="cluster_push",
            state="MOTION_FAIL",
            error_code=2,
            error_msg=push_action_result.error_msg or "pick_and_place rejected",
            target_class=target.cls,
            target_xyz={
                "x": cluster_plan.push_end_xyz_mm[0],
                "y": cluster_plan.push_end_xyz_mm[1],
                "z": cluster_plan.push_end_xyz_mm[2],
            },
            robot_pose=push_action_result.final_pose,
        )
        return False

    # Case C: success — no DB write needed. The next iteration of the main
    # loop will re-detect and attempt a fresh pick. We *don't* update
    # inventory here because no nut left the workspace.
    _ = push_count_before  # unused; useful for callers tracking caps
    return True


# ---- 2) Verification Loop integration --------------------------------------

def remaining_from_verification(
    ordered: Dict[str, int],
    initial: Dict[str, int],
    final: Dict[str, int],
) -> Dict[str, int]:
    """Mirrors _remaining_from_verification in task_manager_node.

    For each class:
        moved = max(0, initial - final)  # nuts that left the table
        remaining = max(0, ordered - moved)
    """
    out: Dict[str, int] = {}
    for cls, want in ordered.items():
        moved = max(0, initial.get(cls, 0) - final.get(cls, 0))
        out[cls] = max(0, want - moved)
    return out


def run_verification_round(
    db: CobotDbManager,
    *,
    round_index: int,
    ordered: Dict[str, int],
    initial: Dict[str, int],
    final: Dict[str, int],
    pick_results: Dict[str, FakePickResult],
) -> Dict[str, int]:
    """One verification round: compute remaining, log mismatches, update stock.

    `pick_results` carries the outcome of the correction picks attempted in
    THIS round (one per class with remaining>0). On success we deduct
    inventory; on mismatch where we still have unmet demand AND we ran out
    of correction rounds (caller-controlled), we log the shortfall.
    """
    remaining = remaining_from_verification(ordered, initial, final)

    # Log COUNT_MISMATCH for every class where final != ordered.
    # We log once per class per round so the timeline shows which round
    # the gap appeared in.
    for cls, want in ordered.items():
        moved = max(0, initial.get(cls, 0) - final.get(cls, 0))
        if moved < want:
            db.log_robot_exception(
                task_name="verification_round",
                state="COUNT_MISMATCH",
                error_code=3,
                error_msg=(
                    f"round={round_index + 1} ordered={want} moved={moved} "
                    f"missing={want - moved}"
                ),
                target_class=cls,
                target_xyz=None,
                robot_pose=None,
            )

    # Apply successful correction picks to inventory.
    # In task_manager_node these are dispatched by _process_order_book on
    # the correction_order; here we just iterate their reported results.
    for cls, result in pick_results.items():
        if result.success:
            db.update_inventory(
                nut_type=cls,
                amount=-1,
                reason=f"verify_pick_success_round_{round_index + 1}",
            )
        else:
            # Failed correction pick — log it. We do NOT update inventory.
            db.log_robot_exception(
                task_name="verification_round",
                state="MOTION_FAIL",
                error_code=4,
                error_msg=result.error_msg or "correction pick failed",
                target_class=cls,
                target_xyz=None,
                robot_pose=result.final_pose,
            )

    return remaining


# ---- 3) Primary pick (the common case) -------------------------------------

def record_primary_pick(
    db: CobotDbManager,
    nut_type: str,
    result: FakePickResult,
) -> None:
    """Called once per primary-round pick attempt.

    Success -> deduct one from inventory.
    Failure -> NOT logged here. _process_order_book has its own retry
               policy (record_grasp_failure → mark_skipped after N).
               Only persist to exception_logs once that policy gives up,
               and tag it with task_name='verification_round' if we entered
               correction, else leave the failure unlogged (the loop's own
               state info covers it).
    """
    if result.success:
        db.update_inventory(
            nut_type=nut_type,
            amount=-1,
            reason="primary_pick_success",
        )


# ---- 4) End-to-end demo ----------------------------------------------------

def main() -> None:
    db = CobotDbManager()

    # --- 4a) Show current inventory ---
    print("== inventory before ==")
    for row in db.get_inventory():
        print(f"  {row.nut_type:<10} {row.current_stock}")

    # --- 4b) Cluster push: simulate a planner give-up + a motion failure ---
    target = FakeDetection(cls="cashew", base_xyz=(450.0, -50.0, 65.0))

    # Case A: planner returned None
    print("\n== cluster_push case A: planner=None ==")
    handle_cluster_push(
        db,
        target=target,
        cluster_plan=None,
        push_action_result=FakePickResult(success=False),
        push_count_before=0,
    )

    # Case B: planner produced a plan but motion failed
    @dataclass
    class _FakePlan:
        push_end_xyz_mm: tuple
    plan = _FakePlan(push_end_xyz_mm=(470.0, -65.0, 67.0))
    print("== cluster_push case B: motion fail ==")
    handle_cluster_push(
        db,
        target=target,
        cluster_plan=plan,
        push_action_result=FakePickResult(
            success=False,
            error_msg="action server: planning failed",
            final_pose={f"j{i+1}": round(random.uniform(-90, 90), 2)
                        for i in range(6)},
        ),
        push_count_before=0,
    )

    # --- 4c) Verification round: 2 ordered, 1 picked, 1 missing ---
    print("\n== verification round 1 ==")
    ordered = {"almond": 2, "cashew": 2}
    initial = {"almond": 4, "cashew": 4}
    final = {"almond": 3, "cashew": 3}   # only 1 of each moved → 1 missing each
    correction_results = {
        "almond": FakePickResult(success=True),
        "cashew": FakePickResult(
            success=False,
            error_msg="grasp slipped",
            final_pose=None,
        ),
    }
    remaining = run_verification_round(
        db,
        round_index=0,
        ordered=ordered,
        initial=initial,
        final=final,
        pick_results=correction_results,
    )
    print(f"  remaining after round 1: {remaining}")

    # --- 4d) Primary pick success path (just to bump the deduction count) ---
    print("\n== primary pick success: pistachio ==")
    record_primary_pick(db, "pistachio", FakePickResult(success=True))

    # --- 4e) Show inventory after ---
    print("\n== inventory after ==")
    for row in db.get_inventory():
        print(f"  {row.nut_type:<10} {row.current_stock}")


if __name__ == "__main__":
    main()
