"""Pick the best detection for the current target class.

Policy (matches implementation_plan.md v2 §4.2):
  1. class filter
  2. confidence gate (>= conf_gate)
  3. workspace filter (xy box + z range)
  4. depth/transform validity
  5. sort by OBB area (width * height) descending, tiebreak by confidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence


@dataclass
class WorkspaceBox:
    xmin_mm: float
    xmax_mm: float
    ymin_mm: float
    ymax_mm: float
    zmin_mm: float
    zmax_mm: float

    def contains(self, x: float, y: float, z: float) -> bool:
        return (
            self.xmin_mm <= x <= self.xmax_mm
            and self.ymin_mm <= y <= self.ymax_mm
            and self.zmin_mm <= z <= self.zmax_mm
        )


def choose_target(
    detections: Iterable,
    target_class: str,
    workspace: WorkspaceBox,
    conf_gate: float = 0.40,
    min_depth_mm: float = 2.0,
):
    """Return the best DetectedObject for `target_class`, or None."""
    candidates = [
        d for d in detections
        if d.class_name == target_class
        and d.transform_valid
        and d.confidence >= conf_gate
        and d.base_xyz.z > min_depth_mm
        and workspace.contains(d.base_xyz.x, d.base_xyz.y, d.base_xyz.z)
    ]
    if not candidates:
        return None

    def sort_key(d):
        return (d.width * d.height, d.confidence)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]
