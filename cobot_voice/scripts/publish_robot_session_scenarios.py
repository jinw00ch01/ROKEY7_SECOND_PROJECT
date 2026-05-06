import argparse
import logging
import time
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from cobot_voice.firebase_bridge import (  # noqa: E402
    publish_completed,
    publish_dispatching,
    publish_error,
    publish_question,
    publish_recommendation_result,
    reset_session,
    update_display_state,
)


RESULT_ORDER = {
    "request_id": "manual_firebase_test",
    "recognized_text": "너무 피곤하고 집중이 안 돼요 많이",
    "categories": ["fatigue", "focus"],
    "intensity": "high",
    "combo": [
        {"nut": "cashew", "count": 3},
        {"nut": "walnut", "count": 3},
    ],
    "combo_text": "캐슈넛 세 개와 호두 세 개",
    "confirm_message": "말씀하신 상태에 맞춰 캐슈넛 세 개와 호두 세 개를 준비해드릴게요.",
    "success": True,
}


def publish_step(name, callback, delay):
    print(f"[publish] {name}")
    callback()
    time.sleep(delay)


def run_scenarios(delay):
    publish_step("idle", reset_session, delay)
    publish_step(
        "wake_detected",
        lambda: publish_question(
            "네, 맞춤 견과류 콤보를 준비해드릴게요.",
            "wake_detected",
        ),
        delay,
    )
    publish_step(
        "asking_state",
        lambda: publish_question(
            "오늘 컨디션은 어떤가요?",
            "asking_state",
        ),
        delay,
    )
    publish_step("listening_state", lambda: update_display_state("listening_state"), delay)
    publish_step("recommending", lambda: update_display_state("recommending"), delay)
    publish_step(
        "result_ready",
        lambda: publish_recommendation_result(RESULT_ORDER),
        delay,
    )
    publish_step("dispatching", lambda: publish_dispatching(RESULT_ORDER), delay)
    publish_step("completed", lambda: publish_completed(RESULT_ORDER), delay)
    publish_step("error", lambda: publish_error("수동 테스트 에러 화면입니다."), delay)


def main():
    parser = argparse.ArgumentParser(
        description="Publish /robot_session/current states for web integration testing."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between Firebase session updates.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show Firebase bridge debug logs.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="[%(levelname)s] %(name)s: %(message)s",
    )
    run_scenarios(args.delay)
    print("Robot session Firebase scenario publish finished.")


if __name__ == "__main__":
    main()
