"""Tests for firebase_status_bridge — parsing + state mapping logic.

The bridge node itself is exercised end-to-end at runtime; these unit
tests cover the pure functions and the state translation table so we
catch regressions in message parsing without spinning up rclpy.
"""

from __future__ import annotations

import pytest

from cobot_voice.firebase_status_bridge import (
    _NUT_CLASSES,
    _STATUS_TO_ROBOT_STATE,
    parse_result,
    parse_status,
)


# --- parse_status -----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_state, expected_info",
    [
        ("detect", "detect", ""),
        ("init", "init", ""),
        ("done", "done", ""),
        ("select_target cashew", "select_target", "cashew"),
        ("pick_and_place walnut", "pick_and_place", "walnut"),
        ("aborted home_failed", "aborted", "home_failed"),
        ("aborted failure_code=3", "aborted", "failure_code=3"),
        ("safety_stop", "safety_stop", ""),
        # whitespace tolerance
        ("  detect  ", "detect", ""),
        ("pick_and_place   cashew  ", "pick_and_place", "cashew"),
        # info that itself contains spaces
        ("done counts={'walnut': 1}", "done", "counts={'walnut': 1}"),
        ("", "", ""),
        ("   ", "", ""),
    ],
)
def test_parse_status(raw, expected_state, expected_info):
    state, info = parse_status(raw)
    assert state == expected_state
    assert info == expected_info


# --- parse_result -----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_outcome, expected_info",
    [
        ("success", "success", ""),
        ("failure", "failure", ""),
        ("success counts={'walnut': 1, 'cashew': 0} skipped=[]",
         "success", "counts={'walnut': 1, 'cashew': 0} skipped=[]"),
        ("failure home_failed", "failure", "home_failed"),
        ("failure failure_code=3", "failure", "failure_code=3"),
        # case-insensitive outcome
        ("Failure something", "failure", "something"),
        ("", "", ""),
    ],
)
def test_parse_result(raw, expected_outcome, expected_info):
    outcome, info = parse_result(raw)
    assert outcome == expected_outcome
    assert info == expected_info


# --- state mapping ----------------------------------------------------


def test_status_map_covers_every_taskstate_except_idle():
    """The map should cover every TaskState value except `idle`.

    `idle` is intentionally not mirrored — it would clobber the voice
    flow's display_state.
    """
    from cobot_task_manager.task_state import TaskState

    expected_keys = {s.value for s in TaskState if s.value != "idle"}
    assert set(_STATUS_TO_ROBOT_STATE.keys()) == expected_keys


def test_status_map_only_emits_known_robot_states():
    """Every value in the map must be a valid ROBOT_PROGRESS_STATES entry."""
    from cobot_voice.firebase_bridge import ROBOT_PROGRESS_STATES

    for status, robot_state in _STATUS_TO_ROBOT_STATE.items():
        assert robot_state in ROBOT_PROGRESS_STATES, (
            f"status {status!r} -> {robot_state!r} not in ROBOT_PROGRESS_STATES"
        )


def test_nut_classes_match_task_manager_priority():
    """Bridge's nut-class set must match the order book's class list."""
    expected = {"almond", "cashew", "pistachio", "walnut"}
    assert _NUT_CLASSES == expected


# --- robot progress publisher behavior --------------------------------


def test_publish_robot_progress_writes_robot_state_field(monkeypatch):
    from cobot_voice import firebase_bridge

    captured = {}

    def fake_safe_update(payload):
        captured["payload"] = payload
        return True

    monkeypatch.setattr(firebase_bridge, "_safe_update", fake_safe_update)

    firebase_bridge.publish_robot_progress(
        "picking", target_class="cashew", remaining=2
    )

    assert captured["payload"] == {
        "robot_state": "picking",
        "robot_target_class": "cashew",
        "robot_remaining": 2,
    }


def test_publish_robot_progress_unknown_state_falls_back_to_error(monkeypatch):
    from cobot_voice import firebase_bridge

    captured = {}
    monkeypatch.setattr(
        firebase_bridge, "_safe_update", lambda payload: captured.setdefault("p", payload)
    )

    firebase_bridge.publish_robot_progress("not_a_real_state", error="bad")

    assert captured["p"]["robot_state"] == "error"
    assert captured["p"]["robot_error"] == "bad"


def test_publish_robot_progress_does_not_touch_display_state(monkeypatch):
    """voice flow's display_state must not be overwritten."""
    from cobot_voice import firebase_bridge

    payload_seen = {}
    monkeypatch.setattr(
        firebase_bridge, "_safe_update", lambda p: payload_seen.update(p)
    )

    firebase_bridge.publish_robot_progress("detecting")

    assert "display_state" not in payload_seen
    assert payload_seen["robot_state"] == "detecting"
