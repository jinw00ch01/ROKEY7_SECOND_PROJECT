"""OBB rotation -> gripper yaw conversion.

The two-finger RG2 gripper closes along its local Y axis, so the fingers
should travel across the nut's short axis. We pick a yaw that makes the
gripper's closing direction perpendicular to the OBB long axis.
"""

from __future__ import annotations

import math


def yaw_from_obb(theta_rad: float, width_px: float, height_px: float) -> float:
    if width_px >= height_px:
        gripper_yaw = theta_rad + math.pi / 2.0
    else:
        gripper_yaw = theta_rad
    return _normalize(gripper_yaw)


def _normalize(angle_rad: float) -> float:
    a = ((angle_rad + math.pi / 2.0) % math.pi) - math.pi / 2.0
    return a
