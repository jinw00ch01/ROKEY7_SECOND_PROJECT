"""Sliding-window aggregation for YOLO-OBB detections.

Buffers per-frame detections inside a fixed time window and fuses them into
stable instances by class + center-distance clustering.

Fusion rules:
- Group by class_name, then cluster by Euclidean distance between (cx, cy).
- A new detection joins an existing cluster if its center distance to the
  cluster centroid is below `cluster_distance_threshold_px`.
- The fused (cx, cy, width, height) is the median across the cluster.
- Theta uses circular mean with period pi (OBB symmetry).
- confidence is the maximum across the cluster (not mean) to preserve the
  caller's gate semantics.
"""

from __future__ import annotations

import cmath
import time
from collections import deque
from typing import Deque, Iterable, List, Tuple

import numpy as np

from .yolo_detector import ObbDetection


class DetectionAggregator:
    def __init__(
        self,
        window_sec: float = 0.5,
        cluster_distance_px: float = 30.0,
    ) -> None:
        self._window_sec = float(window_sec)
        self._cluster_dist = float(cluster_distance_px)
        self._buffer: Deque[Tuple[float, List[ObbDetection]]] = deque()

    def add(self, detections: Iterable[ObbDetection], stamp: float) -> None:
        self._buffer.append((float(stamp), list(detections)))
        self._prune(stamp)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_sec
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def fuse(self) -> List[ObbDetection]:
        flat: List[ObbDetection] = []
        for _, dets in self._buffer:
            flat.extend(dets)
        if not flat:
            return []

        by_class: dict[str, List[ObbDetection]] = {}
        for d in flat:
            by_class.setdefault(d.class_name, []).append(d)

        fused: List[ObbDetection] = []
        for cls_name, dets in by_class.items():
            clusters: List[List[ObbDetection]] = []
            for d in dets:
                placed = False
                for cluster in clusters:
                    cx_mean = float(np.mean([m.cx for m in cluster]))
                    cy_mean = float(np.mean([m.cy for m in cluster]))
                    if (d.cx - cx_mean) ** 2 + (d.cy - cy_mean) ** 2 <= self._cluster_dist ** 2:
                        cluster.append(d)
                        placed = True
                        break
                if not placed:
                    clusters.append([d])

            for cluster in clusters:
                fused.append(self._fuse_one(cluster))

        return fused

    @staticmethod
    def _fuse_one(cluster: List[ObbDetection]) -> ObbDetection:
        cxs = [d.cx for d in cluster]
        cys = [d.cy for d in cluster]
        ws = [d.width for d in cluster]
        hs = [d.height for d in cluster]
        # Circular mean with period pi (OBB orientation symmetry).
        z = sum(cmath.exp(2j * d.theta) for d in cluster) / len(cluster)
        theta = 0.0 if abs(z) < 1e-9 else cmath.phase(z) / 2.0
        best = max(cluster, key=lambda d: d.confidence)
        return ObbDetection(
            class_idx=best.class_idx,
            class_name=best.class_name,
            confidence=best.confidence,
            cx=float(np.median(cxs)),
            cy=float(np.median(cys)),
            width=float(np.median(ws)),
            height=float(np.median(hs)),
            theta=float(theta),
        )

    def clear(self) -> None:
        self._buffer.clear()

    def buffer_size(self) -> int:
        return len(self._buffer)
