"""YOLOv8-OBB inference wrapper.

Loads the trained nut OBB model and parses ultralytics OBB output into a flat
list of dicts with normalized rotation theta in [-pi/2, pi/2].
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional

import numpy as np


def _normalize_theta(theta_rad: float) -> float:
    a = ((theta_rad + math.pi / 2.0) % math.pi) - math.pi / 2.0
    return a


@dataclass
class ObbDetection:
    class_idx: int
    class_name: str
    confidence: float
    cx: float
    cy: float
    width: float
    height: float
    theta: float


class YoloObbDetector:
    def __init__(
        self,
        model_path: str,
        class_names: Iterable[str],
        imgsz: int = 800,
        conf_threshold: float = 0.40,
        iou_threshold: float = 0.50,
        device: Optional[str] = None,
    ) -> None:
        from ultralytics import YOLO  # heavy import deferred

        self._model = YOLO(model_path)
        self._class_names = list(class_names)
        self._imgsz = int(imgsz)
        self._conf = float(conf_threshold)
        self._iou = float(iou_threshold)
        self._device = device  # None lets ultralytics pick

    def infer(self, frame_bgr: np.ndarray) -> List[ObbDetection]:
        kwargs = dict(
            conf=self._conf,
            iou=self._iou,
            imgsz=self._imgsz,
            verbose=False,
        )
        if self._device is not None:
            kwargs["device"] = self._device
        results = self._model(frame_bgr, **kwargs)

        out: List[ObbDetection] = []
        for r in results:
            obb = getattr(r, "obb", None)
            if obb is None or len(obb) == 0:
                continue
            xywhr = obb.xywhr.cpu().numpy()  # (N, 5)
            confs = obb.conf.cpu().numpy()
            classes = obb.cls.cpu().numpy().astype(int)
            for i in range(xywhr.shape[0]):
                cx, cy, w, h, theta = xywhr[i].tolist()
                cls_idx = int(classes[i])
                if cls_idx < 0 or cls_idx >= len(self._class_names):
                    continue
                out.append(
                    ObbDetection(
                        class_idx=cls_idx,
                        class_name=self._class_names[cls_idx],
                        confidence=float(confs[i]),
                        cx=float(cx),
                        cy=float(cy),
                        width=float(w),
                        height=float(h),
                        theta=_normalize_theta(float(theta)),
                    )
                )
        return out
