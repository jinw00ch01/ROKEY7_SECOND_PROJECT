import argparse
import os
import time
from datetime import datetime, timezone


ROBOT_MOTION_SECONDS = 5.0


class VoiceWebDemo:
    """Runs wake word, STT, and keyword extraction without ROS topics."""

    def __init__(self, enable_audio: bool = False):
        from ament_index_python.packages import get_package_share_directory
        from dotenv import load_dotenv
        from cobot_voice.keyword_extractor import KeywordExtractor

        package_path = get_package_share_directory("cobot_voice")
        load_dotenv(dotenv_path=os.path.join(package_path, "resource", ".env"))

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in cobot_voice/resource/.env")

        self.db = self._init_firestore()
        self.doc_ref = self.db.collection("robot_state").document("loki")
        self.extractor = KeywordExtractor(openai_api_key=openai_api_key)
        self.stt = None
        self.mic = None
        self.wakeup = None
        if enable_audio:
            self._init_audio(openai_api_key)
        self._running = False

    def _init_firestore(self):
        import firebase_admin
        from firebase_admin import credentials, firestore

        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if not service_account_path:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT is not set in cobot_voice/resource/.env")

        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)

        return firestore.client()

    def _init_audio(self, openai_api_key: str):
        from cobot_voice.mic_controller import MicController
        from cobot_voice.stt import STT
        from cobot_voice.wakeup_word import WakeupWord

        self.stt = STT(openai_api_key=openai_api_key)
        self.mic = MicController()
        self.wakeup = WakeupWord(buffer_size=self.mic.config.buffer_size)

    def _update_state(self, **fields):
        self.doc_ref.set(
            {
                **fields,
                "updatedAt": datetime.now(timezone.utc),
            },
            merge=True,
        )

    def set_state(self, **fields):
        self._update_state(**fields)

    def stop(self):
        self._running = False

    def process_text(self, text: str):
        from cobot_voice.firebase_bridge import publish_recommendation_result, reset_session
        from cobot_voice.keyword_extractor import save_latest_order

        clean_text = text.strip()
        reset_session()
        self._update_state(
            mode="processing",
            wakeWordDetected=True,
            commandText=clean_text,
            parsedAction="",
            targets=[],
        )

        order = save_latest_order(clean_text)
        if order["success"]:
            publish_recommendation_result(order)
        else:
            from cobot_voice.firebase_bridge import publish_error

            publish_error("추천 결과를 생성하지 못했습니다.")

        action, targets = self.extractor.extract(clean_text)
        self._update_state(
            mode="processing" if action == "sort" and targets else "idle",
            wakeWordDetected=False,
            commandText=clean_text,
            parsedAction=action,
            targets=targets,
        )
        if action == "sort" and targets:
            time.sleep(ROBOT_MOTION_SECONDS)
            self._update_state(
                mode="idle",
                wakeWordDetected=False,
                commandText=clean_text,
                parsedAction=action,
                targets=[],
            )
        print(f"Parsed action={action}, targets={targets}")
        return action, targets

    def run_once(self):
        from cobot_voice.voice_order_flow import run_recommendation_flow

        if self.stt is None or self.mic is None or self.wakeup is None:
            raise RuntimeError("Audio components were not initialized")

        self._running = True
        try:
            return run_recommendation_flow(
                stt=self.stt,
                wakeup=self.wakeup,
                mic=self.mic,
                debug=False,
                wait_for_wake=True,
                should_continue=lambda: self._running,
            )
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
