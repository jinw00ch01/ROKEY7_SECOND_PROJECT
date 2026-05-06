from cobot_voice import firebase_bridge


def _capture_updates():
    updates = []
    original_safe_update = firebase_bridge._safe_update

    def fake_safe_update(fields):
        updates.append(fields)
        return True

    firebase_bridge._safe_update = fake_safe_update
    return updates, original_safe_update


def test_reset_session_payload():
    updates, original_safe_update = _capture_updates()
    try:
        assert firebase_bridge.reset_session() is True
    finally:
        firebase_bridge._safe_update = original_safe_update

    payload = updates[-1]
    assert payload["display_state"] == "idle"
    assert payload["question"] == ""
    assert payload["transcript"] == ""
    assert payload["categories"] == []
    assert payload["combo"] == []
    assert payload["success"] is False


def test_publish_question_payload():
    updates, original_safe_update = _capture_updates()
    try:
        assert firebase_bridge.publish_question("오늘 컨디션은 어떤가요?", "asking_state")
    finally:
        firebase_bridge._safe_update = original_safe_update

    payload = updates[-1]
    assert payload["display_state"] == "asking_state"
    assert payload["question"] == "오늘 컨디션은 어떤가요?"
    assert payload["error"] == ""


def test_publish_recommendation_result_payload():
    updates, original_safe_update = _capture_updates()
    order = {
        "request_id": "20260506_120000",
        "recognized_text": "너무 피곤하고 집중이 안 돼요 많이",
        "categories": ["fatigue", "focus"],
        "intensity": "high",
        "combo": [
            {"nut": "cashew", "count": 3},
            {"nut": "walnut", "count": 3},
        ],
        "combo_text": "캐슈넛 세 개와 호두 세 개",
        "confirm_message": "말씀하신 상태에 맞춰 캐슈넛 세 개와 호두 세 개를 준비해드릴게요.",
        "success": True,
    }

    try:
        assert firebase_bridge.publish_recommendation_result(order)
    finally:
        firebase_bridge._safe_update = original_safe_update

    payload = updates[-1]
    assert payload["display_state"] == "result_ready"
    assert payload["transcript"] == order["recognized_text"]
    assert payload["categories"] == ["fatigue", "focus"]
    assert payload["intensity"] == "high"
    assert payload["combo"] == order["combo"]
    assert payload["combo_text"] == order["combo_text"]
    assert payload["confirm_message"] == order["confirm_message"]
    assert payload["success"] is True
    assert payload["theme"]["primary_category"] == "fatigue"
    assert payload["theme"]["primary_nut"] == "cashew"
    assert payload["theme"]["primary_color"] == "#F2C879"


def test_error_and_unknown_state_payloads():
    updates, original_safe_update = _capture_updates()
    try:
        assert firebase_bridge.publish_error("테스트 오류")
        assert firebase_bridge.update_display_state("unknown_state")
    finally:
        firebase_bridge._safe_update = original_safe_update

    error_payload = updates[-2]
    unknown_state_payload = updates[-1]

    assert error_payload["display_state"] == "error"
    assert error_payload["error"] == "테스트 오류"
    assert error_payload["success"] is False
    assert unknown_state_payload["display_state"] == "error"


def test_build_theme_fallbacks():
    assert firebase_bridge.build_theme(["diet"], [])["primary_color"] == "#8BC34A"
    assert (
        firebase_bridge.build_theme([], [{"nut": "almond", "count": 2}])[
            "primary_category"
        ]
        == "blood_sugar"
    )
    assert firebase_bridge.build_theme([], []) == firebase_bridge.DEFAULT_THEME


def main():
    test_reset_session_payload()
    test_publish_question_payload()
    test_publish_recommendation_result_payload()
    test_error_and_unknown_state_payloads()
    test_build_theme_fallbacks()
    print("All Firebase bridge tests passed.")


if __name__ == "__main__":
    main()
