#!/usr/bin/env python3
"""Detect-and-pick a single nut by class.

Usage:
    pick_one.py <class>                     # auto-pick highest-conf nut
    pick_one.py <class> --z-override 310    # override grasp z (mm)
    pick_one.py <class> --pre-grasp-width 35
    pick_one.py <class> --dry-run           # only print, do not send action

Class: cashew | almond | pistachio | walnut

Calls /perception/detect_once, picks highest-confidence detection of the
requested class with transform_valid=True, then sends a /robot/pick_and_place
goal using detected base_xyz / grasp_yaw. pre_grasp_width defaults to
short_axis + 15 mm.
"""

from __future__ import annotations

import argparse
import sys

import rclpy
from geometry_msgs.msg import Point
from rclpy.action import ActionClient

from cobot_msgs.action import PickAndPlace
from cobot_msgs.srv import DetectOnce


CLASSES = ("cashew", "almond", "pistachio", "walnut")
DEFAULT_RETURN_XYZ = (367.0, -150.0, 70.0)
DEFAULT_RETURN_ZYZ = (168.0, 179.0, 168.0)
DEFAULT_PRE_GRASP_MARGIN_MM = 15.0

# Per-class fine-tune offset added to grasp z (mm). Negative = grip deeper
# (good for nuts that slip). Positive = grip shallower (good if pressing
# into table). Applied on top of perception z and --z-override.
PER_CLASS_Z_OFFSET = {
    "cashew": 0.0,
    "almond": 0.0,
    "pistachio": 0.0,
    "walnut": 0.0,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect and pick a single nut.")
    p.add_argument("target_class", choices=CLASSES)
    p.add_argument("--z-override", type=float, default=None,
                   help="Override grasp z (mm in base frame)")
    p.add_argument("--pre-grasp-width", type=float, default=None,
                   help="Override pre-grasp width (mm); default short_axis + 15")
    p.add_argument("--dry-run", action="store_true",
                   help="Print target only, do not send action")
    p.add_argument("--detect-timeout", type=float, default=5.0)
    p.add_argument("--action-timeout", type=float, default=120.0)
    return p.parse_args()


def call_detect(node, timeout):
    cli = node.create_client(DetectOnce, "/perception/detect_once")
    if not cli.wait_for_service(timeout_sec=timeout):
        raise RuntimeError("/perception/detect_once not available")
    fut = cli.call_async(DetectOnce.Request())
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    if not fut.done():
        raise RuntimeError("detect_once timed out")
    return fut.result()


def select_target(detection, target_class):
    matches = [
        obj for obj in detection.objects.objects
        if obj.class_name == target_class and obj.transform_valid
    ]
    if not matches:
        return None
    # Prefer the largest physical area (short * long in mm). Confidence is
    # already filtered upstream by the OD conf_threshold; bigger nuts give
    # the gripper a forgiving target. Use conf as tiebreaker.
    matches.sort(
        key=lambda o: (o.short_axis_mm * o.long_axis_mm, o.confidence),
        reverse=True,
    )
    return matches[0]


def send_pick(node, target, pre_grasp_width, z_value, action_timeout):
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
        print(f"  [stage] {fb.feedback.stage}", flush=True)

    send_fut = ac.send_goal_async(goal, feedback_callback=feedback_cb)
    rclpy.spin_until_future_complete(node, send_fut)
    handle = send_fut.result()
    if handle is None or not handle.accepted:
        raise RuntimeError("goal rejected by action server")

    result_fut = handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_fut, timeout_sec=action_timeout)
    if not result_fut.done():
        raise RuntimeError(f"action did not finish within {action_timeout}s")
    return result_fut.result().result


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = rclpy.create_node("pick_one_helper")
    try:
        print(f"Calling /perception/detect_once ...", flush=True)
        det = call_detect(node, args.detect_timeout)
        if not det.success:
            print(f"detect_once failed: {det.message}", file=sys.stderr)
            return 2
        print(f"  -> {det.message}")

        target = select_target(det, args.target_class)
        if target is None:
            print(f"No '{args.target_class}' found with transform_valid=True",
                  file=sys.stderr)
            return 3

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

        print(f"\n=== Target: {target.class_name} ===")
        print(f"  conf         : {target.confidence:.3f}")
        print(f"  base_xyz     : ({target.base_xyz.x:.1f}, "
              f"{target.base_xyz.y:.1f}, {target.base_xyz.z:.1f}) mm")
        if args.z_override is not None:
            print(f"  z override   : {args.z_override:.1f} mm "
                  f"(detected {target.base_xyz.z:.1f})")
        print(f"  grasp_yaw    : {target.grasp_yaw:.3f} rad")
        print(f"  short_axis   : {target.short_axis_mm:.1f} mm")
        print(f"  pre_grasp_w  : {pre_grasp_width:.1f} mm")
        print(f"  command z    : {z_cmd:.1f} mm")

        if args.dry_run:
            print("\n[DRY RUN] not sending action")
            return 0

        print("\nSending pick_and_place action ...", flush=True)
        result = send_pick(node, target, pre_grasp_width, z_cmd, args.action_timeout)

        print(f"\n=== Result ===")
        print(f"  success      : {result.success}")
        print(f"  failure_code : {result.failure_code}")
        print(f"  message      : {result.message}")
        return 0 if result.success else 1
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 4
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
