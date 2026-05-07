# 한국어 요약:
#   OBB 회전각으로부터 그리퍼 yaw를 산출하는 모듈.
#   RG2 두 손가락 그리퍼는 로컬 Y축으로 닫히므로, 손가락이 너트의 짧은 축을
#   가로지르도록 OBB 긴 축에 수직으로 grasp yaw를 정렬한다.
#   결과 각도는 [-pi/2, pi/2] 범위로 정규화하여 그리퍼 회전 한계와 양립시킨다.
"""OBB rotation -> gripper yaw conversion.

The two-finger RG2 gripper closes along its local Y axis, so the fingers
should travel across the nut's short axis. We pick a yaw that makes the
gripper's closing direction perpendicular to the OBB long axis.
"""

from __future__ import annotations

import math


def yaw_from_obb(theta_rad: float, width_px: float, height_px: float) -> float:
    # width가 더 크면 OBB 긴 축이 width 방향이므로 yaw를 90도 회전시켜 수직 정렬.
    if width_px >= height_px:
        gripper_yaw = theta_rad + math.pi / 2.0
    else:
        gripper_yaw = theta_rad
    return _normalize(gripper_yaw)


def _normalize(angle_rad: float) -> float:
    a = ((angle_rad + math.pi / 2.0) % math.pi) - math.pi / 2.0
    return a
