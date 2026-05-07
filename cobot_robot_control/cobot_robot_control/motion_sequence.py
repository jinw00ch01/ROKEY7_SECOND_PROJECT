# 한국어 요약:
#   PickAndPlace 액션의 9단계 stage 시퀀스를 실행.
#   pre_grasp_width → approach → grasp → verify_grip → lift → transit →
#   place → retreat → home 순서로 motion/gripper를 호출하며 feedback_cb로
#   stage 이름을 보고. workspace_bounds 위반·취소·grip 미감지 등을
#   failure_code(0~5)로 구분해 (success, code, message) 튜플로 반환.
"""Pick & place sequence for the cobot_robot_control Action server.

Stages match cobot_msgs/action/PickAndPlace.action and feed back via the
provided `feedback_cb`. Returns a (success, failure_code, message) tuple
mirroring the action result.

The verify_grip stage is the Codex-flagged enhancement: after closing the
gripper, we read the RG2 status word; if the "grip detected" bit is low we
treat it as an empty grasp and bail out before transit.

failure_code values match the action definition:
  0 = ok
  1 = approach_fail
  2 = grasp_not_detected
  3 = motion_fail
  4 = safety_stop
  5 = workspace_violation
"""
# 한국어: failure_code 의미 - 0=정상, 1=approach 실패(현재 미사용),
# 2=close 후 grip 비검출(가장 흔한 실패), 3=motion/gripper 예외 일반,
# 4=cancel/stop 신호, 5=workspace 경계 밖 좌표.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .doosan_motion_client import MotionError
from .gripper_controller import wait_until_idle
from .pose_converter import point_yaw_to_posx, point_zyz_to_posx


@dataclass
class WorkspaceBounds:
    xmin_mm: float = 200.0
    xmax_mm: float = 700.0
    ymin_mm: float = -300.0
    ymax_mm: float = 300.0
    zmin_mm: float = 0.0
    zmax_mm: float = 500.0

    def contains(self, xyz_mm: Sequence[float]) -> bool:
        if len(xyz_mm) < 3:
            return False
        x, y, z = float(xyz_mm[0]), float(xyz_mm[1]), float(xyz_mm[2])
        return (
            math.isfinite(x)
            and math.isfinite(y)
            and math.isfinite(z)
            and self.xmin_mm <= x <= self.xmax_mm
            and self.ymin_mm <= y <= self.ymax_mm
            and self.zmin_mm <= z <= self.zmax_mm
        )

    def describe(self) -> str:
        return (
            f"x=[{self.xmin_mm:.1f},{self.xmax_mm:.1f}], "
            f"y=[{self.ymin_mm:.1f},{self.ymax_mm:.1f}], "
            f"z=[{self.zmin_mm:.1f},{self.zmax_mm:.1f}]"
        )


@dataclass
class MotionConfig:
    home_joints_deg: Sequence[float]
    approach_offset_z_mm: float = 80.0
    velocity: float = 60.0
    acceleration: float = 60.0
    velocity_slow: float = 30.0
    acceleration_slow: float = 30.0
    grip_settle_timeout_sec: float = 5.0
    # Constant offset applied to grasp_xyz in the gripper's local frame.
    # Used to compensate for a TCP that is not centered between the
    # gripper fingers (Doosan's TCP setting vs. the lecture hand-eye
    # calibration's assumed TCP). Rotated by grasp_yaw before adding.
    grasp_local_offset_xy_mm: Sequence[float] = field(default_factory=lambda: [0.0, 0.0])
    place_y_margin_mm: float = 3.0
    workspace_enabled: bool = True
    workspace_bounds: WorkspaceBounds = field(default_factory=WorkspaceBounds)


def _apply_local_xy_offset(
    grasp_xyz_mm: Sequence[float],
    yaw_rad: float,
    local_offset_xy_mm: Sequence[float],
) -> List[float]:
    dx, dy = float(local_offset_xy_mm[0]), float(local_offset_xy_mm[1])
    if dx == 0.0 and dy == 0.0:
        return [float(grasp_xyz_mm[0]), float(grasp_xyz_mm[1]), float(grasp_xyz_mm[2])]
    # 한국어: offset은 그리퍼 local 프레임 기준이므로 grasp yaw로 회전한 뒤
    # world 좌표에 더해야 한다. yaw=0일 때만 offset이 그대로 world에 더해진다.
    c = math.cos(yaw_rad)
    s = math.sin(yaw_rad)
    world_dx = dx * c - dy * s
    world_dy = dx * s + dy * c
    return [
        float(grasp_xyz_mm[0]) + world_dx,
        float(grasp_xyz_mm[1]) + world_dy,
        float(grasp_xyz_mm[2]),
    ]


def _safe_call(cb: Optional[Callable[[str], None]], stage: str) -> None:
    if cb is not None:
        try:
            cb(stage)
        except Exception:
            pass


def _workspace_violation(
    cfg: MotionConfig,
    waypoints: Sequence[Tuple[str, Sequence[float]]],
) -> Optional[str]:
    if not cfg.workspace_enabled:
        return None

    bounds = cfg.workspace_bounds
    for name, xyz in waypoints:
        if not bounds.contains(xyz):
            point = list(xyz[:3]) if len(xyz) >= 3 else list(xyz)
            return (
                f"{name} outside workspace: {point!r}; "
                f"allowed {bounds.describe()}"
            )
    return None


def execute_pick_and_place(
    motion,
    gripper,
    cfg: MotionConfig,
    grasp_xyz_mm: Sequence[float],
    grasp_yaw_rad: float,
    return_xyz_mm: Sequence[float],
    return_zyz_deg: Sequence[float],
    pre_grasp_width_mm: float = 0.0,
    feedback_cb: Optional[Callable[[str], None]] = None,
    place_ready_cb: Optional[Callable[[bool, str], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
):
    def cancelled() -> bool:
        return bool(is_cancelled and is_cancelled())

    grasp_xyz_corrected = _apply_local_xy_offset(
        grasp_xyz_mm, grasp_yaw_rad, cfg.grasp_local_offset_xy_mm
    )
    approach = point_yaw_to_posx(grasp_xyz_corrected, grasp_yaw_rad, cfg.approach_offset_z_mm)
    grasp_pose = point_yaw_to_posx(grasp_xyz_corrected, grasp_yaw_rad)
    above_return = point_zyz_to_posx(return_xyz_mm, return_zyz_deg, cfg.approach_offset_z_mm)
    place_pose = point_zyz_to_posx(return_xyz_mm, return_zyz_deg)

    violation = _workspace_violation(
        cfg,
        [
            ("grasp_xyz", grasp_xyz_mm),
            ("corrected_grasp_xyz", grasp_xyz_corrected),
            ("approach_xyz", approach),
            ("return_xyz", return_xyz_mm),
            ("above_return_xyz", above_return),
        ],
    )
    if violation is not None:
        return False, 5, violation

    def set_place_ready(ready: bool, reason: str) -> None:
        if place_ready_cb is not None:
            try:
                place_ready_cb(ready, reason)
            except Exception:
                pass

    def is_tcp_at_place_y() -> bool:
        current_pose = motion.get_current_pose()
        if len(current_pose) < 2:
            raise MotionError(f"unexpected current pose: {current_pose!r}")
        return abs(float(current_pose[1]) - float(return_xyz_mm[1])) <= float(cfg.place_y_margin_mm)

    motion.set_speed(cfg.velocity, cfg.acceleration)

    try:
        # 한국어: 시작 시점에 place_ready=False로 강제. 컨베이어 트리거가
        # False→True 에지를 보기 때문에, 한 번 False로 떨어뜨려야
        # 이후 place 단계의 True 전이가 유효한 트리거가 된다.
        set_place_ready(False, "pick_and_place_started")

        # Pre-position the gripper width before motion starts so the close
        # travel during grasp is short (and we don't sweep neighbor nuts).
        if pre_grasp_width_mm > 0.0:
            _safe_call(feedback_cb, "pre_grasp_width")
            gripper.move_to(pre_grasp_width_mm)
            wait_until_idle(gripper, timeout_sec=cfg.grip_settle_timeout_sec)

        _safe_call(feedback_cb, "approach")
        if cancelled():
            return False, 4, "cancelled before approach"
        motion.move_line(approach)

        _safe_call(feedback_cb, "grasp")
        if cancelled():
            return False, 4, "cancelled before grasp"
        motion.set_speed(cfg.velocity_slow, cfg.acceleration_slow)
        motion.move_line(grasp_pose)
        gripper.close()
        # 한국어: 첫 wait_until_idle은 close() 직후 busy 상승을 기다리고
        # 끝까지 idle이 되기를 기다린다. 과거에는 close() 직후 stale idle을
        # 읽고 즉시 verify_grip으로 넘어가 grip_detected 비트를 잘못 읽는
        # 버그가 있었다(gripper_controller의 두 단계 검증과 짝).
        if not wait_until_idle(gripper, timeout_sec=cfg.grip_settle_timeout_sec):
            return False, 3, "gripper close did not settle in time"

        _safe_call(feedback_cb, "verify_grip")
        if not gripper.is_grip_detected():
            # 한국어: 빈 grip이면 손가락을 다시 열고 approach 높이로 후퇴해
            # 다음 시도/오퍼레이터가 안전하게 개입할 수 있게 한다.
            gripper.open()
            wait_until_idle(gripper, timeout_sec=cfg.grip_settle_timeout_sec)
            motion.set_speed(cfg.velocity, cfg.acceleration)
            motion.move_line(approach)
            return False, 2, "gripper closed but no object detected"

        _safe_call(feedback_cb, "lift")
        motion.set_speed(cfg.velocity, cfg.acceleration)
        motion.move_line(approach)

        _safe_call(feedback_cb, "transit")
        if cancelled():
            return False, 4, "cancelled in transit"
        motion.move_line(above_return)

        _safe_call(feedback_cb, "place")
        motion.set_speed(cfg.velocity_slow, cfg.acceleration_slow)
        motion.move_line(place_pose)
        gripper.open()
        if not wait_until_idle(gripper, timeout_sec=cfg.grip_settle_timeout_sec):
            return False, 3, "gripper open did not settle in time"

        # 한국어: 그리퍼가 열린 직후, TCP의 y가 place 위치 margin 안에 있을 때만
        # place_ready를 True로 set. 이 False→True 에지가 컨베이어 트리거로
        # 사용되므로, 정확히 "물체가 놓인 순간"에만 한 번 발생해야 한다.
        try:
            at_place_y = is_tcp_at_place_y()
        except Exception as exc:  # noqa: BLE001
            set_place_ready(False, f"tcp_check_failed: {exc}")
        else:
            set_place_ready(at_place_y, "gripper_open_at_place" if at_place_y else "tcp_y_outside_place_margin")

        _safe_call(feedback_cb, "retreat")
        motion.set_speed(cfg.velocity, cfg.acceleration)
        motion.move_line(above_return)
        # 한국어: retreat 시작과 동시에 place_ready를 다시 False로 내려
        # 다음 사이클을 위해 에지를 초기화.
        set_place_ready(False, "retreat")

        _safe_call(feedback_cb, "home")
        motion.move_joint(cfg.home_joints_deg)

        return True, 0, "ok"

    except MotionError as exc:
        return False, 3, f"motion error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, 3, f"unexpected error: {exc}"
