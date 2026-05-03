import argparse
import os
from datetime import datetime, timezone


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

    def process_text(self, text: str):
        clean_text = text.strip()
        self._update_state(
            mode="processing",
            wakeWordDetected=True,
            commandText=clean_text,
            parsedAction="",
            targets=[],
        )

        action, targets = self.extractor.extract(clean_text)
        self._update_state(
            mode="idle",
            wakeWordDetected=False,
            commandText=clean_text,
            parsedAction=action,
            targets=targets,
        )
        print(f"Parsed action={action}, targets={targets}")
        return action, targets

    def run_once(self):
        if self.stt is None or self.mic is None or self.wakeup is None:
            raise RuntimeError("Audio components were not initialized")

        self._running = True
        self._update_state(
            mode="idle",
            wakeWordDetected=False,
            commandText="",
            parsedAction="",
            targets=[],
        )

        self.mic.open_stream()
        self.wakeup.set_stream(self.mic.stream)
        print("Listening for wake word: hello rokey")

        try:
            while self._running:
                if self.wakeup.is_wakeup():
                    print("Wake word detected. Recording command...")
                    self._update_state(mode="wake_detected", wakeWordDetected=True)
                    self.mic.close_stream()

                    self._update_state(mode="listening", wakeWordDetected=True)
                    text = self.stt.speech2text(
                        status_callback=lambda mode: self._update_state(
                            mode=mode,
                            wakeWordDetected=True,
                        )
                    )
                    self.process_text(text)
                    break
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
