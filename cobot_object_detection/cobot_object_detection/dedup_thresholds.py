# 한국어 요약:
#   클래스별 픽셀 거리 임계값을 YAML에서 읽어오는 single source of truth 로더.
#   object_detection_node와 perception_transform_node가 동일 값을 쓰도록 한다.
#   resolver는 explicit -> env var -> ament-share -> 소스 트리 순으로 후보를
#   훑고, 파일이 없거나 키가 깨졌을 때도 fallback 단일 값으로 채워 노드가
#   멈추지 않게 한다.
"""Per-class detection-dedup threshold loader.

Single source of truth for the per-class pixel-distance threshold used by
``DetectionAggregator`` to fuse multi-frame YOLO-OBB detections. The
canonical YAML lives at ``cobot_config/config/dedup_thresholds.yaml``.

Resolution order:
  1. Caller-provided explicit_path
  2. Env var COBOT_DEDUP_THRESHOLDS_PATH
  3. Installed share dir (ament_index_python -> cobot_config)
  4. Source-tree fallback (sibling cobot_config/ next to this workspace)

Returns a dict ``{class_name: threshold_px}`` covering at least the four
canonical classes; missing or invalid entries fall back to the caller's
``fallback_px`` (the legacy ``cluster_distance_threshold_px`` ROS param).
Missing files log a warning and return the fallback for every class so
detection continues to work.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

CANONICAL_CLASSES = ("almond", "cashew", "pistachio", "walnut")
ENV_OVERRIDE = "COBOT_DEDUP_THRESHOLDS_PATH"
_YAML_KEY = "per_class_distance_threshold_px"


def _candidate_paths(explicit_path: Optional[str]) -> List[Path]:
    # 4단계 fallback resolver — pick_offsets.py와 동일한 우선순위 정책:
    #   1) explicit_path: 호출자/launch 파라미터가 명시한 경로 (최우선).
    #   2) ENV_OVERRIDE: 운영 환경에서 빠르게 덮어쓰기 위한 환경 변수.
    #   3) ament-share: colcon install 후 정상 배포된 cobot_config의 위치.
    #   4) 소스 트리 fallback: install 안 된 dev 환경에서도 동작하도록.
    out: List[Path] = []
    if explicit_path:
        out.append(Path(explicit_path).expanduser())
    env_value = os.getenv(ENV_OVERRIDE, "").strip()
    if env_value:
        out.append(Path(env_value).expanduser())
    try:
        from ament_index_python.packages import get_package_share_directory

        out.append(
            Path(get_package_share_directory("cobot_config"))
            / "config"
            / "dedup_thresholds.yaml"
        )
    except Exception:
        # ament_index가 import 안 되거나 패키지 미배포면 다음 후보로 넘어감.
        pass
    out.append(
        Path(__file__).resolve().parents[2]
        / "cobot_config"
        / "config"
        / "dedup_thresholds.yaml"
    )
    return out


def load_dedup_thresholds(
    explicit_path: Optional[str] = None,
    fallback_px: float = 30.0,
    class_names: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Return per-class pixel-distance thresholds for detection dedup.

    Always returns a dict covering at least ``class_names`` (default
    canonical four). Classes missing from the YAML fall back to
    ``fallback_px``. Missing files log a warning and return
    ``{cls: fallback_px}`` for every class.
    """
    import yaml

    classes = list(class_names) if class_names else list(CANONICAL_CLASSES)
    defaults = {cls: float(fallback_px) for cls in classes}

    for path in _candidate_paths(explicit_path):
        if not path or not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning("%s: failed to parse (%s); trying next candidate", path, exc)
            continue

        source = data.get(_YAML_KEY)
        if not isinstance(source, dict):
            logger.warning(
                "%s: missing/invalid %r mapping; using fallback=%s for all classes",
                path,
                _YAML_KEY,
                fallback_px,
            )
            return defaults

        merged = dict(defaults)
        for cls, val in source.items():
            try:
                merged[str(cls)] = float(val)
            except (TypeError, ValueError):
                logger.warning(
                    "%s: %s[%r]=%r is not a number; using fallback=%s",
                    path,
                    _YAML_KEY,
                    cls,
                    val,
                    fallback_px,
                )
        logger.info("Loaded dedup thresholds from %s: %s", path, merged)
        return merged

    logger.warning(
        "dedup_thresholds.yaml not found on any candidate path; "
        "using fallback=%s for all classes",
        fallback_px,
    )
    return defaults
