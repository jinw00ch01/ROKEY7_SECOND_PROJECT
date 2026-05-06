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
        if failure_code == 2:  # grasp_not_detected
            if consecutive_grasp >= self.max_grasp_failures:
                return FailureAction.SKIP_CLASS
            return FailureAction.RETRY_PICK
        if failure_code in (4,):  # safety_stop
            return FailureAction.ABORT
        if failure_code in (3, 5, 1):  # motion / workspace / approach
            return FailureAction.ABORT
        # Anything unrecognised: be conservative.
        return FailureAction.ABORT
