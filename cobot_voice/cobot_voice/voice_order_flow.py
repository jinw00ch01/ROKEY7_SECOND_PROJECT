# 한국어 요약:
#   wake word 감지 후 STT로 사용자 상태/강도를 듣고 LLM 또는 메뉴 매칭으로
#   추천 combo를 생성하는 음성 주문 플로우의 메인 모듈.
#   TTS는 ElevenLabs → spd-say 순서로 auto-fallback 하며, freeform/menu
#   두 가지 prompt mode를 환경변수로 전환한다. dispatch_callback 훅으로
#   실제 로봇 동작은 분리하여 테스트 가능하도록 설계.
import argparse
import json
import logging
import os
import re
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

# freeform: 자연어 그대로 LLM에 전달하여 의도 추출.
# menu: 정해진 번호/키워드만 받도록 하여 STT 오인식과 LLM 비용을 회피.
PROMPT_MODE_FREEFORM = "freeform"
PROMPT_MODE_MENU = "menu"

# Menu-mode keyword sets. Single ASCII digits ("1"-"4") are matched as
# whitespace-separated tokens to avoid false hits in numbers like "12".
# Bare Korean numerals (일/이/삼/사) are intentionally omitted because they
# overlap with common particles (e.g. "이번", "일하다"); we keep "1번"/"일번"
# style instead. Multi-char keywords match as substring.
_MENU_STATE_CHOICES = (
    ("fatigue",     ("1", "1번", "일번", "첫째", "피로", "피곤")),
    ("blood_sugar", ("2", "2번", "이번째", "둘째", "혈당", "당분")),
    ("diet",        ("3", "3번", "삼번", "셋째", "다이어트", "체중", "살빼")),
    ("focus",       ("4", "4번", "사번", "넷째", "집중", "두뇌", "공부")),
)
_MENU_INTENSITY_CHOICES = (
    ("low",    ("1", "1번", "일번", "low",    "조금", "약간", "약하", "맛만", "적게")),
    ("normal", ("2", "2번", "이번째", "normal", "보통", "적당", "그냥")),
    ("high",   ("3", "3번", "삼번", "high",   "많이", "듬뿍", "잔뜩", "왕창", "강하")),
)

_MENU_ASK_STATE = (
    "오늘 컨디션을 골라주세요. "
    "1번 피로, 2번 혈당, 3번 다이어트, 4번 집중. "
    "번호나 키워드로 답해주세요."
)
_MENU_ASK_INTENSITY = (
    "정도를 골라주세요. 1번 약하게, 2번 보통, 3번 많이. "
    "번호나 키워드로 답해주세요."
)


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
        # provider 명시 시 해당 backend만 시도. auto일 경우 ElevenLabs를 먼저
        # 시도하고 실패하면 spd-say로 자동 폴백한다.
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
    # should_continue 콜백을 통해 외부(ROS shutdown 등)에서 대기 루프를
    # 비동기적으로 중단할 수 있도록 한다.
    while should_continue is None or should_continue():
        if wakeup.is_wakeup():
            logger.info("Wake word detected.")
            return True
        time.sleep(poll_interval)
    logger.info("Wake word wait stopped before detection.")
    return False


def listen_text(stt=None, debug=False, prompt="사용자 입력"):
    # debug 모드에서는 STT 대신 터미널 input으로 대체하여 마이크 없이 테스트 가능.
    # 실제 STT는 Whisper 기반으로 5초 / 16kHz mono 녹음을 가정한다.
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


def _prompt_mode():
    load_package_env()
    value = os.getenv("COBOT_VOICE_PROMPT_MODE", PROMPT_MODE_FREEFORM).strip().lower()
    return PROMPT_MODE_MENU if value == PROMPT_MODE_MENU else PROMPT_MODE_FREEFORM


def _match_menu_choice(text, choices):
    if not text:
        return None
    sample = text.strip().lower()
    if not sample:
        return None
    # 공백/구두점으로 토큰을 분리해 단일 ASCII 숫자("1")가 "12" 같은 더 긴
    # 숫자에 부분 매칭되는 것을 방지한다.
    tokens = {t for t in re.split(r"[\s,.\?!　]+", sample) if t}
    for canonical, keywords in choices:
        for kw in keywords:
            if not kw:
                continue
            # 한 글자 ASCII 키워드(예: "1")는 토큰 단위로만 정확히 일치 검사.
            # 그 외 다중 문자 키워드는 일반 substring 검색으로 처리.
            if len(kw) == 1 and kw.isascii():
                if kw in tokens:
                    return canonical
            elif kw in sample:
                return canonical
    return None


def _resolve_state(text, openai_api_key, mode):
    if mode == PROMPT_MODE_MENU:
        canonical = _match_menu_choice(text, _MENU_STATE_CHOICES)
        if canonical:
            return {"category": canonical, "reasoning_message": ""}
    return StateAnalyzer(openai_api_key).analyze(text)


def _resolve_intensity(text, openai_api_key, mode):
    if mode == PROMPT_MODE_MENU:
        canonical = _match_menu_choice(text, _MENU_INTENSITY_CHOICES)
        if canonical:
            return {"intensity": canonical, "reasoning_message": ""}
    return IntensityAnalyzer(openai_api_key).analyze(text)


def run_recommendation_flow(
    stt=None,
    wakeup=None,
    mic=None,
    debug=False,
    wait_for_wake=True,
    dispatch_callback=None,
    should_continue=None,
):
    # dispatch_callback: 추천 결과를 실제 로봇 동작(pick & place 등)으로 보내는
    #   훅. None이면 추천만 수행하고 종료하므로 단위 테스트에서 로봇 동작 분리 가능.
    # should_continue: 외부 stop 신호(ROS shutdown 등) 폴링용 콜백.
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

        mode = _prompt_mode()
        ask_state = _MENU_ASK_STATE if mode == PROMPT_MODE_MENU else get_message("ask_state")
        publish_question(ask_state, "asking_state")
        speak(ask_state)
        update_display_state("listening_state")
        state_text = listen_text(stt=stt, debug=debug, prompt="상태")
        publish_transcript(state_text)


        load_package_env()
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.warning("OPENAI_API_KEY is missing. AI analysis might fail.")

        state_result = _resolve_state(state_text, openai_api_key, mode)

        # Menu mode에서는 LLM을 거치지 않으므로 매칭 실패 시 한 번 재시도하여
        # 사용자에게 다시 번호/키워드를 입력받는다.
        # Menu mode: validate the parse, retry once on miss before bailing.
        if mode == PROMPT_MODE_MENU and not state_result.get("category"):
            retry_prompt = get_message("retry_state")
            publish_question(retry_prompt, "asking_state")
            speak(retry_prompt)
            update_display_state("listening_state")
            retry_text = listen_text(stt=stt, debug=debug, prompt="상태")
            publish_transcript(" ".join(p for p in (state_text, retry_text) if p))
            state_text = " ".join(p for p in (state_text, retry_text) if p).strip()
            state_result = _resolve_state(retry_text, openai_api_key, mode)

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

        update_display_state(
            "asking_intensity",
            categories=categories,
            theme=build_theme(categories, []),
        )
        # UI에는 핵심 질문만 표시 (예: "얼마나 드릴까요?")
        # TTS로는 AI의 판단 근거를 포함하여 상세히 설명 (freeform mode).
        # Menu mode skips the LLM-reasoning prefix and asks the explicit menu.
        if mode == PROMPT_MODE_MENU:
            simple_prompt = _MENU_ASK_INTENSITY
            combined_tts_message = simple_prompt
        else:
            simple_prompt = get_message("ask_intensity")
            combined_tts_message = reasoning_message + " " + simple_prompt

        publish_question(simple_prompt, "asking_intensity")
        speak(combined_tts_message)

        update_display_state("listening_intensity")
        intensity_text = listen_text(stt=stt, debug=debug, prompt="강도")
        publish_transcript(" ".join(part for part in (state_text, intensity_text) if part))

        intensity_result = _resolve_intensity(intensity_text, openai_api_key, mode)

        # Menu mode: validate intensity parse, retry once on miss.
        if mode == PROMPT_MODE_MENU and not intensity_result.get("intensity"):
            retry_prompt = get_message("retry_intensity")
            publish_question(retry_prompt, "asking_intensity")
            speak(retry_prompt)
            update_display_state("listening_intensity")
            retry_text = listen_text(stt=stt, debug=debug, prompt="강도")
            publish_transcript(
                " ".join(p for p in (state_text, intensity_text, retry_text) if p)
            )
            intensity_text = " ".join(p for p in (intensity_text, retry_text) if p).strip()
            intensity_result = _resolve_intensity(retry_text, openai_api_key, mode)

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
            # 최종 확인 단계도 마찬가지로 UI는 깔끔하게, 목소리는 상세하게
            simple_confirm = get_message('confirm_template', combo_text=order['combo_text'])
            combined_confirm_tts = intensity_reasoning + " " + simple_confirm
            
            order["confirm_message"] = simple_confirm # 화면에는 간결하게
            publish_recommendation_result(order)
            speak(combined_confirm_tts)

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
