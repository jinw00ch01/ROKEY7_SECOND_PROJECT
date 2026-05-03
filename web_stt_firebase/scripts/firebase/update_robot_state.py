import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / "cobot_voice" / "resource" / ".env"


def init_firestore():
    load_dotenv(ENV_PATH)
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT")

    if not service_account_path:
        raise RuntimeError(f"FIREBASE_SERVICE_ACCOUNT is not set in {ENV_PATH}")

    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)

    return firestore.client()


def update_robot_state(
    mode: str,
    wake_word_detected: bool,
    command_text: str = "",
    parsed_action: str = "",
    targets: list[str] | None = None,
):
    db = init_firestore()
    db.collection("robot_state").document("loki").set({
        "mode": mode,
        "wakeWordDetected": wake_word_detected,
        "commandText": command_text,
        "parsedAction": parsed_action,
        "targets": targets or [],
        "updatedAt": datetime.now(timezone.utc),
    }, merge=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish a mock LOKI robot state to Firestore.")
    parser.add_argument("--mode", default="listening")
    parser.add_argument("--wake-word-detected", action="store_true")
    parser.add_argument("--command-text", default="")
    parser.add_argument("--parsed-action", default="")
    parser.add_argument("--target", action="append", default=[])
    args = parser.parse_args()

    update_robot_state(
        mode=args.mode,
        wake_word_detected=args.wake_word_detected,
        command_text=args.command_text,
        parsed_action=args.parsed_action,
        targets=args.target,
    )
