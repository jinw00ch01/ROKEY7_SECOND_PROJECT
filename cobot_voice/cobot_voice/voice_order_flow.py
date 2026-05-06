import argparse
import json
import logging
import time

from cobot_voice.keyword_extractor import DEFAULT_OUTPUT_PATH, save_recommendation_order
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


def wait_for_wake_word(wakeup, poll_interval=0.05):
    logger.info("Waiting for wake word.")
    while not wakeup.is_wakeup():
        time.sleep(poll_interval)
    logger.info("Wake word detected.")
    return True


def listen_text(stt=None, debug=False, prompt="사용자 입력"):
    if debug:
        return input(f"{prompt}> ").strip()
    if stt is None:
        raise ValueError("stt is required when debug=False")
    return stt.speech2text()


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


def run_recommendation_flow(stt=None, wakeup=None, debug=False, wait_for_wake=True):
    logger.debug("Starting recommendation flow. debug=%s wait_for_wake=%s", debug, wait_for_wake)
    if wait_for_wake:
        if debug:
            input("Wake word debug mode: Enter를 누르면 wake word 감지로 처리합니다.")
        else:
            if wakeup is None:
                raise ValueError("wakeup is required when wait_for_wake=True and debug=False")
            wait_for_wake_word(wakeup)

    speak(get_message("wake_response"))
    speak(get_message("ask_state"))
    state_text = listen_text(stt=stt, debug=debug, prompt="상태")

    config_dir = _get_config_dir()
    categories_config = load_json(config_dir / "keyword_categories.json")
    categories = extract_categories(state_text, categories_config)

    if not categories:
        logger.info("No category found on first attempt; asking retry_state.")
        speak(get_message("retry_state"))
        state_text = listen_text(stt=stt, debug=debug, prompt="상태 재입력")
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
        return order

    speak(get_message("ask_intensity"))
    intensity_text = listen_text(stt=stt, debug=debug, prompt="강도")

    recommendation = build_recommendation_from_parts(state_text, intensity_text)
    order = save_recommendation_order(recommendation)

    if order["success"]:
        speak(get_message("confirm_template", combo_text=order["combo_text"]))
    else:
        logger.warning("Recommendation flow ended without a successful order.")

    return order


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
