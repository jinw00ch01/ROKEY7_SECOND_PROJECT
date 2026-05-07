"""Tests for cobot_task_manager.pick_offsets.load_pick_offsets."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cobot_task_manager.pick_offsets import (
    DEFAULT_OFFSETS_MM,
    ENV_OVERRIDE,
    load_pick_offsets,
)


_CANONICAL_CLASSES = ("almond", "cashew", "pistachio", "walnut")


def _write_yaml(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def test_explicit_path_wins(tmp_path):
    cfg = tmp_path / "pick_offsets.yaml"
    _write_yaml(
        cfg,
        """
        per_class_z_offset_mm:
          almond: 1.5
          cashew: -2.5
          pistachio: 0.25
          walnut: -3.0
        """,
    )

    offsets = load_pick_offsets(str(cfg))

    assert offsets == {
        "almond": 1.5,
        "cashew": -2.5,
        "pistachio": 0.25,
        "walnut": -3.0,
    }


def test_missing_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_OVERRIDE, raising=False)
    nonexistent = tmp_path / "absent.yaml"

    offsets = load_pick_offsets(str(nonexistent))

    # Should still return all canonical classes with default values.
    for cls in _CANONICAL_CLASSES:
        assert offsets[cls] == DEFAULT_OFFSETS_MM[cls]


def test_partial_yaml_fills_missing_with_defaults(tmp_path):
    cfg = tmp_path / "partial.yaml"
    _write_yaml(
        cfg,
        """
        per_class_z_offset_mm:
          walnut: -2.0
        """,
    )

    offsets = load_pick_offsets(str(cfg))

    assert offsets["walnut"] == -2.0
    assert offsets["almond"] == DEFAULT_OFFSETS_MM["almond"]
    assert offsets["cashew"] == DEFAULT_OFFSETS_MM["cashew"]
    assert offsets["pistachio"] == DEFAULT_OFFSETS_MM["pistachio"]


def test_invalid_value_falls_back_to_default_for_that_key(tmp_path):
    cfg = tmp_path / "bad.yaml"
    _write_yaml(
        cfg,
        """
        per_class_z_offset_mm:
          almond: "not-a-number"
          walnut: -1.5
        """,
    )

    offsets = load_pick_offsets(str(cfg))

    assert offsets["almond"] == DEFAULT_OFFSETS_MM["almond"]
    assert offsets["walnut"] == -1.5


def test_missing_top_key_returns_full_defaults(tmp_path):
    cfg = tmp_path / "wrong.yaml"
    _write_yaml(
        cfg,
        """
        # Wrong top-level key on purpose.
        offsets:
          walnut: -10
        """,
    )

    offsets = load_pick_offsets(str(cfg))

    assert offsets == DEFAULT_OFFSETS_MM


def test_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "via_env.yaml"
    _write_yaml(
        cfg,
        """
        per_class_z_offset_mm:
          cashew: 7.0
        """,
    )
    monkeypatch.setenv(ENV_OVERRIDE, str(cfg))

    offsets = load_pick_offsets()  # no explicit path

    assert offsets["cashew"] == 7.0
    # Other classes still default.
    assert offsets["walnut"] == DEFAULT_OFFSETS_MM["walnut"]


def test_explicit_path_beats_env(tmp_path, monkeypatch):
    env_cfg = tmp_path / "env.yaml"
    explicit_cfg = tmp_path / "explicit.yaml"
    _write_yaml(env_cfg, "per_class_z_offset_mm: { cashew: 99.0 }\n")
    _write_yaml(explicit_cfg, "per_class_z_offset_mm: { cashew: 1.0 }\n")
    monkeypatch.setenv(ENV_OVERRIDE, str(env_cfg))

    offsets = load_pick_offsets(str(explicit_cfg))

    assert offsets["cashew"] == 1.0


def test_canonical_yaml_in_repo_loads():
    """The committed cobot_config/config/pick_offsets.yaml must parse."""
    repo_root = Path(__file__).resolve().parents[2]
    canonical = repo_root / "cobot_config" / "config" / "pick_offsets.yaml"
    if not canonical.is_file():
        pytest.skip("canonical pick_offsets.yaml not present in source tree")

    offsets = load_pick_offsets(str(canonical))

    for cls in _CANONICAL_CLASSES:
        assert cls in offsets
        assert isinstance(offsets[cls], float)
