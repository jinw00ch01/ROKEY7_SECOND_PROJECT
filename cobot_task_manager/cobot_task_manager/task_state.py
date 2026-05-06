"""State enum for the task manager loop."""

from enum import Enum


class TaskState(str, Enum):
    IDLE = "idle"
    INIT = "init"
    DETECT = "detect"
    SELECT_TARGET = "select_target"
    PICK_AND_PLACE = "pick_and_place"
    DONE = "done"
    ABORTED = "aborted"
    SAFETY_STOP = "safety_stop"
