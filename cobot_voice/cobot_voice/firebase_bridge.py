import logging
import os
import queue
import threading
from datetime import datetime, timezone

from cobot_voice.env import load_package_env

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

SESSION_COLLECTION = "robot_session"
SESSION_DOCUMENT = "current"

DISPLAY_STATES = {
    "idle",
    "wake_detected",
    "asking_state",
    "listening_state",
    "asking_intensity",
    "listening_intensity",
    "recommending",
    "result_ready",
    "dispatching",
    "completed",
    "error",
}

DEFAULT_THEME = {
    "primary_category": "",
    "primary_nut": "",
    "primary_color": "#031B2D",
    "secondary_color": "#0B3552",
    "accent_color": "#30C7F2",
}

ERROR_THEME = {
    "primary_category": "",
    "primary_nut": "",
    "primary_color": "#3A1010",
    "secondary_color": "#F5C7C7",
    "accent_color": "#E54848",
}

THEMES_BY_CATEGORY = {
    "fatigue": {
        "primary_category": "fatigue",
        "primary_nut": "cashew",
        "primary_color": "#F2C879",
        "secondary_color": "#FFF3D6",
        "accent_color": "#D99A36",
    },
    "blood_sugar": {
        "primary_category": "blood_sugar",
        "primary_nut": "almond",
        "primary_color": "#B9855A",
        "secondary_color": "#F3E1D0",
        "accent_color": "#7A4E2D",
    },
    "diet": {
        "primary_category": "diet",
        "primary_nut": "pistachio",
        "primary_color": "#8BC34A",
        "secondary_color": "#E8F5D2",
        "accent_color": "#4F8A10",
    },
    "focus": {
        "primary_category": "focus",
        "primary_nut": "walnut",
        "primary_color": "#6D4C41",
        "secondary_color": "#D7CCC8",
        "accent_color": "#3E2723",
    },
}

CATEGORY_BY_NUT = {
    "cashew": "fatigue",
    "almond": "blood_sugar",
    "pistachio": "diet",
    "walnut": "focus",
}

_SESSION_REF = None
_FIREBASE_UNAVAILABLE = False
_UPDATE_QUEUE = queue.Queue()
_WORKER_STARTED = False


def _iso_timestamp():
    return datetime.now(timezone.utc).isoformat()


def _get_session_ref():
    global _SESSION_REF, _FIREBASE_UNAVAILABLE
    if _SESSION_REF is not None:
        return _SESSION_REF
    if _FIREBASE_UNAVAILABLE:
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        load_package_env()
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT")

        if not firebase_admin._apps:
            if service_account_path:
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()

        db = firestore.client()
        _SESSION_REF = db.collection(SESSION_COLLECTION).document(SESSION_DOCUMENT)
        return _SESSION_REF
    except Exception as exc:
        _FIREBASE_UNAVAILABLE = True
        logger.warning("Firebase session connection failed: %s", exc)
        return None


def _blocking_update(payload):
    global _FIREBASE_UNAVAILABLE
    if _FIREBASE_UNAVAILABLE:
        return

    ref = _get_session_ref()
    if ref is None:
        return

    try:
        ref.set(payload, merge=True, timeout=2)
        logger.debug(
            "Updated Firebase /%s/%s: %s",
            SESSION_COLLECTION,
            SESSION_DOCUMENT,
            payload,
        )
    except Exception as exc:
        _FIREBASE_UNAVAILABLE = True
        logger.warning("Firebase session update failed: %s", exc)


def _worker_loop():
    while True:
        payload = _UPDATE_QUEUE.get()
        try:
            _blocking_update(payload)
        finally:
            _UPDATE_QUEUE.task_done()


def _ensure_worker_started():
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return

    thread = threading.Thread(target=_worker_loop, daemon=True)
    thread.start()
    _WORKER_STARTED = True


def _safe_update(fields):
    if _FIREBASE_UNAVAILABLE:
        return False

    payload = {
        **fields,
        "updated_at": _iso_timestamp(),
    }

    _ensure_worker_started()
    _UPDATE_QUEUE.put(payload)
    return True


def update_display_state(state, **kwargs):
    if state not in DISPLAY_STATES:
        logger.warning("Unknown display_state %r; using error.", state)
        state = "error"

    return _safe_update(
        {
            "display_state": state,
            **kwargs,
        }
    )


def reset_session():
    return _safe_update(
        {
            "display_state": "idle",
            "question": "",
            "transcript": "",
            "categories": [],
            "intensity": "normal",
            "combo": [],
            "combo_text": "",
            "confirm_message": "",
            "success": False,
            "theme": DEFAULT_THEME,
            "error": "",
        }
    )


def publish_question(question_text, state):
    return update_display_state(
        state,
        question=str(question_text or ""),
        error="",
    )


def publish_transcript(text):
    return _safe_update(
        {
            "transcript": str(text or ""),
            "error": "",
        }
    )


def publish_recommendation_result(order):
    combo = order.get("combo", []) if isinstance(order, dict) else []
    categories = order.get("categories", []) if isinstance(order, dict) else []
    combo_text = str(order.get("combo_text", "") if isinstance(order, dict) else "")
    confirm_message = str(
        order.get("confirm_message", "") if isinstance(order, dict) else ""
    )
    if not confirm_message and combo_text:
        confirm_message = f"말씀하신 상태에 맞춰 {combo_text}를 준비해드릴게요."

    return update_display_state(
        "result_ready",
        transcript=str(order.get("recognized_text", "") if isinstance(order, dict) else ""),
        categories=list(categories),
        intensity=str(order.get("intensity", "normal") if isinstance(order, dict) else "normal"),
        combo=list(combo) if isinstance(combo, list) else [],
        combo_text=combo_text,
        confirm_message=confirm_message,
        success=bool(order.get("success", False) if isinstance(order, dict) else False),
        theme=build_theme(categories, combo),
        error="",
    )


def publish_dispatching(order=None):
    fields = {
        "error": "",
    }
    if isinstance(order, dict):
        fields.update(
            {
                "transcript": str(order.get("recognized_text", "")),
                "categories": list(order.get("categories", [])),
                "intensity": str(order.get("intensity", "normal")),
                "combo": list(order.get("combo", []))
                if isinstance(order.get("combo", []), list)
                else [],
                "combo_text": str(order.get("combo_text", "")),
                "confirm_message": str(order.get("confirm_message", "")),
                "success": bool(order.get("success", False)),
                "theme": build_theme(order.get("categories", []), order.get("combo", [])),
            }
        )

    return update_display_state("dispatching", **fields)


def publish_completed(order=None):
    fields = {
        "error": "",
    }
    if isinstance(order, dict):
        fields.update(
            {
                "transcript": str(order.get("recognized_text", "")),
                "categories": list(order.get("categories", [])),
                "intensity": str(order.get("intensity", "normal")),
                "combo": list(order.get("combo", []))
                if isinstance(order.get("combo", []), list)
                else [],
                "combo_text": str(order.get("combo_text", "")),
                "confirm_message": str(order.get("confirm_message", "")),
                "success": bool(order.get("success", False)),
                "theme": build_theme(order.get("categories", []), order.get("combo", [])),
            }
        )

    return update_display_state("completed", **fields)


def publish_error(message):
    return update_display_state(
        "error",
        question="문제가 발생했습니다. 다시 시도해주세요.",
        error=str(message or "Unknown error"),
        success=False,
        theme=ERROR_THEME,
    )


def build_theme(categories, combo):
    primary_category = ""
    for category in categories or []:
        if category in THEMES_BY_CATEGORY:
            primary_category = category
            break

    if not primary_category:
        for item in combo or []:
            if not isinstance(item, dict):
                continue
            nut = item.get("nut")
            category = CATEGORY_BY_NUT.get(nut)
            if category:
                primary_category = category
                break

    if not primary_category:
        return DEFAULT_THEME

    return THEMES_BY_CATEGORY[primary_category]
