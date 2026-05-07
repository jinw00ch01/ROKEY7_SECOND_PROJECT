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
