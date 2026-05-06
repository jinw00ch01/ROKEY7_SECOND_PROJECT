from cobot_voice.question_flow import get_message, load_question_flow


def test_load_question_flow():
    messages = load_question_flow()

    for key in (
        "wake_response",
        "ask_state",
        "ask_intensity",
        "retry_state",
        "retry_intensity",
        "confirm_template",
    ):
        assert key in messages
        assert messages[key]
    assert "{combo_text}" in messages["confirm_template"]


def test_get_message():
    messages = load_question_flow()

    assert get_message("wake_response") == messages["wake_response"]
    assert get_message("ask_state") == messages["ask_state"]
    assert get_message("ask_intensity") == messages["ask_intensity"]


def test_confirm_template_formatting():
    message = get_message(
        "confirm_template",
        combo_text="캐슈넛 두 개와 호두 두 개",
    )

    assert "캐슈넛 두 개와 호두 두 개" in message
    assert "{combo_text}" not in message


def main():
    test_load_question_flow()
    test_get_message()
    test_confirm_template_formatting()
    print("All question flow tests passed.")


if __name__ == "__main__":
    main()
