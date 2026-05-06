from cobot_voice.question_flow import get_message, load_question_flow


def test_load_question_flow():
    messages = load_question_flow()

    assert messages["wake_response"] == "네, 맞춤 견과류 콤보를 준비해드릴게요."
    assert "ask_state" in messages
    assert "ask_intensity" in messages


def test_get_message():
    assert get_message("wake_response") == "네, 맞춤 견과류 콤보를 준비해드릴게요."
    assert get_message("ask_state").startswith("오늘 컨디션은 어떤가요?")
    assert get_message("ask_intensity").startswith("그 정도는 어느 정도인가요?")


def test_confirm_template_formatting():
    message = get_message(
        "confirm_template",
        combo_text="캐슈넛 두 개와 호두 두 개",
    )

    assert message == "말씀하신 상태에 맞춰 캐슈넛 두 개와 호두 두 개를 준비해드릴게요."


def main():
    test_load_question_flow()
    test_get_message()
    test_confirm_template_formatting()
    print("All question flow tests passed.")


if __name__ == "__main__":
    main()
