import argparse
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from cobot_voice.keyword_extractor import DEFAULT_OUTPUT_PATH, save_recommendation_order, StateAnalyzer, IntensityAnalyzer
from cobot_voice.env import load_package_env
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
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_ADAM_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
ELEVENLABS_DEFAULT_MODEL_ID = "eleven_flash_v2_5"
ELEVENLABS_DEFAULT_LANGUAGE_CODE = "ko"
ELEVENLABS_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
TTS_TIMEOUT_SECONDS = 20
TTS_DISABLED_VALUES = {"0", "false", "no", "off"}
ELEVENLABS_PROVIDER_VALUES = {"elevenlabs", "eleven_labs", "eleven"}
SPD_PROVIDER_VALUES = {"spd", "spd-say", "spdsay"}


def configure_logging(debug=False):
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s: %(message)s",
    )


def _tts_enabled():
    load_package_env()
    value = os.getenv("COBOT_TTS_ENABLED", "1").strip().lower()
    return value not in TTS_DISABLED_VALUES


def _tts_provider():
    load_package_env()
    return os.getenv("COBOT_TTS_PROVIDER", "auto").strip().lower()


def _get_elevenlabs_api_key():
    load_package_env()
    return os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_LABS_API_KEY")


def _parse_float_env(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        return float(value)
    except ValueError:
        logger.warning("Ignoring invalid %s value: %s", name, value)
        return default


def _parse_bool_env(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    return value.strip().lower() not in TTS_DISABLED_VALUES


def _build_elevenlabs_payload(text):
    payload = {
        "text": text,
        "model_id": os.getenv("ELEVENLABS_MODEL_ID", ELEVENLABS_DEFAULT_MODEL_ID),
        "language_code": os.getenv(
            "ELEVENLABS_LANGUAGE_CODE",
            ELEVENLABS_DEFAULT_LANGUAGE_CODE,
        ),
        "voice_settings": {
            "stability": _parse_float_env("ELEVENLABS_STABILITY", 0.5),
            "similarity_boost": _parse_float_env(
                "ELEVENLABS_SIMILARITY_BOOST",
                0.75,
            ),
            "style": _parse_float_env("ELEVENLABS_STYLE", 0.0),
            "use_speaker_boost": _parse_bool_env(
                "ELEVENLABS_USE_SPEAKER_BOOST",
                True,
            ),
        },
    }

    return payload


def _play_audio_file(path):
    command = shutil.which("ffplay")
    if command is None:
        logger.warning("TTS audio generated but ffplay is not installed.")
        return False

    subprocess.run(
        [
            command,
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "error",
            path,
        ],
        check=True,
        timeout=TTS_TIMEOUT_SECONDS,
    )
    return True


def _run_elevenlabs(text):
    api_key = _get_elevenlabs_api_key()
    if not api_key:
        return False

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", ELEVENLABS_ADAM_VOICE_ID)
    output_format = os.getenv(
        "ELEVENLABS_OUTPUT_FORMAT",
        ELEVENLABS_DEFAULT_OUTPUT_FORMAT,
    )
    url = ELEVENLABS_TTS_URL.format(voice_id=urllib.parse.quote(voice_id))
    url = f"{url}?{urllib.parse.urlencode({'output_format': output_format})}"
    body = json.dumps(_build_elevenlabs_payload(text)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )

    audio_path = ""
    try:
        with urllib.request.urlopen(request, timeout=TTS_TIMEOUT_SECONDS) as response:
            audio_data = response.read()

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp3",
            prefix="cobot_elevenlabs_",
        ) as audio_file:
            audio_file.write(audio_data)
            audio_path = audio_file.name

        return _play_audio_file(audio_path)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.warning("ElevenLabs TTS request failed: %s %s", exc.code, error_body)
        return False
    except Exception as exc:
        logger.warning("ElevenLabs TTS failed: %s", exc)
        return False
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except OSError:
                pass


def _run_spd_say(text):
    command = shutil.which("spd-say")
    if command is None:
        return False

    subprocess.run(
        [
            command,
            "--wait",
            "--language",
            "ko",
            "--rate",
            "-10",
            text,
        ],
        check=True,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        timeout=TTS_TIMEOUT_SECONDS,
    )
    return True


def speak(text):
    clean_text = str(text or "").strip()
    if not clean_text:
        return

    print(f"[TTS] {clean_text}")
    if not _tts_enabled():
        return

    try:
        provider = _tts_provider()
        if provider in ELEVENLABS_PROVIDER_VALUES:
            if not _get_elevenlabs_api_key():
                logger.warning(
                    "COBOT_TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is not set."
                )
                return
            if not _run_elevenlabs(clean_text):
                logger.warning("ElevenLabs TTS requested but playback failed.")
            return

        if provider in SPD_PROVIDER_VALUES:
            if not _run_spd_say(clean_text):
                logger.warning("TTS skipped because spd-say is not installed.")
            return

        if _get_elevenlabs_api_key() and _run_elevenlabs(clean_text):
            return
        if not _run_spd_say(clean_text):
            logger.warning("TTS skipped because spd-say is not installed.")
    except Exception as exc:
        logger.warning("TTS playback failed; continuing without narration: %s", exc)


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


        load_package_env()
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.warning("OPENAI_API_KEY is missing. AI analysis might fail.")

        state_analyzer = StateAnalyzer(openai_api_key)
        state_result = state_analyzer.analyze(state_text)
        
        category = state_result.get("category", "")
        categories = [category] if category else []
        reasoning_message = state_result.get("reasoning_message", "상태를 파악하기 어렵네요.")

        if not categories:
            logger.info("AI could not determine category; saving unsuccessful order.")
            recommendation = {
                "recognized_text": state_text,
                "categories": [],
                "intensity": "normal",
                "combo": [],
                "combo_text": "",
            }
            order = save_recommendation_order(recommendation)
            publish_error("상태 카테고리를 찾지 못했습니다.")
            speak(reasoning_message)
            return order

        ask_intensity = get_message("ask_intensity")
        combined_message = f"{reasoning_message} {ask_intensity}"
        
        update_display_state(
            "asking_intensity",
            categories=categories,
            theme=build_theme(categories, []),
        )
        publish_question(combined_message, "asking_intensity")
        speak(combined_message)
        
        update_display_state("listening_intensity")
        intensity_text = listen_text(stt=stt, debug=debug, prompt="강도")
        publish_transcript(" ".join(part for part in (state_text, intensity_text) if part))

        intensity_analyzer = IntensityAnalyzer(openai_api_key)
        intensity_result = intensity_analyzer.analyze(intensity_text)
        
        intensity = intensity_result.get("intensity", "normal")
        intensity_reasoning = intensity_result.get("reasoning_message", "적당량으로 준비해 드릴게요.")

        update_display_state("recommending")
        
        config_dir = _get_config_dir()
        categories_config = load_json(config_dir / "keyword_categories.json")
        combo_rules = load_json(config_dir / "nut_combo_rules.json")
        combo = build_combo(categories, intensity, combo_rules, categories_config)

        recommendation = {
            "recognized_text": " ".join(part for part in (state_text, intensity_text) if part),
            "categories": categories,
            "intensity": intensity,
            "combo": combo,
            "combo_text": format_combo_text(combo),
        }
        order = save_recommendation_order(recommendation)

        if order["success"]:
            confirm_message = f"{intensity_reasoning} {get_message('confirm_template', combo_text=order['combo_text'])}"
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
