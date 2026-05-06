import argparse
import os
import time


ROBOT_MOTION_SECONDS = 10.0
COMPLETED_SESSION_SECONDS = 3.0
MODE_TO_DISPLAY_STATE = {
    "idle": "idle",
    "wake_detected": "wake_detected",
    "listening": "listening_state",
    "transcribing": "listening_state",
    "processing": "recommending",
    "speaking": "asking_state",
    "error": "error",
}


def _get_package_path():
    try:
        from ament_index_python.packages import get_package_share_directory

        return get_package_share_directory("cobot_voice")
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VoiceWebDemo:
    """Runs wake word, STT, and keyword extraction without ROS topics."""

    def __init__(self, enable_audio: bool = False):
        from dotenv import load_dotenv
        from cobot_voice.keyword_extractor import KeywordExtractor

        package_path = _get_package_path()
        load_dotenv(dotenv_path=os.path.join(package_path, "resource", ".env"))

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in cobot_voice/resource/.env")

        self.extractor = KeywordExtractor(openai_api_key=openai_api_key)
        self.stt = None
        self.mic = None
        self.wakeup = None
        if enable_audio:
            self._init_audio(openai_api_key)
        self._running = False

    def _init_audio(self, openai_api_key: str):
        from cobot_voice.mic_controller import MicController
        from cobot_voice.stt import STT
        from cobot_voice.wakeup_word import WakeupWord

        self.stt = STT(openai_api_key=openai_api_key)
        self.mic = MicController()
        self.wakeup = WakeupWord(buffer_size=self.mic.config.buffer_size)

    def set_state(self, **fields):
        from cobot_voice.firebase_bridge import publish_transcript, update_display_state

        mode = str(fields.get("mode", "idle") or "idle")
        display_state = MODE_TO_DISPLAY_STATE.get(mode)
        command_text = str(fields.get("commandText", "") or "").strip()

        if command_text:
            publish_transcript(command_text)
        if display_state is not None:
            update_display_state(display_state)

    def stop(self):
        self._running = False

    def wait_for_robot_motion(self, order):
        del order
        deadline = time.monotonic() + ROBOT_MOTION_SECONDS
        while self._running and time.monotonic() < deadline:
            time.sleep(0.1)

    def wait_for_completed_session(self):
        deadline = time.monotonic() + COMPLETED_SESSION_SECONDS
        while self._running and time.monotonic() < deadline:
            time.sleep(0.1)

    def process_text(self, text: str):
        from cobot_voice.firebase_bridge import (
            publish_completed,
            publish_dispatching,
            publish_recommendation_result,
            reset_session,
            update_display_state,
        )
        from cobot_voice.keyword_extractor import save_latest_order

        clean_text = text.strip()
        reset_session()
        update_display_state("recommending", transcript=clean_text)

        order = save_latest_order(clean_text)
        if order["success"]:
            publish_recommendation_result(order)
        else:
            from cobot_voice.firebase_bridge import publish_error

            publish_error("추천 결과를 생성하지 못했습니다.")

        action, targets = self.extractor.extract(clean_text)
        if action == "sort" and targets:
            publish_dispatching(order)
            time.sleep(ROBOT_MOTION_SECONDS)
            publish_completed(order)
        print(f"Parsed action={action}, targets={targets}")
        return action, targets

    def run_once(self):
        from cobot_voice.voice_order_flow import run_recommendation_flow

        if self.stt is None or self.mic is None or self.wakeup is None:
            raise RuntimeError("Audio components were not initialized")

        self._running = True
        try:
            order = run_recommendation_flow(
                stt=self.stt,
                wakeup=self.wakeup,
                mic=self.mic,
                debug=False,
                wait_for_wake=True,
                dispatch_callback=self.wait_for_robot_motion,
                should_continue=lambda: self._running,
            )
            if order and order.get("success"):
                self.wait_for_completed_session()
            return order
        finally:
            self._running = False
            self.mic.close_stream()


def main():
    parser = argparse.ArgumentParser(
        description="Run website-connected wake word, STT, and keyword extraction without ROS."
    )
    parser.add_argument(
        "--text",
        help="Bypass microphone/wake word and extract keywords from this text.",
    )
    args = parser.parse_args()

    demo = VoiceWebDemo(enable_audio=args.text is None)
    if args.text:
        demo.process_text(args.text)
    else:
        demo.run_once()


if __name__ == "__main__":
    main()
