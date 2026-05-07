import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / "cobot_voice" / "resource" / ".env"
SESSION_COLLECTION = "robot_session"
SESSION_DOCUMENT = "current"
MODE_TO_DISPLAY_STATE = {
    "idle": "idle",
    "wake_detected": "wake_detected",
    "listening": "listening_state",
    "transcribing": "listening_state",
    "processing": "recommending",
    "speaking": "asking_state",
    "error": "error",
}


def init_firestore():
    load_dotenv(ENV_PATH)
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT")

    if not firebase_admin._apps:
        if service_account_path:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()

    return firestore.client()


def update_robot_session(
    display_state: str,
    transcript: str = "",
    combo_text: str = "",
    error: str = "",
):
    db = init_firestore()
    payload = {
        "display_state": display_state,
        "transcript": transcript,
        "combo_text": combo_text,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.collection(SESSION_COLLECTION).document(SESSION_DOCUMENT).set(
        payload,
        merge=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Publish a mock LOKI robot session to Firestore."
    )
    parser.add_argument("--display-state", default="")
    parser.add_argument("--mode", default="", help="Deprecated alias for legacy tests.")
    parser.add_argument("--transcript", default="")
    parser.add_argument("--combo-text", default="")
    parser.add_argument("--error", default="")
    args = parser.parse_args()

    display_state = args.display_state or MODE_TO_DISPLAY_STATE.get(args.mode, "idle")
    update_robot_session(
        display_state=display_state,
        transcript=args.transcript,
        combo_text=args.combo_text,
        error=args.error,
    )
