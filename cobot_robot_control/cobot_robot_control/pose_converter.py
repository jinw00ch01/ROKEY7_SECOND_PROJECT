"""Convert between cobot_msgs Point/yaw and Doosan posx lists.

Doosan DSR posx convention: [x, y, z, rx, ry, rz] in mm + ZYZ Euler degrees.
For top-down picking we keep rx=0, ry=180, and let yaw drive rz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class TopDownPose:
    rx_deg: float = 0.0
    ry_deg: float = 180.0


DEFAULT_TOPDOWN = TopDownPose()


def point_yaw_to_posx(
    xyz_mm: Sequence[float],
    yaw_rad: float,
    z_offset_mm: float = 0.0,
    topdown: TopDownPose = DEFAULT_TOPDOWN,
) -> List[float]:
    """Build a DSR posx list from a (x, y, z) point and a yaw on top-down."""
    if len(xyz_mm) != 3:
        raise ValueError(f"xyz_mm must be 3 floats, got {xyz_mm!r}")
    return [
        float(xyz_mm[0]),
        float(xyz_mm[1]),
        float(xyz_mm[2]) + float(z_offset_mm),
        topdown.rx_deg,
        topdown.ry_deg,
        math.degrees(float(yaw_rad)),
    ]


def point_zyz_to_posx(
    xyz_mm: Sequence[float],
    zyz_deg: Sequence[float],
    z_offset_mm: float = 0.0,
) -> List[float]:
    """Build a DSR posx list from (x, y, z) + full ZYZ Euler [rx, ry, rz] degrees."""
    if len(xyz_mm) != 3:
        raise ValueError(f"xyz_mm must be 3 floats, got {xyz_mm!r}")
    if len(zyz_deg) != 3:
        raise ValueError(f"zyz_deg must be 3 floats, got {zyz_deg!r}")
    return [
        float(xyz_mm[0]),
        float(xyz_mm[1]),
        float(xyz_mm[2]) + float(z_offset_mm),
        float(zyz_deg[0]),
        float(zyz_deg[1]),
        float(zyz_deg[2]),
    ]


def msg_point_to_xyz(point_msg) -> List[float]:
    """Extract [x, y, z] from a geometry_msgs/Point."""
    return [float(point_msg.x), float(point_msg.y), float(point_msg.z)]
