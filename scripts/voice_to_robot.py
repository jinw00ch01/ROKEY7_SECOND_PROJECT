#!/usr/bin/env python3
"""End-to-end: voice/text -> recommendation -> robot pickup.

Wires cobot_voice's recommendation flow into cobot_task_manager via the
`/task/start` service. Saves latest_order.json then triggers the task
manager to consume it.

Modes:
    voice_to_robot.py --text "피곤하고 집중이 안 돼요 많이"   # text bypass
    voice_to_robot.py --debug                                 # terminal input
    voice_to_robot.py                                         # mic + wake word

Pre-conditions:
    - cobot_task_manager launched with order_source=file and
      file_order_path pointing at cobot_voice/output/latest_order.json.
    - task_autostart can be either true (worker idle then triggered) or
      false (we trigger via /task/start). Either works.
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voice/text -> nut combo -> robot pickup."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--text",
        help="Bypass STT/wake-word; extract keywords from this text directly.",
    )
    mode.add_argument(
        "--debug",
        action="store_true",
        help="Use terminal input instead of microphone (no STT/wake word).",
    )
    parser.add_argument(
        "--no-dispatch",
        action="store_true",
        help="Skip the /task/start trigger (saves latest_order.json only).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from cobot_voice.env import load_package_env
    load_package_env()

    from cobot_voice.task_manager_dispatcher import dispatch_to_task_manager

    callback = None if args.no_dispatch else dispatch_to_task_manager

    if args.text:
        from cobot_voice.keyword_extractor import save_latest_order
        order = save_latest_order(args.text)
        print(f"\nrecognized_text : {order.get('recognized_text', '')!r}")
        print(f"combo           : {order.get('combo', [])}")
        print(f"success         : {order.get('success', False)}")
        if callback is not None:
            ok = callback(order)
            print(f"dispatched      : {ok}")
        return 0

    if args.debug:
        from cobot_voice.voice_order_flow import run_recommendation_flow
        order = run_recommendation_flow(
            debug=True, wait_for_wake=True, dispatch_callback=callback,
        )
        return 0 if order and order.get("success") else 1

    # Microphone + wake word mode
    from cobot_voice.voice_web_demo import VoiceWebDemo
    demo = VoiceWebDemo(enable_audio=True)
    # Override the demo's default callback (a 10s wait stub) with the real
    # task_manager dispatcher.
    if callback is not None:
        # voice_web_demo.run_once builds the call internally; reach in.
        from cobot_voice.voice_order_flow import run_recommendation_flow
        order = run_recommendation_flow(
            stt=demo.stt,
            wakeup=demo.wakeup,
            mic=demo.mic,
            debug=False,
            wait_for_wake=True,
            dispatch_callback=callback,
        )
        try:
            demo.mic.close_stream()
        except Exception:  # noqa: BLE001
            pass
        return 0 if order and order.get("success") else 1
    else:
        demo.run_once()
        return 0


if __name__ == "__main__":
    sys.exit(main())
