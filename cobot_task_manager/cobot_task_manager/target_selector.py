# 한국어 요약:
#   현재 target class에 대해 최적 detection을 고르는 모듈이다.
#   class/conf/workspace/depth 필터를 차례로 적용한 뒤 OBB 면적 내림차순,
#   동률이면 confidence로 정렬해 첫 번째 후보를 반환한다.
#   면적 우선 정책의 근거는 _choose_target 본문 주석 참고.
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

    # 정렬 우선순위: area > confidence.
    # 면적이 큰 detection은 (1) 카메라에 더 잘 보이고 (2) 가려지지 않은
    # 단일 너트일 가능성이 높아 그리퍼가 안정적으로 잡을 수 있다.
    # confidence는 YOLO score인데 작은/부분 가림 객체에서도 종종 높게 나오므로
    # 면적을 1차 키로 두고 동률 처리에만 사용한다.
    def sort_key(d):
        return (d.width * d.height, d.confidence)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]
