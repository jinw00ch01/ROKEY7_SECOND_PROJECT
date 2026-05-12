# 한국어 요약:
#   YOLO-OBB detection을 슬라이딩 윈도우(multi_frame_window_sec)로 모아 융합하는 모듈.
#   단일 프레임 노이즈(잘못된 confidence, OBB 흔들림)를 완화하기 위해 클래스별로
#   중심점 거리(cluster_distance_threshold_px) 기반 클러스터링을 수행한다.
#   클러스터 내 cx,cy,w,h는 median, theta는 주기 pi의 circular mean,
#   confidence는 최댓값을 채택하여 호출측 게이트 의미를 보존한다.
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
from typing import Deque, Dict, Iterable, List, Mapping, Tuple, Union

import numpy as np

from .yolo_detector import ObbDetection

# 클래스별 lookup에서 해당 키가 없을 때 fallback할 기본 임계값.
_DEFAULT_FALLBACK_PX = 30.0


class DetectionAggregator:
    def __init__(
        self,
        window_sec: float = 0.5,
        cluster_distance_px: Union[float, Mapping[str, float]] = 30.0,
    ) -> None:
        self._window_sec = float(window_sec)
        # cluster_distance_px가 dict면 클래스별 lookup, float면 모든 클래스 동일.
        # 내부적으로는 항상 dict + fallback float로 정규화해 fuse() 로직을 단순화.
        if isinstance(cluster_distance_px, Mapping):
            self._cluster_dist_by_class: Dict[str, float] = {
                str(k): float(v) for k, v in cluster_distance_px.items()
            }
            # dict 모드의 fallback은 캡쳐된 값들의 평균 (혹은 첫 값) — 외부에서
            # 명시한 클래스만 쓰는 게 일반적이라 큰 의미는 없지만, 미지의
            # 클래스가 들어와도 안전하게 작동하도록 둔다.
            self._cluster_dist_fallback: float = (
                next(iter(self._cluster_dist_by_class.values()), _DEFAULT_FALLBACK_PX)
            )
        else:
            self._cluster_dist_by_class = {}
            self._cluster_dist_fallback = float(cluster_distance_px)
        self._buffer: Deque[Tuple[float, List[ObbDetection]]] = deque()

    def _threshold_for(self, class_name: str) -> float:
        return self._cluster_dist_by_class.get(class_name, self._cluster_dist_fallback)

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
            # 클래스마다 임계값이 다를 수 있으므로 inner loop 시작 전에 lookup.
            threshold_sq = self._threshold_for(cls_name) ** 2
            clusters: List[List[ObbDetection]] = []
            for d in dets:
                placed = False
                for cluster in clusters:
                    cx_mean = float(np.mean([m.cx for m in cluster]))
                    cy_mean = float(np.mean([m.cy for m in cluster]))
                    # 중심점 Euclidean 거리가 임계값 이내면 같은 인스턴스로 본다.
                    if (d.cx - cx_mean) ** 2 + (d.cy - cy_mean) ** 2 <= threshold_sq:
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
