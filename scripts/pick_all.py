#!/usr/bin/env python3
"""Detect-and-pick nuts in the workspace, one at a time, with per-class quotas.

Usage:
    pick_all.py                              # pick all detected (no cap)
    pick_all.py --per-class 2                # pick 2 of EACH class (8 total)
    pick_all.py --counts cashew=2,almond=1   # pick exactly that many per class
    pick_all.py --per-class 2 --counts walnut=0   # 2 of each except 0 walnut
    pick_all.py --z-override 315             # apply same z to every pick
    pick_all.py --order cashew,almond,...    # restrict / prioritize classes
    pick_all.py --max-failures 3             # stop after N consecutive failures
    pick_all.py --inter-pick-delay 0.5       # seconds to wait between rounds
    pick_all.py --order-file /path/to/latest_order.json
                                             # read combo from cobot_voice output;
                                             # overrides --counts / --per-class

Selection is round-robin: the eligible class with the fewest picks so far
wins (ties broken by --order). This gives balanced picking even when stops
happen partway through.

Each round:
  1. /perception/detect_once
  2. select target (round-robin among eligible classes, highest conf within)
  3. /robot/pick_and_place via cobot_msgs/action/PickAndPlace
  4. on success or recoverable failure, repeat
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

import rclpy
from geometry_msgs.msg import Point
from rclpy.action import ActionClient

from cobot_msgs.action import PickAndPlace
from cobot_msgs.srv import DetectOnce


CLASSES = ("cashew", "almond", "pistachio", "walnut")
DEFAULT_RETURN_XYZ = (367.0, -150.0, 90.0)
DEFAULT_RETURN_ZYZ = (168.0, 179.0, 168.0)
DEFAULT_PRE_GRASP_MARGIN_MM = 15.0

# Per-class fine-tune offset added to grasp z (mm). Negative = grip deeper
# (good for nuts that slip). Positive = grip shallower (good if pressing
# into table). Applied on top of perception z and --z-override.
PER_CLASS_Z_OFFSET = {
    "cashew": 0.0,
    "almond": 0.0,
    "pistachio": 0.0,
    "walnut": -1.0,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect and pick nuts in sequence.")
    p.add_argument("--z-override", type=float, default=None,
                   help="Override grasp z (mm) for every pick")
    p.add_argument("--pre-grasp-width", type=float, default=None,
                   help="Override pre-grasp width (mm); default short_axis + 15")
    p.add_argument("--per-class", type=int, default=None,
                   help="Pick N of each class. Combined with --order. "
                        "If omitted and --counts also omitted, no per-class cap.")
    p.add_argument("--counts", default="",
                   help="Per-class targets, e.g. 'cashew=2,almond=1'. "
                        "Overrides --per-class for listed classes; classes "
                        "not in --counts and not in --per-class default to 0.")
    p.add_argument("--max-picks", type=int, default=12,
                   help="Safety cap on total picks (default 12)")
    p.add_argument("--max-failures", type=int, default=3,
                   help="Stop after this many consecutive failures (default 3)")
    p.add_argument("--inter-pick-delay", type=float, default=0.5,
                   help="Seconds between picks (default 0.5)")
    p.add_argument("--order", default=",".join(CLASSES),
                   help=f"Comma-separated class priority. Default: {','.join(CLASSES)}")
    p.add_argument("--detect-timeout", type=float, default=5.0)
    p.add_argument("--action-timeout", type=float, default=120.0)
    p.add_argument("--order-file", default=None,
                   help="Path to latest_order.json from cobot_voice. "
                        "When given, derives counts from JSON 'combo' field. "
                        "Refuses if success=false or combo empty. "
                        "Overrides --counts and --per-class.")
    return p.parse_args()


def parse_counts(counts_str: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for piece in counts_str.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "=" not in piece:
            raise ValueError(f"--counts entry {piece!r} missing '='")
        cls, val = piece.split("=", 1)
        cls = cls.strip()
        try:
            n = int(val.strip())
        except ValueError as exc:
            raise ValueError(f"--counts entry {piece!r}: bad integer") from exc
        if n < 0:
            raise ValueError(f"--counts entry {piece!r}: negative count")
        if cls not in CLASSES:
            raise ValueError(f"--counts entry {piece!r}: unknown class")
        out[cls] = n
    return out


def parse_order_file(file_path: str) -> tuple[dict[str, int], dict]:
    """Read a cobot_voice latest_order.json and extract per-class counts.

    Returns (counts, metadata). Raises ValueError on any validation failure
    so the caller can refuse to dispatch the robot.

    Expected JSON shape (from cobot_voice/keyword_extractor.py):
        {
          "request_id": "...",
          "recognized_text": "...",
          "combo": [{"nut": "cashew", "count": 3}, ...],
          "success": true,
          ...
        }
    """
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise ValueError(f"order file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"order file is not valid JSON: {exc}") from exc

    if not data.get("success", False):
        raise ValueError(
            "order success=false "
            f"(text: {data.get('recognized_text', '')!r})"
        )

    combo = data.get("combo")
    if not isinstance(combo, list) or not combo:
        raise ValueError("order has empty or missing 'combo'")

    counts: dict[str, int] = {}
    for item in combo:
        if not isinstance(item, dict):
            continue
        nut = item.get("nut")
        try:
            n = int(item.get("count", 0))
        except (TypeError, ValueError):
            continue
        if nut not in CLASSES or n <= 0:
            continue
        counts[nut] = counts.get(nut, 0) + n

    if not counts:
        raise ValueError(f"order combo has no valid items: {combo!r}")

    metadata = {
        "request_id": str(data.get("request_id", "")),
        "recognized_text": str(data.get("recognized_text", "")),
        "intensity": str(data.get("intensity", "")),
    }
    return counts, metadata


def build_target_counts(
    order: list[str],
    per_class: Optional[int],
    explicit_counts: dict[str, int],
) -> dict[str, int]:
    """Compose the final target count per class.

    Rule:
      - explicit --counts always wins for listed classes
      - --per-class fills in for classes in --order that --counts didn't set
      - classes neither in --order nor --counts get 0
      - if both --per-class and --counts are absent, every class in --order
        gets infinity (unlimited; preserves the original "pick all detected"
        behavior)
    """
    targets: dict[str, int] = {c: 0 for c in CLASSES}
    if per_class is None and not explicit_counts:
        for c in order:
            targets[c] = 10**9  # effectively unlimited
    else:
        if per_class is not None:
            for c in order:
                targets[c] = int(per_class)
        for c, n in explicit_counts.items():
            targets[c] = int(n)
    return targets


def call_detect(node, timeout):
    cli = node.create_client(DetectOnce, "/perception/detect_once")
    if not cli.wait_for_service(timeout_sec=timeout):
        raise RuntimeError("/perception/detect_once not available")
    fut = cli.call_async(DetectOnce.Request())
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    if not fut.done():
        raise RuntimeError("detect_once timed out")
    return fut.result()


def select_target(
    detection,
    order: list[str],
    picked: dict[str, int],
    targets: dict[str, int],
):
    """Round-robin pick: among classes that still need more picks AND have
    available detections, choose the one with the fewest picks so far. Ties
    broken by `order`. Within the chosen class, pick the highest-confidence
    detection.
    """
    eligible = [c for c in order if picked.get(c, 0) < targets.get(c, 0)]

    matches_by_class: dict[str, list] = {}
    for obj in detection.objects.objects:
        if not obj.transform_valid:
            continue
        if obj.class_name not in eligible:
            continue
        matches_by_class.setdefault(obj.class_name, []).append(obj)

    classes_with_matches = [c for c in eligible if c in matches_by_class]
    if not classes_with_matches:
        return None

    classes_with_matches.sort(key=lambda c: (picked.get(c, 0), order.index(c)))
    chosen = classes_with_matches[0]
    bucket = matches_by_class[chosen]
    # Within a class, prefer the LARGEST physical area (short * long in mm).
    # Confidence is already filtered upstream by the OD node's conf_threshold;
    # bigger objects give the gripper a forgiving target. Conf used as tiebreak.
    bucket.sort(
        key=lambda o: (o.short_axis_mm * o.long_axis_mm, o.confidence),
        reverse=True,
    )
    return bucket[0]


def send_pick(node, target, pre_grasp_width, z_value, action_timeout) -> tuple[bool, int, str]:
    ac = ActionClient(node, PickAndPlace, "/robot/pick_and_place")
    if not ac.wait_for_server(timeout_sec=5.0):
        raise RuntimeError("/robot/pick_and_place action server not available")

    goal = PickAndPlace.Goal()
    goal.target_class = target.class_name
    goal.grasp_xyz = Point(
        x=float(target.base_xyz.x),
        y=float(target.base_xyz.y),
        z=float(z_value),
    )
    goal.grasp_yaw = float(target.grasp_yaw)
    goal.pre_grasp_width_mm = float(pre_grasp_width)
    goal.return_xyz = Point(
        x=DEFAULT_RETURN_XYZ[0],
        y=DEFAULT_RETURN_XYZ[1],
        z=DEFAULT_RETURN_XYZ[2],
    )
    goal.return_zyz_deg = list(DEFAULT_RETURN_ZYZ)

    def feedback_cb(fb):
        print(f"    [stage] {fb.feedback.stage}", flush=True)

    send_fut = ac.send_goal_async(goal, feedback_callback=feedback_cb)
    rclpy.spin_until_future_complete(node, send_fut)
    handle = send_fut.result()
    if handle is None or not handle.accepted:
        raise RuntimeError("goal rejected by action server")

    result_fut = handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_fut, timeout_sec=action_timeout)
    if not result_fut.done():
        raise RuntimeError(f"action did not finish within {action_timeout}s")
    res = result_fut.result().result
    return bool(res.success), int(res.failure_code), str(res.message)


def main() -> int:
    args = parse_args()
    order = [c.strip() for c in args.order.split(",") if c.strip()]
    bad = [c for c in order if c not in CLASSES]
    if bad:
        print(f"Unknown classes in --order: {bad}", file=sys.stderr)
        return 4

    if args.order_file:
        if args.counts:
            print(
                "Cannot use --order-file together with --counts",
                file=sys.stderr,
            )
            return 4
        try:
            explicit_counts, order_meta = parse_order_file(args.order_file)
        except ValueError as exc:
            print(f"--order-file: {exc}", file=sys.stderr)
            return 4
        per_class_arg = None  # order-file fully specifies counts
        print(f"Order file : {args.order_file}")
        if order_meta["request_id"]:
            print(f"  request_id     : {order_meta['request_id']}")
        if order_meta["recognized_text"]:
            print(f"  recognized_text: {order_meta['recognized_text']!r}")
        if order_meta["intensity"]:
            print(f"  intensity      : {order_meta['intensity']}")
    else:
        try:
            explicit_counts = parse_counts(args.counts)
        except ValueError as exc:
            print(f"--counts: {exc}", file=sys.stderr)
            return 4
        per_class_arg = args.per_class

    targets = build_target_counts(order, per_class_arg, explicit_counts)
    total_target = sum(targets.values())
    print(f"Targets: {{ "
          + ", ".join(f"{c}={targets[c]}" for c in order)
          + f" }}  total={total_target if total_target < 10**8 else 'unlimited'}")

    rclpy.init()
    node = rclpy.create_node("pick_all_helper")

    picked: dict[str, int] = {c: 0 for c in CLASSES}
    success_count = 0
    pick_count = 0
    consecutive_failures = 0
    try:
        while pick_count < args.max_picks:
            print(f"\n=== Round {pick_count + 1} "
                  f"(picked: " + ", ".join(f"{c}={picked[c]}" for c in order) + ") ===")
            print("Detecting ...", flush=True)
            try:
                det = call_detect(node, args.detect_timeout)
            except RuntimeError as exc:
                print(f"  detect failed: {exc}", file=sys.stderr)
                consecutive_failures += 1
                if consecutive_failures >= args.max_failures:
                    print(f"\n[stop] {consecutive_failures} consecutive detection failures",
                          file=sys.stderr)
                    break
                time.sleep(args.inter_pick_delay)
                continue

            if not det.success:
                print(f"  detect_once: {det.message}", file=sys.stderr)
                consecutive_failures += 1
                if consecutive_failures >= args.max_failures:
                    break
                time.sleep(args.inter_pick_delay)
                continue

            target = select_target(det, order, picked, targets)
            if target is None:
                quotas_done = all(picked[c] >= targets[c] for c in order)
                if quotas_done:
                    print(f"\n[done] all per-class quotas reached")
                else:
                    remaining = [(c, targets[c] - picked[c]) for c in order
                                 if picked[c] < targets[c]]
                    print(f"  no more detected matches; quotas still pending: {remaining}")
                    print(f"\n[done] no more targets in workspace")
                break

            pre_grasp_width = (
                args.pre_grasp_width
                if args.pre_grasp_width is not None
                else target.short_axis_mm + DEFAULT_PRE_GRASP_MARGIN_MM
            )
            z_cmd = (
                args.z_override
                if args.z_override is not None
                else target.base_xyz.z
            )
            z_cmd += PER_CLASS_Z_OFFSET.get(target.class_name, 0.0)
            print(f"  target: {target.class_name:9s} conf={target.confidence:.2f} "
                  f"base=({target.base_xyz.x:.1f}, {target.base_xyz.y:.1f}, "
                  f"{target.base_xyz.z:.1f}) -> z={z_cmd:.1f} "
                  f"yaw={target.grasp_yaw:.2f} preW={pre_grasp_width:.1f}")

            print("  sending pick_and_place ...", flush=True)
            try:
                success, failure_code, message = send_pick(
                    node, target, pre_grasp_width, z_cmd, args.action_timeout
                )
            except RuntimeError as exc:
                print(f"  action error: {exc}", file=sys.stderr)
                consecutive_failures += 1
                if consecutive_failures >= args.max_failures:
                    break
                time.sleep(args.inter_pick_delay)
                continue

            pick_count += 1
            if success:
                picked[target.class_name] += 1
                success_count += 1
                consecutive_failures = 0
                print(f"  result: success (pick #{pick_count}, "
                      f"{target.class_name}={picked[target.class_name]}/"
                      f"{targets[target.class_name]})")
            else:
                consecutive_failures += 1
                print(f"  result: FAIL code={failure_code} msg={message!r}",
                      file=sys.stderr)
                if consecutive_failures >= args.max_failures:
                    print(f"\n[stop] {consecutive_failures} consecutive failures",
                          file=sys.stderr)
                    break

            time.sleep(args.inter_pick_delay)

        print(f"\n=== Summary ===")
        print(f"  attempted : {pick_count}")
        print(f"  succeeded : {success_count}")
        for c in order:
            print(f"    {c:9s} : {picked[c]} / "
                  f"{targets[c] if targets[c] < 10**8 else '*'}")
        return 0 if success_count > 0 and consecutive_failures < args.max_failures else 1
    except KeyboardInterrupt:
        print("\n[interrupt] aborted by user", file=sys.stderr)
        return 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
