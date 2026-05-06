import argparse
import json
import logging
import time

from cobot_voice.keyword_extractor import DEFAULT_OUTPUT_PATH, save_recommendation_order
from cobot_voice.firebase_bridge import (
    build_theme,
    publish_completed,
    publish_dispatching,
    publish_error,
    publish_question,
    publish_recommendation_result,
    publish_transcript,
    reset_session,
    update_display_state,
)
from cobot_voice.nut_recommendation import (
    _get_config_dir,
    build_combo,
    extract_categories,
    extract_intensity,
    format_combo_text,
    load_json,
)
from cobot_voice.question_flow import get_message


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def configure_logging(debug=False):
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s: %(message)s",
    )


def speak(text):
    print(f"[TTS] {text}")


def wait_for_wake_word(wakeup, poll_interval=0.05, should_continue=None):
    logger.info("Waiting for wake word.")
    while should_continue is None or should_continue():
        if wakeup.is_wakeup():
            logger.info("Wake word detected.")
            return True
        time.sleep(poll_interval)
    logger.info("Wake word wait stopped before detection.")
    return False


def listen_text(stt=None, debug=False, prompt="사용자 입력"):
    if debug:
        return input(f"{prompt}> ").strip()
    if stt is None:
        raise ValueError("stt is required when debug=False")
    return stt.speech2text()


def wait_for_wake_word_with_optional_mic(wakeup, mic=None, should_continue=None):
    if mic is not None:
        mic.open_stream()
        wakeup.set_stream(mic.stream)

    try:
        return wait_for_wake_word(wakeup, should_continue=should_continue)
    finally:
        if mic is not None:
            mic.close_stream()


def build_recommendation_from_parts(state_text, intensity_text):
    config_dir = _get_config_dir()
    categories_config = load_json(config_dir / "keyword_categories.json")
    combo_rules = load_json(config_dir / "nut_combo_rules.json")

    categories = extract_categories(state_text, categories_config)
    intensity = extract_intensity(intensity_text)
    combo = build_combo(categories, intensity, combo_rules, categories_config)

    recognized_text = " ".join(
        part for part in (state_text.strip(), intensity_text.strip()) if part
    )

    return {
        "recognized_text": recognized_text,
        "categories": categories,
        "intensity": intensity,
        "combo": combo,
        "combo_text": format_combo_text(combo),
    }


def run_recommendation_flow(
    stt=None,
    wakeup=None,
    mic=None,
    debug=False,
    wait_for_wake=True,
    dispatch_callback=None,
    should_continue=None,
):
    logger.debug("Starting recommendation flow. debug=%s wait_for_wake=%s", debug, wait_for_wake)
    reset_session()

    try:
        if wait_for_wake:
            if debug:
                input("Wake word debug mode: Enter를 누르면 wake word 감지로 처리합니다.")
            else:
                if wakeup is None:
                    raise ValueError("wakeup is required when wait_for_wake=True and debug=False")
                wake_detected = wait_for_wake_word_with_optional_mic(
                    wakeup=wakeup,
                    mic=mic,
                    should_continue=should_continue,
                )
                if not wake_detected:
                    update_display_state("idle")
                    return None

        wake_response = get_message("wake_response")
        publish_question(wake_response, "wake_detected")
        speak(wake_response)

        ask_state = get_message("ask_state")
        publish_question(ask_state, "asking_state")
        speak(ask_state)
        update_display_state("listening_state")
        state_text = listen_text(stt=stt, debug=debug, prompt="상태")
        publish_transcript(state_text)

        config_dir = _get_config_dir()
        categories_config = load_json(config_dir / "keyword_categories.json")
        categories = extract_categories(state_text, categories_config)

        if not categories:
            logger.info("No category found on first attempt; asking retry_state.")
            retry_state = get_message("retry_state")
            publish_question(retry_state, "asking_state")
            speak(retry_state)
            update_display_state("listening_state")
            state_text = listen_text(stt=stt, debug=debug, prompt="상태 재입력")
            publish_transcript(state_text)
            categories = extract_categories(state_text, categories_config)

        if not categories:
            logger.info("No category found after retry; saving unsuccessful order.")
            recommendation = {
                "recognized_text": state_text,
                "categories": [],
                "intensity": "normal",
                "combo": [],
                "combo_text": "",
            }
            order = save_recommendation_order(recommendation)
            publish_error("상태 카테고리를 찾지 못했습니다.")
            return order

        ask_intensity = get_message("ask_intensity")
        update_display_state(
            "asking_intensity",
            categories=categories,
            theme=build_theme(categories, []),
        )
        publish_question(ask_intensity, "asking_intensity")
        speak(ask_intensity)
        update_display_state("listening_intensity")
        intensity_text = listen_text(stt=stt, debug=debug, prompt="강도")
        publish_transcript(" ".join(part for part in (state_text, intensity_text) if part))

        update_display_state("recommending")
        recommendation = build_recommendation_from_parts(state_text, intensity_text)
        order = save_recommendation_order(recommendation)

        if order["success"]:
            confirm_message = get_message("confirm_template", combo_text=order["combo_text"])
            order["confirm_message"] = confirm_message
            publish_recommendation_result(order)
            speak(confirm_message)

            if dispatch_callback is not None:
                publish_dispatching(order)
                dispatch_callback(order)
                publish_completed(order)
        else:
            logger.warning("Recommendation flow ended without a successful order.")
            publish_error("추천 결과를 생성하지 못했습니다.")

        return order
    except Exception as exc:
        publish_error(str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Run wake word -> state STT -> intensity STT -> nut combo flow."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Use terminal input instead of wake word and microphone STT.",
    )
    args = parser.parse_args()
    configure_logging(debug=args.debug)

    if not args.debug:
        raise SystemExit("Use --debug unless you provide STT/Wakeup objects from another node.")

    order = run_recommendation_flow(debug=True, wait_for_wake=True)
    print(json.dumps(order, ensure_ascii=False, indent=2))
    print(f"Saved to {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
