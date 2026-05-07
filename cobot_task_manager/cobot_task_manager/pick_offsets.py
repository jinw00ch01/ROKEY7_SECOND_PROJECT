# 한국어 요약:
#   클래스별 z offset을 YAML에서 읽어오는 single source of truth 로더이다.
#   /task/start 경로와 scripts/pick_*.py가 동일한 오프셋을 쓰도록 한다.
#   resolver는 explicit -> env var -> ament-share -> 소스 트리 순으로 후보를
#   훑고, 파일이 없거나 키가 깨졌을 때도 DEFAULT_OFFSETS_MM으로 fallback해
#   로봇이 멈추지 않게 한다.
"""Per-class Z-offset loader.

Single source of truth for the offset added to grasp_xyz.z at pick time.
The canonical YAML lives at ``cobot_config/config/pick_offsets.yaml``.

Resolution order:
  1. Caller-provided explicit_path
  2. Env var COBOT_PICK_OFFSETS_PATH
  3. Installed share dir (ament_index_python -> cobot_config)
  4. Source-tree fallback (sibling cobot_config/ next to this workspace)

Always returns a dict with all four canonical classes; missing or invalid
entries fall back to DEFAULT_OFFSETS_MM. Missing files log a warning and
return defaults so the robot can still pick (at z = perception z).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

DEFAULT_OFFSETS_MM: Dict[str, float] = {
    "almond": 0.0,
    "cashew": 0.0,
    "pistachio": 0.0,
    "walnut": -1.0,
}
ENV_OVERRIDE = "COBOT_PICK_OFFSETS_PATH"
_YAML_KEY = "per_class_z_offset_mm"


def _candidate_paths(explicit_path: Optional[str]) -> List[Path]:
    # 4단계 fallback resolver:
    #   1) explicit_path: 호출자/launch 파라미터가 명시한 경로 (최우선).
    #   2) ENV_OVERRIDE: 운영 환경에서 빠르게 덮어쓰기 위한 환경 변수.
    #   3) ament-share: colcon install 후 정상 배포된 cobot_config의 위치.
    #   4) 소스 트리 fallback: install 안 된 dev 환경에서도 동작하도록.
    # 순서는 "사용자 지정 -> 환경 -> 정상 install -> dev 편의" 우선순위를 따른다.
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
            / "pick_offsets.yaml"
        )
    except Exception:
        # ament_index가 import 안 되거나 패키지 미배포면 다음 후보로 넘어감.
        pass
    out.append(
        Path(__file__).resolve().parents[2]
        / "cobot_config"
        / "config"
        / "pick_offsets.yaml"
    )
    return out


def load_pick_offsets(explicit_path: Optional[str] = None) -> Dict[str, float]:
    """Return per-class z offsets in mm.

    Always returns the full 4-class dict; classes missing from the YAML
    fall back to ``DEFAULT_OFFSETS_MM``.
    """
    import yaml

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
                "%s: missing/invalid %r mapping; using defaults", path, _YAML_KEY
            )
            return dict(DEFAULT_OFFSETS_MM)

        merged = dict(DEFAULT_OFFSETS_MM)
        for cls, val in source.items():
            try:
                merged[str(cls)] = float(val)
            except (TypeError, ValueError):
                logger.warning(
                    "%s: %s[%r]=%r is not a number; using default",
                    path,
                    _YAML_KEY,
                    cls,
                    val,
                )
        logger.info("Loaded pick offsets from %s: %s", path, merged)
        return merged

    logger.warning(
        "pick_offsets.yaml not found on any candidate path; using defaults: %s",
        DEFAULT_OFFSETS_MM,
    )
    return dict(DEFAULT_OFFSETS_MM)
