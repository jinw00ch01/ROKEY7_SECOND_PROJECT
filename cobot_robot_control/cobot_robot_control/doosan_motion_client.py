# 한국어 요약:
#   DSR_ROBOT2 모듈의 얇은 래퍼. real 백엔드는 DR_init 전역 바인딩 후
#   DSR_ROBOT2를 import해 movej/movel/get_current_posx 등을 호출.
#   호출 측이 robot_id 네임스페이스에 이미 배치된 rclpy.Node를 넘겨야 한다.
#   mock 백엔드(MockMotionClient)는 동일 인터페이스로 가짜 pose만 갱신하며
#   가상(virtual) 모드 개발/테스트에서 실 로봇 없이 상위 시퀀스를 검증.
"""Thin wrapper around DSR_ROBOT2 with a mock fallback.

DSR_ROBOT2 expects:
  1. DR_init.__dsr__id, __dsr__model, __dsr__node set before import
  2. The owning rclpy node lives in the robot's namespace (e.g. "dsr01")

So callers must hand us an already-created rclpy.Node placed in that
namespace. We then perform the DR_init binding and the DSR_ROBOT2 import.

`MockMotionClient` implements the same surface for virtual development - it
just records calls and returns immediately. Tests of higher-level sequences
can target the mock without a robot running.
"""

from __future__ import annotations

from typing import List, Optional, Sequence


class MotionError(RuntimeError):
    pass


def _bind_dsr_init(ros_node, robot_id: str, robot_model: str) -> None:
    """Set DR_init globals at module/function scope.

    This MUST live outside the class. Python applies name-mangling to any
    identifier of the form `__name` (no trailing `__`) inside class bodies,
    which would rewrite `DR_init.__dsr__id` to
    `DR_init._DoosanMotionClient__dsr__id` and silently drop our values.
    DSR_ROBOT2.py reads the unmangled attributes at import time, so the
    binding has to use the literal names from outside any class.
    """
    # 한국어: 이 함수는 반드시 클래스 밖(모듈 스코프)에 있어야 한다.
    # Python의 name-mangling 규칙상 클래스 본문 안에서 `__dsr__id`처럼
    # 앞쪽 더블 언더스코어 식별자에 접근하면 `_DoosanMotionClient__dsr__id`로
    # 변환되어 실제 DR_init 모듈 속성에 값이 들어가지 않는다. DSR_ROBOT2가
    # import 시점에 mangling 안 된 원래 이름을 읽으므로 외부 함수에서 바인딩.
    import DR_init  # type: ignore

    DR_init.__dsr__id = robot_id
    DR_init.__dsr__model = robot_model
    DR_init.__dsr__node = ros_node


def _import_dsr_robot2():
    from DSR_ROBOT2 import (  # type: ignore
        movej,
        movel,
        get_current_posx,
        mwait,
        set_velx,
        set_accx,
    )
    return movej, movel, get_current_posx, mwait, set_velx, set_accx


class DoosanMotionClient:
    def __init__(
        self,
        ros_node,
        robot_id: str,
        robot_model: str,
        velocity: float = 60.0,
        acceleration: float = 60.0,
    ) -> None:
        _bind_dsr_init(ros_node, robot_id, robot_model)
        try:
            (
                movej,
                movel,
                get_current_posx,
                mwait,
                set_velx,
                set_accx,
            ) = _import_dsr_robot2()
        except ImportError as exc:
            raise MotionError(f"Failed to import DSR_ROBOT2: {exc}") from exc

        self._movej = movej
        self._movel = movel
        self._get_current_posx = get_current_posx
        self._mwait = mwait
        self._set_velx = set_velx
        self._set_accx = set_accx
        self._vel = float(velocity)
        self._acc = float(acceleration)

    def set_speed(self, velocity: float, acceleration: float) -> None:
        self._vel = float(velocity)
        self._acc = float(acceleration)

    def move_joint(self, joints_deg: Sequence[float], vel: Optional[float] = None, acc: Optional[float] = None) -> None:
        v = self._vel if vel is None else float(vel)
        a = self._acc if acc is None else float(acc)
        result = self._movej(list(joints_deg), vel=v, acc=a)
        self._mwait()
        if result is False:
            raise MotionError(f"movej failed for {list(joints_deg)}")

    def move_line(self, posx_mm_deg: Sequence[float], vel: Optional[float] = None, acc: Optional[float] = None) -> None:
        v = self._vel if vel is None else float(vel)
        a = self._acc if acc is None else float(acc)
        result = self._movel(list(posx_mm_deg), vel=v, acc=a)
        self._mwait()
        if result is False:
            raise MotionError(f"movel failed for {list(posx_mm_deg)}")

    def get_current_pose(self) -> List[float]:
        pose = self._get_current_posx()
        if isinstance(pose, (list, tuple)) and len(pose) >= 1:
            return list(pose[0])
        raise MotionError(f"unexpected get_current_posx return: {pose!r}")

    def shutdown(self) -> None:
        return None


# 한국어: MockMotionClient는 가상(virtual) 모드 전용. movej/movel를
# history에 기록만 하고 즉시 반환하며, get_current_pose는 마지막 movel
# 좌표 또는 초기 fake_pose를 돌려준다. 실 로봇 없이 motion_sequence와
# 상위 액션 흐름을 검증하기 위한 의도.
class MockMotionClient:
    def __init__(self, ros_node=None, robot_id: str = "mock", robot_model: str = "mock", velocity: float = 60.0, acceleration: float = 60.0) -> None:
        self._vel = float(velocity)
        self._acc = float(acceleration)
        self._fake_pose: List[float] = [400.0, 0.0, 400.0, 0.0, 180.0, 0.0]
        self.history: List[tuple] = []

    def set_speed(self, velocity: float, acceleration: float) -> None:
        self._vel = float(velocity)
        self._acc = float(acceleration)

    def move_joint(self, joints_deg: Sequence[float], vel: Optional[float] = None, acc: Optional[float] = None) -> None:
        self.history.append(("movej", list(joints_deg)))

    def move_line(self, posx_mm_deg: Sequence[float], vel: Optional[float] = None, acc: Optional[float] = None) -> None:
        self.history.append(("movel", list(posx_mm_deg)))
        self._fake_pose = list(posx_mm_deg)

    def get_current_pose(self) -> List[float]:
        return list(self._fake_pose)

    def shutdown(self) -> None:
        return None


def make_motion_client(backend: str, **kwargs):
    backend = backend.lower()
    if backend == "mock":
        return MockMotionClient(**kwargs)
    if backend == "real":
        return DoosanMotionClient(**kwargs)
    raise ValueError(f"unknown motion backend: {backend!r}")
