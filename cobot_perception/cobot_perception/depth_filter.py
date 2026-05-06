"""Depth lookup for an OBB detection.

RealSense aligned depth images are uint16 with values in millimeters.
We pull the median of all valid pixels inside the OBB rotated rectangle
to be robust to dropouts at the rim of small objects (typical for nuts).

`median_inside_obb` returns NaN when no valid pixel is found, so callers
can mark the detection invalid without raising.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np


def _obb_polygon(cx: float, cy: float, w: float, h: float, theta_rad: float) -> np.ndarray:
    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)
    half_w = w / 2.0
    half_h = h / 2.0
    corners = np.array(
        [
            [-half_w, -half_h],
            [half_w, -half_h],
            [half_w, half_h],
            [-half_w, half_h],
        ],
        dtype=np.float64,
    )
    R = np.array([[cos_t, -sin_t], [sin_t, cos_t]], dtype=np.float64)
    rotated = corners @ R.T
    rotated[:, 0] += cx
    rotated[:, 1] += cy
    return rotated


def _polygon_mask(poly: np.ndarray, height: int, width: int) -> np.ndarray:
    xs = np.arange(width, dtype=np.float64)
    ys = np.arange(height, dtype=np.float64)
    grid_x, grid_y = np.meshgrid(xs, ys)
    inside = np.ones((height, width), dtype=bool)
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        edge_x = bx - ax
        edge_y = by - ay
        # Sign of cross product (b-a) x (p-a). For a convex CCW polygon all signs match.
        cross = edge_x * (grid_y - ay) - edge_y * (grid_x - ax)
        inside &= cross >= 0.0
    if not inside.any():
        # corners may have been emitted CW, retry with the opposite sign
        inside = np.ones((height, width), dtype=bool)
        for i in range(len(poly)):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % len(poly)]
            edge_x = bx - ax
            edge_y = by - ay
            cross = edge_x * (grid_y - ay) - edge_y * (grid_x - ax)
            inside &= cross <= 0.0
    return inside


def median_inside_obb(
    depth_mm: np.ndarray,
    cx: float,
    cy: float,
    width: float,
    height: float,
    theta_rad: float,
    min_depth_mm: float = 50.0,
    max_depth_mm: float = 1500.0,
    inset_factor: float = 0.7,
) -> float:
    if depth_mm.ndim != 2:
        raise ValueError(f"depth must be 2D, got {depth_mm.shape}")
    h, w = depth_mm.shape
    poly = _obb_polygon(cx, cy, width * inset_factor, height * inset_factor, theta_rad)
    # crop bounding box of polygon to limit mask cost
    xmin = int(max(0, math.floor(poly[:, 0].min())))
    xmax = int(min(w, math.ceil(poly[:, 0].max())))
    ymin = int(max(0, math.floor(poly[:, 1].min())))
    ymax = int(min(h, math.ceil(poly[:, 1].max())))
    if xmax <= xmin or ymax <= ymin:
        return float("nan")

    sub_depth = depth_mm[ymin:ymax, xmin:xmax]
    sub_poly = poly.copy()
    sub_poly[:, 0] -= xmin
    sub_poly[:, 1] -= ymin
    mask = _polygon_mask(sub_poly, sub_depth.shape[0], sub_depth.shape[1])
    valid = (
        mask
        & (sub_depth >= min_depth_mm)
        & (sub_depth <= max_depth_mm)
    )
    if not valid.any():
        return float("nan")
    return float(np.median(sub_depth[valid]))


def depth_at_pixel(
    depth_mm: np.ndarray,
    cx: float,
    cy: float,
    min_depth_mm: float = 50.0,
    max_depth_mm: float = 1500.0,
) -> Optional[float]:
    if depth_mm.ndim != 2:
        raise ValueError(f"depth must be 2D, got {depth_mm.shape}")
    h, w = depth_mm.shape
    ix = int(round(cx))
    iy = int(round(cy))
    if ix < 0 or ix >= w or iy < 0 or iy >= h:
        return None
    z = float(depth_mm[iy, ix])
    if z < min_depth_mm or z > max_depth_mm:
        return None
    return z
