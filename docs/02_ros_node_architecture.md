# ROS2 Node Architecture

This document describes how the running ROS 2 graph is shaped: which
nodes exist, what they publish/subscribe, the services and actions they
expose, the parameters that govern their behavior, and the runtime flow
that ties them together.

## Index

1. Node Overview Table
2. Main Execution Graph
3. ROS Interfaces (topics / services / actions)
4. Task Manager State Machine
5. Pick-and-Place Sequence
6. Conveyor Trigger Logic
7. Configuration and Parameters
8. Debugging Topics and Commands

## Document set

- `docs/01_system_architecture.md` — system-level design and rationale.
- `docs/02_ros_node_architecture.md` — **this file**.
- `docs/03_run_manual.md` — operator-facing run order.
- `docs/04_validation_checklist.md` — pre-flight test checklist.
- `docs/cleanup_deletion_proposal.md` and
  `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` — meta/cleanup
  records. The `_archive_cleanup/` directory is **not active code** and
  is excluded from the runtime graph described in this file.

ROS distribution: ROS 2 Humble. All Python nodes in this repo are
`ament_python`; `cobot_msgs` and `cobot_bringup` are `ament_cmake`.

> **Naming convention used throughout this document.** The Doosan-side
> nodes live in the `dsr01` namespace, so their **node names** are
> `/dsr01/robot_control_node`, `/dsr01/robot_action_helper`, and
> `/dsr01/robot_pose_helper`. **Service and action names are absolute**
> in this repo — they are declared in `robot_control.yaml` with a
> leading `/` (e.g. `/robot/pick_and_place`, `/robot/home`,
> `/robot/stop`, `/robot/get_current_pose`) and are therefore **not**
> prefixed with `/dsr01/` at runtime. The task manager calls them with
> the same absolute names from `task_manager.yaml`.

---

## 1. Node Overview Table

The table covers the production runtime nodes brought up by
`cobot_bringup/launch/full_system.launch.py` plus the conveyor (launched
separately) and the upstream RealSense / Doosan packages.

> The **Actions** column also lists notable external interfaces a node
> calls as a *client* (action goals it sends, and the small set of
> external service clients worth knowing about — e.g. the Doosan
> `/dsr01/system/get_current_pose` passthrough). Keeping them on the
> same row lets you read each node end-to-end without cross-referencing
> the §3 interface tables. Anything tagged *(server)* is hosted by the
> node; anything tagged *(client)* is consumed by it.

| Node | Package | Key file | Role | Publishes | Subscribes | Services (server) | Actions | Parameters |
|---|---|---|---|---|---|---|---|---|
| `task_manager_node` | `cobot_task_manager` | `cobot_task_manager/task_manager_node.py` | Order-driven orchestrator: detect → select → pick loop | `/task/status` (`std_msgs/String`), `/task/result` (`std_msgs/String`) | — | `/task/start` (`std_srvs/Trigger`) | `/robot/pick_and_place` *(client)*, `/perception/detect_once` *(client)*, `/robot/home` *(client)*, `/db/get_nut_order` *(client when `order_source=db`)* | `order_source` (`mock`/`db`/`file`), `mock_order_*`, `db_service_name`, `file_order_path`, `file_order_require_success`, `class_priority`, `conf_gate`, `min_depth_mm`, `workspace_*_mm`, `return_xyz_mm`, `return_zyz_deg`, `pre_grasp_margin_mm`/`min_mm`/`max_mm`, `pick_offsets_path`, `perception_service_name`, `pick_action_name`, `home_service_name`, `max_detect_misses`, `max_grasp_failures`, `service_timeout_sec`, `action_timeout_sec`, `inter_pick_delay_sec`, `autostart` |
| `object_detection_node` | `cobot_object_detection` | `cobot_object_detection/object_detection_node.py` | YOLOv8-OBB inference on the RealSense color stream; multi-frame fusion | `/detection/objects` (`cobot_msgs/DetectedObjectArray`) | `/camera/camera/color/image_raw` (`sensor_msgs/Image`, sensor QoS) | — | — | `model_path`, `class_names`, `imgsz`, `conf_threshold`, `iou_threshold`, `device`, `multi_frame_window_sec`, `cluster_distance_threshold_px`, `color_topic`, `output_topic`, `publish_when_empty` |
| `perception_transform_node` | `cobot_perception` | `cobot_perception/perception_transform_node.py` | Depth lookup inside OBB, hand-eye + pinhole lift, base-frame xyz + grasp yaw | — | `/detection/objects`, `/camera/camera/aligned_depth_to_color/image_raw`, `/camera/camera/color/camera_info` | `/perception/detect_once` (`cobot_msgs/srv/DetectOnce`) | `/robot/get_current_pose` *(client when `tcp_source=service`)* | `gripper2camera_npy`, `min_depth_camera_mm`, `max_depth_camera_mm`, `depth_offset_mm`, `min_depth_base_mm`, `tcp_source` (`fixed`/`service`), `fixed_tcp_xyz_mm`, `fixed_tcp_zyz_deg`, `tcp_service_name`, `tcp_service_timeout_sec`, `detection_topic`, `depth_topic`, `camera_info_topic`, `service_name` |
| `mock_perception_node` | `cobot_perception` | `cobot_perception/mock_perception_node.py` | Hardware-free `/perception/detect_once` server (8-nut hardcoded scene) | — | — | `/perception/detect_once` | — | — |
| `robot_control_node` | `cobot_robot_control` | `cobot_robot_control/robot_control_node.py` | Pick-and-place action server, motion + gripper façade, place-ready beacon | `/conveyor/place_ready` (`std_msgs/Bool`, 10 Hz) | — | `/robot/home`, `/robot/stop` (both `std_srvs/Trigger`), `/robot/get_current_pose` (`cobot_msgs/srv/GetCurrentPose`) | `/robot/pick_and_place` *(server)*, `/dsr01/system/get_current_pose` *(client)* | `robot_id`, `robot_model`, `motion_backend` (`real`/`mock`), `gripper_backend` (`modbus`/`mock`/`tool_dio`), `gripper_ip`, `gripper_port`, `gripper_force_x10`, `gripper_open_width_x10`, `home_joints_deg`, `approach_offset_z_mm`, `velocity`/`acceleration`/`*_slow`, `grip_settle_timeout_sec`, `grasp_local_offset_xy_mm`, `action_name`, `home_service_name`, `stop_service_name`, `pose_service_name`, `doosan_pose_service`, `pose_passthrough_timeout_sec`, `place_ready_topic`, `place_y_margin_mm`, `place_ready_publish_period_sec`, `workspace_enabled`, `workspace_*_mm` |
| *Gripper control* | `cobot_robot_control` | `cobot_robot_control/gripper_controller.py` | **Not a ROS node** — Python `Protocol` with three backends (`MockGripperBackend`, Modbus RG2, `tool_dio` stub). Used in-process by `robot_control_node`. | — | — | — | — | — |
| `firebase_status_bridge` | `cobot_voice` | `cobot_voice/firebase_status_bridge.py` | Mirror robot pipeline progress to Firestore `robot_state` field | — | `/task/status`, `/task/result`, `/conveyor/place_ready` | — | — | `status_topic`, `result_topic`, `place_ready_topic` |
| `voice_processing_node` | `cobot_voice` | `cobot_voice/voice_processing_node.py` | **Legacy** wake-word + STT publisher. Not consumed by any in-tree node; production voice path is `voice_to_robot.py` (in-process). | `/voice/text` (`std_msgs/String`), `/voice/status` (`std_msgs/String`) | (mic capture, not a ROS topic) | — | — | (no ROS parameters) |
| `web_voice_bridge_server` | `cobot_voice` | `cobot_voice/web_voice_bridge_server.py` | **Not a ROS node** — local `ThreadingHTTPServer` on `127.0.0.1:8765` driving the voice flow for the web UI. | — | — | — | — | CLI: `--host`, `--port` |
| `conveyor_serial_node` | `conveyor_controller` | `conveyor_controller/conveyor_serial_node.py` | Forward `/conveyor_cmd` strings to Arduino UNO; turn `/conveyor/place_ready` False→True edges into one timed advance | — | `/conveyor_cmd` (`std_msgs/String`), `/conveyor/place_ready` (`std_msgs/Bool`) | — | — | `port`, `baudrate`, `serial_timeout`, `arduino_reset_delay`, `command_topic`, `place_ready_topic`, `auto_command`, `auto_run_duration_sec` |
| `realsense2_camera_node` (`/camera/camera`) | `realsense2_camera` (upstream) | `rs_launch.py` | RealSense color + aligned depth + camera_info | `/camera/camera/color/image_raw`, `/camera/camera/aligned_depth_to_color/image_raw`, `/camera/camera/color/camera_info`, `/camera/camera/depth/color/points` | — | — | — | `enable_color`, `enable_depth`, `rgb_camera.color_profile` (`1280x720x30`), `depth_module.depth_profile` (`848x480x30`), `align_depth.enable`, `enable_rgbd`, `pointcloud.enable`, `initial_reset` |
| `dsr_bringup2` stack (`/dsr01/...`) | `dsr_bringup2` (upstream) | `dsr_bringup2_rviz.launch.py` | Doosan controller bring-up: `ros2_control_node`, `dsr_controller2`, `joint_state_broadcaster`, system services (incl. `/dsr01/system/get_current_pose`) | `/dsr01/joint_states`, controller topics | — | `/dsr01/system/get_current_pose` (and many others) | — | `name=dsr01`, `host`, `port`, `mode` (`real`/`virtual`), `model` (`m0609`), `gui=false` |

In-process helper nodes spawned **inside** `robot_control_node` (visible
to `ros2 node list` as ordinary nodes):

- `robot_action_helper` — owns the `/robot/pick_and_place` action server,
  `/robot/home`, `/robot/stop` services. 4-thread executor.
- `robot_pose_helper` — owns `/robot/get_current_pose` and the
  `/dsr01/system/get_current_pose` client. 2-thread executor.

These helpers exist so DSR_ROBOT2 traffic on the main node's executor
cannot starve action acceptance or pose-service responses (see
`robot_control_node.py` lines 175–260 for the full rationale).

Empty stubs (no implementation, not launched anywhere): `cobot_safety`
(`safety_manager_node`), `cobot_policy` (`policy_selector_node`).

---

## 2. Main Execution Graph

```
voice_to_robot.py    or    web UI POST /voice-audio/start
                                   │
                                   ▼ (in-process)
                         voice_order_flow.run_recommendation_flow
                         → cobot_voice/output/latest_order.json
                         → Firestore robot_session/current
                                   │
                                   ▼  std_srvs/Trigger
                              /task/start
                                   │
                                   ▼
                         ┌───────────────────────┐
                         │   task_manager_node   │
                         │  (state machine §4)   │
                         └─────┬───────────────┬─┘
            cobot_msgs/srv/    │               │  cobot_msgs/action/
            DetectOnce         │               │  PickAndPlace
                               ▼               ▼
                  /perception/detect_once   /robot/pick_and_place
                               │                       │
                               ▼                       ▼
                   perception_transform_node    robot_control_node
                               │                       │
                       /detection/objects              │ Bool /conveyor/place_ready
                               ▲                       ▼ (10 Hz + edge)
                   object_detection_node       conveyor_serial_node
                               ▲                       │
                /camera/camera/color/image_raw         ▼
                /camera/camera/aligned_depth_to_color  Arduino UNO (USB serial)
                /camera/camera/color/camera_info
                               ▲
                   realsense2_camera_node

       task_manager_node ──► /task/status (String)  ──┐
                          ──► /task/result (String)  ──┴──►  firebase_status_bridge
       robot_control_node ─► /conveyor/place_ready  ────────►  ─────────► Firestore
                                                                          (robot_state)
```

For the real-hardware path, `robot_control_node` lives in the `dsr01`
namespace, talks to `dsr_bringup2` via `/dsr01/system/get_current_pose`
and the DSR_ROBOT2 Python module, and drives the OnRobot RG2 over Modbus
TCP at `192.168.1.1:502` (no ROS interface for the gripper itself).

---

## 3. ROS Interfaces

### 3.1 Topics

| Topic | Type | Producer | Consumer(s) | Payload meaning | When used |
|---|---|---|---|---|---|
| `/camera/camera/color/image_raw` | `sensor_msgs/Image` | `realsense2_camera_node` | `object_detection_node`, `scripts/yolo_rqt_view.py` | RGB color frame, 1280×720@30, sensor QoS (best-effort, depth=2) | Continuous while RealSense is up |
| `/camera/camera/aligned_depth_to_color/image_raw` | `sensor_msgs/Image` | `realsense2_camera_node` | `perception_transform_node` | Depth aligned to color (mm-scale uint16), 848×480@30 | Continuous; latched by `_on_depth` callback |
| `/camera/camera/color/camera_info` | `sensor_msgs/CameraInfo` | `realsense2_camera_node` | `perception_transform_node` | Pinhole intrinsics (fx, fy, ppx, ppy from `K`) | Continuous; cached on first change |
| `/detection/objects` | `cobot_msgs/DetectedObjectArray` | `object_detection_node` | `perception_transform_node` | Fused 2D OBBs (`class_name`, `confidence`, `cx/cy/width/height/theta`); `transform_valid=false` here | One message per processed color frame (gated by `_processing` flag) |
| `/perception/detect_once` *(service — listed here for completeness)* | `cobot_msgs/srv/DetectOnce` | `perception_transform_node` | `task_manager_node`, `scripts/pick_*.py` | Latest detections lifted to base frame (`base_xyz` in mm, `grasp_yaw` rad, `short_axis_mm`, `long_axis_mm`, `transform_valid=true`) | Once per task-loop iteration |
| `/conveyor/place_ready` | `std_msgs/Bool` | `robot_control_node` | `conveyor_serial_node`, `firebase_status_bridge` | TCP at place-y within `place_y_margin_mm` AND gripper open at place pose | 10 Hz baseline + edge transitions during `place`/`retreat` stages |
| `/conveyor_cmd` | `std_msgs/String` | (operator / scripts) | `conveyor_serial_node` | Belt command: `F1`–`F100`, `R1`–`R100`, or `STOP` (uppercase, newline-terminated on serial) | Manual control / debugging |
| `/task/status` | `std_msgs/String` | `task_manager_node` | `firebase_status_bridge` | `<state> [<info>]` — `init`, `detect`, `select_target <class>`, `pick_and_place <class>`, `done`, `aborted <reason>`, `safety_stop` | Every state transition in `_set_state` |
| `/task/result` | `std_msgs/String` | `task_manager_node` | `firebase_status_bridge` | `success <info>` or `failure <reason>` (e.g., `home_failed`, `action_failure`, `safety_stop`, `failure_code=N`) | Once per task run, at terminal state |
| `/voice/text` | `std_msgs/String` | `voice_processing_node` (legacy) | (none in-tree) | Whisper transcript | Legacy; not used by the production voice path |
| `/voice/status` | `std_msgs/String` | `voice_processing_node` (legacy) | (none in-tree) | `idle`, `wake_detected`, `listening`, `transcribing`, `processing`, `error` | Legacy |

### 3.2 Services

| Service | Type | Server | Client(s) | Payload meaning | When used |
|---|---|---|---|---|---|
| `/task/start` | `std_srvs/Trigger` | `task_manager_node` | `voice_to_robot.py` (via `cobot_voice.task_manager_dispatcher` → `ros2 service call`), operator | Start the worker if it is not already running. `success=False` with message `"task already running"` if it is. | When `task_autostart:=false` and an external trigger fires |
| `/perception/detect_once` | `cobot_msgs/srv/DetectOnce` | `perception_transform_node` (or `mock_perception_node`) | `task_manager_node`, `scripts/pick_one.py`, `scripts/pick_all.py` | One-shot detection cycle. Response carries `objects.objects[]` with base-frame xyz, grasp yaw, mm sizes; `success=True` only if depth + intrinsics + detection are all populated. | Once per pick attempt |
| `/robot/home` | `std_srvs/Trigger` | `robot_control_node` (on `robot_action_helper`) | `task_manager_node` | Move the arm to `home_joints_deg` via `move_joint`. | Once at task start, before the loop |
| `/robot/stop` | `std_srvs/Trigger` | `robot_control_node` (on `robot_action_helper`) | (operator) | Set the internal stop event, drop place_ready, open the gripper. | Manual stop. Pick action observes the event via `is_cancelled`. |
| `/robot/get_current_pose` | `cobot_msgs/srv/GetCurrentPose` | `robot_control_node` (on `robot_pose_helper`) | `perception_transform_node` (when `tcp_source=service`), scripts | Return the current Doosan TCP — `xyz_mm` and `zyz_deg` (ZYZ Euler degrees). | Each `detect_once` call when `tcp_source=service` (the production default in `perception.yaml`) |
| `/dsr01/system/get_current_pose` | `dsr_msgs2/srv/GetCurrentPose` | `dsr_bringup2` | `robot_control_node` (passthrough source) | Doosan native pose service (`space_type=1` → ROBOT_SPACE_TASK, returns posx). | Backend for `/robot/get_current_pose` |
| `/db/get_nut_order` | `cobot_msgs/srv/GetNutOrder` | **(no server in this repo — Not Implemented)** | `task_manager_node` (when `order_source=db`) | Counts per nut class (`almond`, `cashew`, `pistachio`, `walnut`) with `success`/`message`. | Would be once per task run; today setting `order_source:=db` will time out. |

### 3.3 Actions

| Action | Type | Server | Client(s) | Payload meaning | When used |
|---|---|---|---|---|---|
| `/robot/pick_and_place` | `cobot_msgs/action/PickAndPlace` | `robot_control_node` (on `robot_action_helper`) | `task_manager_node`, `scripts/pick_one.py`, `scripts/pick_all.py` | Goal: `target_class`, `grasp_xyz` (mm), `grasp_yaw` (rad), `pre_grasp_width_mm` (≤0 disables pre-position), `return_xyz`, `return_zyz_deg`. Feedback: `stage` ∈ {`pre_grasp_width`, `approach`, `grasp`, `verify_grip`, `lift`, `transit`, `place`, `retreat`, `home`}. Result: `success`, `failure_code` ∈ {0 ok, 1 approach_fail, 2 grasp_not_detected, 3 motion_fail, 4 safety_stop, 5 workspace_violation}, `message`. | Once per nut in the order; the `_busy_lock` rejects concurrent goals |

---

## 4. Task Manager State Machine

The actual states live in `cobot_task_manager/cobot_task_manager/task_state.py`
as `TaskState` (a `str`-Enum). They are emitted on `/task/status` via
`_set_state` in `task_manager_node.py`. The full set is:

```
IDLE              "idle"
INIT              "init"
DETECT            "detect"
SELECT_TARGET     "select_target"
PICK_AND_PLACE    "pick_and_place"
DONE              "done"
ABORTED           "aborted"
SAFETY_STOP       "safety_stop"
```

There are **no separate `WAITING_FOR_TASK`, `PLACING`, `CONVEYOR_MOVING`,
`TASK_DONE`, or `ERROR` states in the task manager**. The mapping to your
proposed model is:

| Proposed state | Closest TaskState | Notes |
|---|---|---|
| `IDLE` | `IDLE` | Set in `__init__` before the worker starts |
| `WAITING_FOR_TASK` | `IDLE` | When `autostart=false`, the node sits in `IDLE` until `/task/start` |
| `DETECTING` | `DETECT` | Set immediately before `_detect_once` |
| `PICKING` | `PICK_AND_PLACE` | Covers approach → grasp → verify_grip → lift |
| `PLACING` | `PICK_AND_PLACE` | Inferred externally from `/conveyor/place_ready` edge |
| `CONVEYOR_MOVING` | `PICK_AND_PLACE` | Same: derived from the same edge by `firebase_status_bridge` |
| `TASK_DONE` | `DONE` | Final state on success |
| `ERROR` | `ABORTED` (and `SAFETY_STOP` for cancellation) | `aborted` carries a reason in the info field |

### 4.1 Transitions (real names)

```
                  ┌───── /task/start ─────┐
                  │                       │
                  ▼                       │
        ┌────────────────┐  start_worker  │
        │      IDLE      ├────────────────┘
        └────────┬───────┘
                 │
                 ▼
         ┌────────────────┐
         │      INIT      │  order_provider.fetch() + /robot/home
         └───┬────────┬───┘
             │        │ home_failed / order_fetch_failed
             │        ▼
             │   ┌──────────┐
             │   │ ABORTED  │ ── publish failure on /task/result ──► (exit)
             │   └──────────┘
             │
             ▼
       ┌────────────┐
   ┌──►│   DETECT   │ ── detect_once miss (≥ max_detect_misses) ──► SKIP_CLASS
   │   └─────┬──────┘
   │         │ candidate ok
   │         ▼
   │   ┌──────────────────┐
   │   │  SELECT_TARGET   │
   │   └─────────┬────────┘
   │             │
   │             ▼
   │   ┌──────────────────┐
   │   │  PICK_AND_PLACE  │ ── action.success ──► consume_one ──► sleep inter_pick_delay ──┐
   │   └─────────┬────────┘                                                                │
   │             │ failure                                                                 │
   │             ▼                                                                         │
   │   ┌─────────────────────────┐                                                         │
   │   │ retry_policy decision:  │                                                         │
   │   │   RETRY_PICK            │── loop ──┐                                              │
   │   │   RETRY_DETECT          │── loop ──┤                                              │
   │   │   SKIP_CLASS            │── mark_skipped ──┐                                      │
   │   │   ABORT (codes 1/3/4/5) │── ABORTED + exit │                                      │
   │   └─────────────────────────┘                  │                                      │
   │                                                │                                      │
   └────────────────────────────────────────────────┴──────────────────────────────────────┘
                          (loop until !order.has_remaining() OR stop_event)
                                      │                          │
                                      ▼                          ▼
                                ┌──────────┐               ┌──────────────┐
                                │   DONE   │               │ SAFETY_STOP  │
                                └──────────┘               └──────────────┘
```

The retry decisions are encoded in
`cobot_task_manager/cobot_task_manager/retry_policy.py`:

- `on_detect_miss(consecutive_misses)` → `RETRY_DETECT` until
  `max_detect_misses`, then `SKIP_CLASS`.
- `on_action_failure(failure_code, consecutive_grasp)`:
  - code 2 (`grasp_not_detected`) → `RETRY_PICK` until
    `max_grasp_failures`, then `SKIP_CLASS`.
  - codes 1, 3, 4, 5 (`approach_fail`, `motion_fail`, `safety_stop`,
    `workspace_violation`) → `ABORT` (human intervention required).

---

## 5. Pick-and-Place Sequence

The action server lives in `robot_control_node`; the actual stage
sequence is in
`cobot_robot_control/cobot_robot_control/motion_sequence.py`'s
`execute_pick_and_place`. A successful pick fires the following stages
(strings emitted as feedback):

1. **Detect requested nut** — `task_manager_node` calls
   `/perception/detect_once`. (Outside the action.)
2. **Transform target to base frame** — `perception_transform_node`
   computes `base_xyz`, `grasp_yaw`, `short_axis_mm`, `long_axis_mm` for
   each detection and the task manager picks a candidate via
   `target_selector.choose_target` (class + workspace + confidence + depth
   + transform-valid filter; tiebreak by OBB area then confidence).
3. **`pre_grasp_width`** — gripper opens to `pre_grasp_width_mm` (short
   axis + margin, clamped). Skipped if `≤0`.
4. **`approach`** — line move to `[grasp_x, grasp_y, grasp_z + approach_offset_z_mm]`,
   nominal velocity. Workspace guard ran already (rejected with
   `failure_code=5` before any motion).
5. **`grasp`** — slow-speed line move down to `grasp_pose`, then
   `gripper.close()`, then `wait_until_idle` (busy=True → busy=False).
6. **`verify_grip`** — `gripper.is_grip_detected()`; if false, open the
   gripper, retreat to the approach pose, and abort with
   `failure_code=2` (`grasp_not_detected`).
7. **`lift`** — line move back up to the approach pose at nominal speed.
8. **`transit`** — line move to `above_return = [return_x, return_y,
   return_z + approach_offset_z_mm]`.
9. **`place`** — slow-speed line move down to `place_pose`
   (`[return_x, return_y, return_z]`), `gripper.open()`, `wait_until_idle`,
   then evaluate `is_tcp_at_place_y()` (TCP y within `place_y_margin_mm`
   of `return_y`). On success, `place_ready_cb(True, "gripper_open_at_place")`
   fires — `robot_control_node` flips `/conveyor/place_ready` to True.
10. **Place-ready event** — `conveyor_serial_node` sees the False→True
    edge on `/conveyor/place_ready` and starts a single timed advance.
11. **`retreat`** — line move back to `above_return`; `place_ready_cb(False, "retreat")`
    flips the topic back to False (only after the conveyor edge has been
    captured).
12. **`home`** — joint move to `home_joints_deg`. The action returns
    `success=True, failure_code=0`.

`task_manager_node` then sleeps `inter_pick_delay_sec` (default `0.5` s)
to let mid-motion camera frames drain from
`perception_transform_node`'s buffer before issuing the next
`detect_once`.

---

## 6. Conveyor Trigger Logic

- **Publisher**: `robot_control_node`. The topic is `/conveyor/place_ready`
  (`std_msgs/Bool`). It is published at `place_ready_publish_period_sec`
  (default `0.1` s, i.e. 10 Hz) by a timer plus eagerly on every state
  change inside `_set_place_ready`. The True transition is set during the
  `place` stage when `is_tcp_at_place_y()` is true and the gripper has
  opened. The False transition is set on `retreat`, on `pick_and_place`
  finish, on `/robot/stop`, and on motion errors / TCP read failures.
- **Subscribers**: `conveyor_serial_node` (the actual hardware driver) and
  `firebase_status_bridge` (mirrors the edge to Firestore as
  `placing` + `conveyor_moving` `robot_state` writes, back to back).
- **Why edge-triggered**: the topic is published continuously at 10 Hz,
  so the conveyor cannot use level semantics — it would re-trigger every
  cycle. `conveyor_serial_node._place_ready_callback` keeps a
  `self._last_place_ready` flag and only acts on `False → True`. A second
  edge that arrives while a previous run is still active is logged
  (`Ignoring place_ready trigger while conveyor auto-run is active`) and
  ignored. Held-True does not re-trigger.
- **Movement is duration-based, not step-based.** On a True edge the
  node sends `auto_command` (default `R80`) over serial, starts a
  one-shot `create_timer(auto_run_duration_sec, _auto_stop_callback)`,
  and on timer expiry sends `STOP`. The Arduino sketch
  (`conveyor_controller/arduino/ConveyorControl_Program/`) speaks
  `F<1-100>`, `R<1-100>`, `STOP` — there is no current "run for N steps"
  command. Step-mode firmware (`S<N>` + ack) is documented as **future
  work** in `conveyor_controller/README.md`; treat the per-pick advance
  distance as approximate and verify with a tape measure when first
  setting up.

---

## 7. Configuration and Parameters

This section lists the knobs you will most often touch when switching
between mock and real hardware. Each item points at the file where the
authoritative default lives.

### 7.1 Mock vs real mode

There are three independent dials that together select dry-run / mock /
real behavior:

| Dial | File | Values | Effect |
|---|---|---|---|
| `motion_backend` | `cobot_robot_control/config/robot_control.yaml` (mock-default) or `robot_control.real.yaml` | `mock` \| `real` | `mock` returns immediately; `real` binds DSR_ROBOT2 and moves the Doosan |
| `gripper_backend` | same | `mock` \| `modbus` \| `tool_dio` (stub) | `modbus` opens a Modbus TCP client to RG2 |
| `tcp_source` | `cobot_perception/config/perception.yaml` | `fixed` \| `service` | `service` calls `/robot/get_current_pose` per detect cycle (default in real mode) |

Top-level launch toggles in `cobot_bringup/launch/full_system.launch.py`:

- `enable_realsense:=true|false`
- `enable_dsr_bringup:=true|false`
- `dsr_mode:=virtual|real`
- `task_autostart:=true|false`
- `order_source:=mock|db|file`
- `file_order_path:=<absolute path to latest_order.json>`
- `enable_firebase_status_bridge:=true|false`
- `config_robot_control:=<share>/cobot_robot_control/config/robot_control.real.yaml`

To opt **into** real hardware you must pass *both*
`enable_dsr_bringup:=true dsr_mode:=real` *and* the real-config path —
otherwise the safe mock-default YAML wins.

### 7.2 Robot IP and ports

- Doosan controller — `host:=192.168.1.100`, `port:=12345` (defaults in
  `robot.launch.py`). Override per environment if needed.
- OnRobot RG2 — `gripper_ip: 192.168.1.1`, `gripper_port: 502` (in
  `robot_control.yaml`). Modbus TCP.

### 7.3 Conveyor serial port

- `port: /dev/ttyACM0` (default in
  `conveyor_controller/config/conveyor_controller.yaml`).
- `baudrate: 115200` — must match the Arduino sketch.
- `arduino_reset_delay: 2.0` — wait after opening the port so the UNO
  can finish its USB-reset boot.
- Override with `ros2 launch conveyor_controller conveyor_controller.launch.py port:=/dev/ttyACMx baudrate:=...`.

### 7.4 Place point (return / drop pose)

- In `cobot_task_manager/config/task_manager.yaml`:
  ```yaml
  return_xyz_mm:  [367.0, -150.0, 90.0]
  return_zyz_deg: [168.0, 179.0, 168.0]
  ```
  These are the goal `return_xyz` / `return_zyz_deg` fields on the action
  goal.
- `place_y_margin_mm: 3.0` (in `robot_control.yaml`) — the tolerance used
  by `is_tcp_at_place_y()` when deciding to flip place_ready True.
- `approach_offset_z_mm: 80.0` (in `robot_control.yaml`) — the lift used
  for both approach and `above_return`.

### 7.5 Per-class Z offsets

- Single source of truth: `cobot_config/config/pick_offsets.yaml`.
- Loader: `cobot_task_manager.pick_offsets.load_pick_offsets` resolves
  in this order:
  1. explicit `pick_offsets_path` parameter (in `task_manager.yaml`),
  2. `COBOT_PICK_OFFSETS_PATH` env var,
  3. `ament_index` share lookup,
  4. source-tree fallback.

  If none of those candidates points at a readable file, the loader
  returns `DEFAULT_OFFSETS_MM` (`almond=0`, `cashew=0`, `pistachio=0`,
  `walnut=-1.0`). Per-class entries missing from a YAML that *did* load
  fall back to the same defaults.
- Applied **only** at the pick stage, added to `goal.grasp_xyz.z`.
- Current values:
  ```yaml
  per_class_z_offset_mm:
    almond: 0.0
    cashew: 0.0
    pistachio: 0.0
    walnut: -1.0
  ```
- Note: `scripts/pick_one.py` and `scripts/pick_all.py` keep their own
  `PER_CLASS_Z_OFFSET` dicts at the top; they are **not** loaded from
  the YAML automatically. **Needs verification** whether they should be
  (kept this way intentionally, per current code).

### 7.6 ROS_DOMAIN_ID

- Reference value `66` is recorded in `cobot_bringup/config/params.yaml`,
  but **that file is not loaded by any launch file in `cobot_bringup/launch/`**.
  The effective domain is whatever `ROS_DOMAIN_ID` is in the operator's
  shell at launch time. **Needs verification** if you want this enforced
  centrally.

### 7.7 Object detection model path

- `cobot_object_detection/config/object_detection.yaml`:
  ```yaml
  model_path: ""
  device: ""    # "" auto, "cpu", "cuda:0"
  imgsz: 800
  conf_threshold: 0.75
  ```
- Resolution order (`cobot_object_detection/cobot_object_detection/model_paths.py`):
  1. explicit `model_path` (absolute, or relative to CWD, or relative to
     ament share),
  2. ament share `models/best.pt` (installed via
     `cobot_object_detection/setup.py` from the
     `experiments/cobot_OD_obb_nano/.../weights/best.pt` symlink),
  3. source-tree fallback under `experiments/`.

### 7.8 Calibration config

- `cobot_perception/config/perception.yaml` — `gripper2camera_npy` is
  **required** (path to `T_gripper2camera.npy`); `depth_offset_mm`
  default `-35.0`; `min_depth_camera_mm`/`max_depth_camera_mm`/`min_depth_base_mm`
  gates.
- `cobot_config/config/handeye.yaml` — reference values; not actually
  loaded by `perception_transform_node` today.
- `cobot_config/config/workspace.yaml` — reference values; the runtime
  workspace lives in `task_manager.yaml` and `robot_control.yaml`.

---

## 8. Debugging Topics and Commands

### 8.1 Inspect the live graph

```bash
ros2 node list
ros2 topic list
ros2 topic list -t                 # show types
ros2 service list
ros2 service list -t
ros2 action list
ros2 action list -t

# What's connected to a topic / service / action?
ros2 topic info /conveyor/place_ready
ros2 service info /perception/detect_once
ros2 action info /robot/pick_and_place
```

### 8.2 Watch the task manager

```bash
ros2 topic echo /task/status
ros2 topic echo /task/result
ros2 topic echo /conveyor/place_ready
```

`/task/status` is one line per state transition; `/task/result` is one
line per task run, terminal only.

### 8.3 Trigger a "fake" task start

When `task_autostart:=false`, the worker waits for an external trigger:

```bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

Expected reply: `success=True message='task started'` (or
`success=False message='task already running'`).

To bypass the file-mode JSON entirely and test the whole loop with
hardcoded counts, launch with `order_source:=mock` and the
`mock_order_*` parameters in `task_manager.yaml`.

### 8.4 Manually fire a place-ready edge (no robot needed)

```bash
# Flip True (one edge → one belt advance)
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
# Reset to False so the next True is a new edge
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: false}"
```

`conveyor_serial_node` will run `auto_command` for `auto_run_duration_sec`
and STOP. Useful for verifying conveyor wiring without running the
robot.

### 8.5 Manually drive the conveyor

```bash
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'F30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'R30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'STOP'}"
```

### 8.6 Sanity-check perception and robot

```bash
# Camera streaming?
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw   # expect ~30 Hz

# Detection pipeline running?
ros2 topic hz /detection/objects

# Live TCP read works?
ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"

# One detection cycle (returns base-frame xyz for all detections)
ros2 service call /perception/detect_once cobot_msgs/srv/DetectOnce "{}"

# Move home (mock or real depending on robot_control config)
ros2 service call /robot/home std_srvs/srv/Trigger "{}"
ros2 service call /robot/stop std_srvs/srv/Trigger "{}"
```

### 8.7 Send a single pick action by hand

The repo ships scripts that assemble a `PickAndPlace` goal from a
`detect_once` response — preferred over composing the goal yaml by hand:

```bash
~/cobot2_ws/scripts/pick_one.py cashew --dry-run         # print only
~/cobot2_ws/scripts/pick_one.py cashew --z-override 315  # send action
```

For a programmatic CLI form:

```bash
ros2 action send_goal -f /robot/pick_and_place cobot_msgs/action/PickAndPlace \
  "{target_class: 'cashew',
    grasp_xyz: {x: 400.0, y: 0.0, z: 60.0},
    grasp_yaw: 0.0,
    pre_grasp_width_mm: 30.0,
    return_xyz: {x: 367.0, y: -150.0, z: 90.0},
    return_zyz_deg: [168.0, 179.0, 168.0]}"
```

> Always `--dry-run` first against a real robot. The action server's
> workspace guard rejects out-of-box goals with `failure_code=5` before
> motion, but the operator should still verify the numbers are sane.

### 8.8 Inspect parameters at runtime

```bash
ros2 param list /task_manager_node
ros2 param get  /task_manager_node order_source
ros2 param get  /dsr01/robot_control_node motion_backend
ros2 param get  /perception_transform_node tcp_source
ros2 param set  /conveyor_serial_node auto_run_duration_sec 3.0
```

### 8.9 Tail node logs

`ros2 launch ... output:=screen` is the default in this repo, but if you
need to read after the fact:

```bash
ls -t ~/.ros/log/                 # newest run first
ros2 launch cobot_bringup full_system.launch.py | tee /tmp/run.log
```

Look for these markers at boot (mirror of the existing run manual):

- `Subscribed to /camera/camera/color/image_raw, publishing on /detection/objects`
- `Service /perception/detect_once ready`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `FileOrderProvider reading /.../latest_order.json` (only when
  `order_source:=file`)

The companion document `docs/03_run_manual.md` chains these checks into
a recommended boot order, and `docs/04_validation_checklist.md` lists
the exact pass/fail criteria.
