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
        if not wait_until_idle(gripper, timeout_sec=cfg.grip_settle_timeout_sec):
            return False, 3, "gripper close did not settle in time"

        _safe_call(feedback_cb, "verify_grip")
        if not gripper.is_grip_detected():
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

        try:
            at_place_y = is_tcp_at_place_y()
        except Exception as exc:  # noqa: BLE001
            set_place_ready(False, f"tcp_check_failed: {exc}")
        else:
            set_place_ready(at_place_y, "gripper_open_at_place" if at_place_y else "tcp_y_outside_place_margin")

        _safe_call(feedback_cb, "retreat")
        motion.set_speed(cfg.velocity, cfg.acceleration)
        motion.move_line(above_return)
        set_place_ready(False, "retreat")

        _safe_call(feedback_cb, "home")
        motion.move_joint(cfg.home_joints_deg)

        return True, 0, "ok"

    except MotionError as exc:
        return False, 3, f"motion error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, 3, f"unexpected error: {exc}"
