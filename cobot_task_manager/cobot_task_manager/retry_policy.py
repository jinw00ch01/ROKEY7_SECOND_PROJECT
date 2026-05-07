# 한국어 요약:
#   task_manager 루프의 재시도/스킵/중단 정책을 결정한다.
#   detect 실패는 누적 횟수에 따라 RETRY_DETECT 또는 SKIP_CLASS를 반환하고,
#   action 실패는 failure_code 별로 RETRY_PICK / SKIP_CLASS / ABORT로 분기한다.
#   복구 가능한 실패(grasp_not_detected)와 사람이 개입해야 하는 실패(motion,
#   workspace, safety_stop)를 구분하는 것이 핵심이다.
"""Retry/skip semantics for the task manager loop.

Policy (matches implementation_plan.md v2 §4.2):

detection failure (no candidate found for the target class):
  - re-detect the same place (counts as one consecutive miss)
  - after `max_detect_misses` consecutive misses for that class -> skip class

grasp failure (action result failure_code == 2 = grasp_not_detected):
  - the action server already opened the gripper and retreated
  - retry up to `max_grasp_failures` times for the same class
  - exceeding the limit -> skip class

motion failure (failure_code == 3) or workspace violation (5):
  - immediate abort, human intervention required
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailureAction(str, Enum):
    RETRY_DETECT = "retry_detect"
    RETRY_PICK = "retry_pick"
    SKIP_CLASS = "skip_class"
    ABORT = "abort"


@dataclass
class RetryPolicy:
    max_detect_misses: int = 2
    max_grasp_failures: int = 2

    def on_detect_miss(self, consecutive_misses: int) -> FailureAction:
        if consecutive_misses >= self.max_detect_misses:
            return FailureAction.SKIP_CLASS
        return FailureAction.RETRY_DETECT

    def on_action_failure(self, failure_code: int, consecutive_grasp: int) -> FailureAction:
        # code=2 (grasp_not_detected): 그리퍼가 닫혔는데 너트를 못 잡은 경우.
        # 액션 서버가 이미 그리퍼를 열고 후퇴해 두었으므로 다른 후보로 재시도
        # 가능. 같은 클래스가 max_grasp_failures만큼 연속 실패하면 SKIP_CLASS.
        if failure_code == 2:  # grasp_not_detected
            if consecutive_grasp >= self.max_grasp_failures:
                return FailureAction.SKIP_CLASS
            return FailureAction.RETRY_PICK
        # code=4 (safety_stop): e-stop이 걸린 상태이므로 사람이 풀어줘야 한다.
        if failure_code in (4,):  # safety_stop
            return FailureAction.ABORT
        # code=1/3/5 (approach/motion/workspace): 모션 플래닝이 아예 깨졌거나
        # workspace 경계를 벗어남 -> 환경/캘리브레이션 점검 필요. 자동 복구 불가.
        if failure_code in (3, 5, 1):  # motion / workspace / approach
            return FailureAction.ABORT
        # 모르는 코드는 보수적으로 ABORT. 알지 못하는 실패를 무시하고 진행하다
        # 더 큰 사고가 나는 것보다 멈추는 편이 안전하다.
        return FailureAction.ABORT
