import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

cred = credentials.Certificate("path/to/serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

def update_robot_state(mode: str, wake_word_detected: bool, command_text: str = ""):
    db.collection("robot_state").document("loki").set({
        "mode": mode,
        "wakeWordDetected": wake_word_detected,
        "commandText": command_text,
        "updatedAt": datetime.now(timezone.utc),
    }, merge=True)

if __name__ == "__main__":
    update_robot_state("listening", True, "")
