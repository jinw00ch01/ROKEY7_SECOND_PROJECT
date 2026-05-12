# 한국어 요약:
#   군집(cluster) 상태로 판정된 견과류를 closed-gripper push로 분산시키는
#   기하 로직. 대상-이웃 쌍의 수직축에 candidate_offset만큼 떨어진 두 후보
#   진입점을 만들고, BBox 충돌 회피 우선 → y 큰 쪽 우선 순서로 선정한다.
#   푸시 종점은 진입 변화량의 -push_scale 배 (대상을 군집 밖으로 밀어냄).
#   docs/05_clustered_nuts_handling.md의 알고리즘 명세에 대응.
"""Cluster handling: closed-gripper push to disperse clustered nuts.

If the edge-to-edge gap between the target and its nearest neighbor is
below `cluster_dist_threshold_mm` (gap = center distance - sum of each
OBB's half-extent projected onto the target-neighbor line), this module
computes a push plan that:
  1. Enters from one of two candidates perpendicular to the target-neighbor
     line, offset by `candidate_offset_mm`.
  2. Pushes the target across to (target + push_scale * (target - candidate))
     (i.e., -push_scale times the entry direction relative to target).
  3. Returns a ClusterPlan for the action server to execute.

Selection priority (per design doc 3.3):
  1) Candidate whose entry point is NOT inside any other detection's OBB.
  2) Among remaining, the one with larger y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from .target_selector import WorkspaceBox


@dataclass
class ClusterPlan:
    target: object
    neighbor: object
    # 진입점: 후보 중 우선순위로 선정된 위치. 그리퍼 닫고 하강할 좌표.
    entry_xyz_mm: Tuple[float, float, float]
    # 푸시 종점: 대상을 군집 밖으로 밀어낸 후 그리퍼 위치.
    push_end_xyz_mm: Tuple[float, float, float]
    neighbor_distance_mm: float


def choose_cluster_plan(
    detections: Iterable,
    target,
    workspace: WorkspaceBox,
    *,
    cluster_dist_threshold_mm: float,
    candidate_offset_mm: float = 10.0,
    push_scale: float = 1.5,
    push_z_offset_mm: float = 0.0,
    conf_gate: float = 0.40,
    min_depth_mm: float = 2.0,
) -> Optional[ClusterPlan]:
    """대상이 군집이면 closed-gripper push 계획을 반환, 아니면 None."""
    valid = _filter_valid(detections, target, workspace, conf_gate, min_depth_mm)

    # 1. 가장 가까운 이웃 탐색.
    neighbor = _closest_neighbor(valid, target)
    if neighbor is None:
        return None
    tx = float(target.base_xyz.x)
    ty = float(target.base_xyz.y)
    # push_z = 검출 base_z + push_z_offset_mm. 호출측에서 per-class
    # grasp 보정 + 추가 lift offset을 합쳐 넘긴다 (예: cashew는
    # grasp가 base-2mm이고 push는 그 위 +2mm라 결과적으로 base와 동일).
    tz = float(target.base_xyz.z) + float(push_z_offset_mm)
    nx = float(neighbor.base_xyz.x)
    ny = float(neighbor.base_xyz.y)
    dist = math.hypot(nx - tx, ny - ty)
    if dist < 1e-6:
        # dist≈0은 dedup 미스로 보고 제외.
        return None
    # 군집 판정: gap = 중심거리 - 두 OBB를 연결선 방향에 투영한 반지름의 합.
    # gap < cluster_dist_threshold_mm 이면 군집.
    ux = (nx - tx) / dist
    uy = (ny - ty) / dist
    r_target = _projected_half_extent(target, ux, uy)
    r_neighbor = _projected_half_extent(neighbor, ux, uy)
    gap = dist - r_target - r_neighbor
    if gap >= float(cluster_dist_threshold_mm):
        return None

    # 2. cluster_axis: target→neighbor 직선의 수직 단위벡터.
    # 이 축을 따라 candidate_offset만큼 떨어진 두 진입점을 만들면, 푸시 방향이
    # 이웃 BBox와 수직이 되어 대상만 한쪽으로 밀어낼 수 있다.
    ax = -(ny - ty) / dist
    ay = (nx - tx) / dist

    cand_a = (tx + ax * candidate_offset_mm, ty + ay * candidate_offset_mm)
    cand_b = (tx - ax * candidate_offset_mm, ty - ay * candidate_offset_mm)

    # 3. 우선순위 선정.
    blocked_a = _point_hits_other_box(cand_a[0], cand_a[1], valid, ignore=(target,))
    blocked_b = _point_hits_other_box(cand_b[0], cand_b[1], valid, ignore=(target,))
    chosen = _select_candidate(cand_a, cand_b, blocked_a, blocked_b)
    if chosen is None:
        return None

    # 4. 진입점 / 푸시 종점 모두 workspace 안인지 확인.
    if not workspace.contains(chosen[0], chosen[1], tz):
        return None
    push_dx = chosen[0] - tx
    push_dy = chosen[1] - ty
    end_x = tx - float(push_scale) * push_dx
    end_y = ty - float(push_scale) * push_dy
    if not workspace.contains(end_x, end_y, tz):
        return None

    return ClusterPlan(
        target=target,
        neighbor=neighbor,
        entry_xyz_mm=(chosen[0], chosen[1], tz),
        push_end_xyz_mm=(end_x, end_y, tz),
        neighbor_distance_mm=dist,
    )


# ---------------------------------------------------------------------------


def _filter_valid(
    detections: Iterable,
    target,
    workspace: WorkspaceBox,
    conf_gate: float,
    min_depth_mm: float,
) -> List:
    valid: List = []
    for d in detections:
        if d is target:
            continue
        if not bool(getattr(d, "transform_valid", True)):
            continue
        if float(getattr(d, "confidence", 0.0)) < float(conf_gate):
            continue
        base_xyz = getattr(d, "base_xyz", None)
        if base_xyz is None:
            continue
        bz = float(base_xyz.z)
        if bz <= float(min_depth_mm):
            continue
        if not workspace.contains(float(base_xyz.x), float(base_xyz.y), bz):
            continue
        valid.append(d)
    return valid


def _closest_neighbor(detections: List, target):
    tx = float(target.base_xyz.x)
    ty = float(target.base_xyz.y)
    best = None
    best_d2 = float("inf")
    for d in detections:
        dx = float(d.base_xyz.x) - tx
        dy = float(d.base_xyz.y) - ty
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best = d
    return best


def _select_candidate(
    cand_a: Tuple[float, float],
    cand_b: Tuple[float, float],
    blocked_a: bool,
    blocked_b: bool,
) -> Optional[Tuple[float, float]]:
    """우선순위: (1) BBox 비충돌, (2) y 큰 쪽."""
    if not blocked_a and blocked_b:
        return cand_a
    if blocked_a and not blocked_b:
        return cand_b
    if not blocked_a and not blocked_b:
        return cand_a if cand_a[1] >= cand_b[1] else cand_b
    # 둘 다 BBox 안 — 안전을 위해 push 자체를 포기하고 None 반환
    # (호출측은 일반 pick으로 fallback).
    return None


def _point_hits_other_box(
    x: float, y: float, detections: List, ignore: tuple
) -> bool:
    for d in detections:
        if any(d is ign for ign in ignore):
            continue
        if _point_in_oriented_box(x, y, d):
            return True
    return False


def _projected_half_extent(detection, ux: float, uy: float) -> float:
    """OBB를 단위벡터 (ux, uy) 방향에 투영한 half-width (SAT projection)."""
    short_axis = max(1.0, float(getattr(detection, "short_axis_mm", 0.0)))
    long_axis = max(short_axis, float(getattr(detection, "long_axis_mm", short_axis)))
    yaw = float(getattr(detection, "grasp_yaw", 0.0))
    c = math.cos(yaw)
    s = math.sin(yaw)
    return (
        abs(long_axis * 0.5 * (c * ux + s * uy))
        + abs(short_axis * 0.5 * (-s * ux + c * uy))
    )


def _point_in_oriented_box(x: float, y: float, detection) -> bool:
    cx = float(detection.base_xyz.x)
    cy = float(detection.base_xyz.y)
    short_axis = max(1.0, float(getattr(detection, "short_axis_mm", 0.0)))
    long_axis = max(short_axis, float(getattr(detection, "long_axis_mm", short_axis)))
    yaw = float(getattr(detection, "grasp_yaw", 0.0))

    c = math.cos(yaw)
    s = math.sin(yaw)
    dx = x - cx
    dy = y - cy
    local_x = dx * c + dy * s
    local_y = -dx * s + dy * c
    return abs(local_x) <= long_axis * 0.5 and abs(local_y) <= short_axis * 0.5
