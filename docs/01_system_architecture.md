# System Architecture

This document describes the final state of the `cobot2_ws` workspace: what
the system does, the runtime components that make it happen, the data
contracts between them, the hardware it expects, and the safety design.
It is written for a teammate who needs to understand the system **before**
running it.

## Index

1. Project Goal
2. End-to-End Flow
3. Runtime Components
4. Data Contract
5. Hardware Architecture
6. Safety Design
7. Current Known Gaps / Decisions

## Document set

| Doc | Purpose |
|---|---|
| `docs/01_system_architecture.md` (this file) | What the system does and why |
| `docs/02_ros_node_architecture.md` | Per-node ROS interface reference |
| `docs/03_run_manual.md` | Step-by-step operator run order |
| `docs/04_validation_checklist.md` | Pre-flight test checklist |
| `docs/cleanup_deletion_proposal.md` | Deletion plan for files that have been archived or flagged for removal |
| `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` | Per-cleanup batch manifest — reason / evidence / risk for every archived file |

The legacy file `docs/run_manual.md` and the design-history files
(`docs/voice_to_robot_integration_plan.md`,
`docs/three_firebase_bridge_*.md`,
`docs/nut_recommendation_*.md`,
`docs/stt_db_tts_robot_integration.md`) are **superseded** by the four
documents above. They remain in the tree as history but contain stale
paths (`~/cobot_ws/...` vs the actual `~/cobot2_ws/...`), outdated
calibration values, and references to integrations that have since
shipped. Do not use them as the primary reference.

The directory `_archive_cleanup/<YYYYMMDD>/` (currently `20260508/`) is
**not active code**. It holds files that have been moved out of the
runtime tree pending a deletion decision. Do not `source`, `colcon
build`, `import`, or otherwise run anything from there; the archive's
purpose is to preserve git history while keeping the active tree
clean. See `docs/cleanup_deletion_proposal.md` for the deletion plan.

---

## 1. Project Goal

The system is a voice-driven nut pick-and-place demo built on a Doosan M0609
6-DOF cobot with an OnRobot RG2 gripper, an Intel RealSense camera, and an
Arduino-controlled stepper conveyor.

A complete user interaction is:

1. The user opens the web UI and starts a voice session (or runs the
   `voice_to_robot.py` CLI).
2. The voice pipeline detects a wake word, then asks the user (TTS) for
   their **condition** ("오늘 컨디션은?") and the **severity** ("얼마나 드릴까요?").
3. The user answers by voice; STT (Whisper) transcribes each answer.
4. A keyword/category analyzer maps the answers to one of four condition
   categories and one of three intensity levels.
5. A combo rule engine produces a list of nut counts (the **order**),
   writes it to `cobot_voice/output/latest_order.json`, and mirrors progress
   to Firestore so the web UI can render state.
6. `voice_to_robot.py` calls `/task/start` on `task_manager_node`, which reads
   the same JSON file via its `FileOrderProvider`.
7. For each remaining nut in the order, the task manager calls
   `/perception/detect_once`, picks the best candidate of the requested class
   in the workspace, and sends a `/robot/pick_and_place` action goal.
8. `robot_control_node` runs the pick stages (approach → grasp → verify_grip
   → lift → transit → place → retreat → home), opens the RG2 gripper at the
   place pose, and asserts `/conveyor/place_ready`.
9. The conveyor node converts that **False → True** edge into one timed belt
   advance, then stops, ready for the next nut.
10. When the order is empty, the task manager publishes `done` on
    `/task/status` and `/task/result`; `firebase_status_bridge` mirrors that
    to Firestore so the web UI can show "completed".

---

## 2. End-to-End Flow

```
            ┌────────────────────┐
            │  Web UI / Start    │  React + Vite + Three.js
            │ (web_stt_firebase) │  Subscribes Firestore /robot_session/current
            └─────────┬──────────┘
                      │ HTTP POST /voice-audio/start
                      ▼
            ┌────────────────────┐
            │ web_voice_bridge_  │  cobot_voice.web_voice_bridge_server
            │       server       │  Drives VoiceWebDemo / voice_order_flow
            └─────────┬──────────┘
                      │
        ┌─────────────┴───────────────┐
        ▼                             ▼
┌──────────────────┐         ┌──────────────────┐
│  Wake word + STT │         │       TTS        │
│  (openwakeword + │         │   ElevenLabs or  │
│   OpenAI Whisper)│         │      spd-say     │
└────────┬─────────┘         └──────────────────┘
         │ recognized text
         ▼
┌────────────────────────────────────────────┐
│ Keyword / Condition / Severity analysis    │
│  - menu mode: regex against menu choices   │
│  - freeform mode: LLM (gpt-4o)             │
│  cobot_voice/keyword_extractor.py          │
│  cobot_voice/nut_recommendation.py         │
└────────┬───────────────────────────────────┘
         │ {categories, intensity, combo}
         ▼
┌────────────────────────────────────────────┐
│  Order Provider (file)                     │
│   latest_order.json   ◄── written here     │
│   Firestore /robot_session/current ◄── UI  │
└────────┬───────────────────────────────────┘
         │ /task/start (std_srvs/Trigger)
         ▼
┌────────────────────────────────────────────┐
│  ROS Task Manager  (task_manager_node)     │
│   loop:                                    │
│     /perception/detect_once  ──┐           │
│     target_selector            │           │
│     /robot/pick_and_place ◄────┘           │
│   /task/status, /task/result publishes     │
└────────┬─────────────────────────┬─────────┘
         │                         │ status/result
         ▼                         ▼
┌────────────────────────┐ ┌──────────────────┐
│ Perception /           │ │ firebase_status_ │
│ Object Detection       │ │ bridge → Firestore
│  realsense2_camera     │ │ robot_state field │
│  object_detection_node │ └──────────────────┘
│  perception_transform_ │
│  node                  │
└────────┬───────────────┘
         │ DetectedObjectArray (base-frame xyz, grasp yaw, mm sizes)
         ▼
┌────────────────────────────────────────────┐
│  Robot Arm + Gripper (robot_control_node)  │
│   pick_and_place stages:                   │
│     pre_grasp_width → approach → grasp     │
│     → verify_grip → lift → transit         │
│     → place → retreat → home               │
│   Doosan DSR_ROBOT2 (real|mock)            │
│   OnRobot RG2 via Modbus TCP (real|mock)   │
└────────┬─────────────────────┬─────────────┘
         │                     │ /conveyor/place_ready (Bool)
         │                     ▼
         │           ┌──────────────────────┐
         │           │ Conveyor Controller  │
         │           │ conveyor_serial_node │
         │           │ Arduino UNO @ /dev/  │
         │           │ ttyACM0, 115200 baud │
         │           └──────────────────────┘
         │ /task/result done
         ▼
       (loop back until order empty)
```

---

## 3. Runtime Components

This section lists every runtime component that ships in this repo. Empty
stub packages (`cobot_safety`, `cobot_policy`) are noted in §7 — they are
**not** runtime components today.

### 3.1 Web UI / Start button

- **Package/module**: `web_stt_firebase/` (Vite + React 19 + Three.js +
  Firebase 12). Lives at the workspace root with a `COLCON_IGNORE`.
- **Key files**: `src/App.tsx`, `src/components/`, `firebase.json`,
  `firestore.rules`, `package.json`.
- **Responsibility**: render the demo state (idle, listening, recommending,
  completed, error) and provide a start affordance that triggers the audio
  workflow on the host.
- **Input**: Firestore document `robot_session/current` (real-time listener).
- **Output**: HTTP POSTs to `web_voice_bridge_server` (see §3.2) on
  `127.0.0.1:8765`.

### 3.2 Web voice bridge server

- **Package/module**: `cobot_voice.web_voice_bridge_server` (executable
  `web_voice_bridge_server`).
- **Key files**: `cobot_voice/cobot_voice/web_voice_bridge_server.py`,
  `cobot_voice/cobot_voice/voice_web_demo.py`.
- **Responsibility**: a `ThreadingHTTPServer` that exposes
  `POST /voice-state`, `POST /voice-command`, `POST /voice-audio/start`,
  `POST /voice-audio/stop`, and `GET /health`. Drives `VoiceWebDemo`, which
  hosts the wake-word/STT loop and pushes Firestore updates.
- **Input**: HTTP requests from the web UI.
- **Output**: writes to Firestore via `firebase_bridge`; calls into the
  recommendation flow.

### 3.3 TTS

- **Package/module**: `cobot_voice.voice_order_flow.speak()` (in-process,
  not a node).
- **Key files**: `cobot_voice/cobot_voice/voice_order_flow.py`.
- **Responsibility**: speak Korean prompts and the final confirm message.
  Resolves provider via env vars: `COBOT_TTS_PROVIDER` (`auto` /
  `elevenlabs` / `spd-say`), `COBOT_TTS_ENABLED`. ElevenLabs uses
  `ELEVENLABS_API_KEY`, voice `pNInz6obpgDQGcFmaJgB` (Adam) by default,
  Korean language, MP3 played via `ffplay`. Falls back to `spd-say`.
- **Input**: prompt strings from `cobot_voice/config/question_flow.json` and
  computed combo text.
- **Output**: audio out of the host's default sound device.

### 3.4 STT

- **Package/module**: `cobot_voice.stt.STT` (in-process). Also a separate
  ROS node `voice_processing_node` exists but is legacy — see §7.
- **Key files**: `cobot_voice/cobot_voice/stt.py`,
  `cobot_voice/cobot_voice/mic_controller.py`,
  `cobot_voice/cobot_voice/wakeup_word.py`.
- **Responsibility**: 5-second microphone capture (16 kHz mono int16) →
  OpenAI Whisper (`whisper-1`) → text. Wake word is `openwakeword` running
  the bundled `hello_rokey_8332_32.tflite` model.
- **Input**: mic device (`MicConfig.device_index=6`, 48 kHz capture
  resampled to 16 kHz; **needs verification** per host).
- **Output**: transcribed Korean text.

### 3.5 Keyword extraction / recommendation

- **Package/module**: `cobot_voice` (in-process; no ROS interface).
- **Key files**:
  - `cobot_voice/cobot_voice/voice_order_flow.py` — top-level state machine
    (wake → ask state → STT → ask intensity → STT → combo → save + dispatch).
  - `cobot_voice/cobot_voice/keyword_extractor.py` — `StateAnalyzer` and
    `IntensityAnalyzer` (gpt-4o via langchain), `save_recommendation_order`.
  - `cobot_voice/cobot_voice/nut_recommendation.py` — keyword-based extraction,
    intensity counts, combo rules, Korean combo text.
  - `cobot_voice/config/keyword_categories.json` — category → keywords + nut.
  - `cobot_voice/config/nut_combo_rules.json` — intensity counts and the
    `per_category_intensity_count_capped_by_max_total` strategy.
  - `cobot_voice/config/question_flow.json` — Korean TTS prompts.
- **Responsibility**: turn STT text into a `(categories, intensity, combo)`
  recommendation. Two prompt modes are selected by
  `COBOT_VOICE_PROMPT_MODE` (see §7):
  - `freeform` (default) — LLM analyzers.
  - `menu` — explicit menu prompts and regex matching.
- **Input**: two STT transcripts (state + intensity).
- **Output**: an order dict written to `cobot_voice/output/latest_order.json`
  and to Firestore `robot_session/current`.

### 3.6 Order provider / database

- **Package/module**: `cobot_task_manager.order_provider`.
- **Key files**: `cobot_task_manager/cobot_task_manager/order_provider.py`.
- **Responsibility**: provide an `OrderBook` to `task_manager_node`. The
  selector is the `order_source` parameter:
  - `mock` — `MockOrderProvider`, hardcoded counts from
    `mock_order_almond/cashew/pistachio/walnut` parameters.
  - `db` — `DBOrderProvider`, calls `cobot_msgs/srv/GetNutOrder` on
    `/db/get_nut_order`. **The server side is not implemented in this repo;
    the client wiring is present but will time out unless someone provides
    a server.**
  - `file` — `FileOrderProvider`, reads `latest_order.json`. Refuses orders
    where `success=false` or `combo` is empty. Tracks `request_id` to avoid
    replaying the same order on a re-trigger.
- **Input**: the JSON file (file mode), the service (db mode), or the
  configured counts (mock mode).
- **Output**: an `OrderBook` (`{class: count}`) consumed by the task loop.

### 3.7 Task manager

- **Package/module**: `cobot_task_manager.task_manager_node`
  (executable `task_manager_node`).
- **Key files**:
  - `cobot_task_manager/cobot_task_manager/task_manager_node.py` — the loop.
  - `cobot_task_manager/cobot_task_manager/target_selector.py` —
    workspace + confidence + depth filtering.
  - `cobot_task_manager/cobot_task_manager/retry_policy.py` — detect/grasp
    miss handling (`max_detect_misses`, `max_grasp_failures`).
  - `cobot_task_manager/cobot_task_manager/pick_offsets.py` — loader for
    `cobot_config/config/pick_offsets.yaml`.
  - `cobot_task_manager/config/task_manager.yaml` — defaults.
- **Responsibility**: orchestrate the full pick loop. Calls `/robot/home`,
  then while the order has items: `detect_once` → `choose_target` →
  `pick_and_place`, applying per-class z offsets at goal time. Publishes
  `/task/status` and `/task/result` (`std_msgs/String`). Exposes
  `/task/start` so the worker can be triggered after `task_autostart:=false`
  startup.
- **Input**: order from §3.6; service `/perception/detect_once`; action
  `/robot/pick_and_place`; service `/robot/home`.
- **Output**: action goals; status/result topics.

### 3.8 Object detection

- **Package/module**: `cobot_object_detection.object_detection_node`
  (executable `object_detection_node`).
- **Key files**:
  - `cobot_object_detection/cobot_object_detection/object_detection_node.py`
  - `cobot_object_detection/cobot_object_detection/yolo_detector.py`
  - `cobot_object_detection/cobot_object_detection/detection_postprocess.py`
    (multi-frame fusion / clustering).
  - `cobot_object_detection/cobot_object_detection/model_paths.py` — resolves
    a configured path, then `ament` share `models/best.pt`, then the
    source-tree training output.
  - `cobot_object_detection/config/object_detection.yaml`.
  - Model weights:
    `experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt`
    (only `best.pt` files are checked in via `.gitignore` allow-listing).
- **Responsibility**: subscribe to RealSense color, run YOLOv8-OBB
  (Ultralytics), publish fused 2D OBB detections.
  `transform_valid` is left **false** here — the perception transform
  populates it.
- **Input**: `/camera/camera/color/image_raw` (sensor QoS).
- **Output**: `/detection/objects` (`cobot_msgs/DetectedObjectArray`).

### 3.9 Perception transform

- **Package/module**: `cobot_perception.perception_transform_node`
  (executable `perception_transform_node`). A `mock_perception_node` ships
  in the same package for hardware-free e2e testing.
- **Key files**:
  - `cobot_perception/cobot_perception/perception_transform_node.py`
  - `cobot_perception/cobot_perception/depth_filter.py` (median inside OBB)
  - `cobot_perception/cobot_perception/handeye_transform.py`
    (`load_gripper2camera`, `tcp_to_base2gripper`, `compose_base2camera`,
    `transform_camera_to_base`).
  - `cobot_perception/cobot_perception/grasp_pose_generator.py`
    (`yaw_from_obb`).
  - `cobot_perception/config/perception.yaml`.
- **Responsibility**: on each `/perception/detect_once` call, take the
  latest detections, look up median depth inside each OBB, lift to the
  camera frame via the pinhole model, transform to robot base frame using
  `T_gripper2camera.npy`, compute `grasp_yaw` from OBB theta, and emit
  physical OBB sizes (`short_axis_mm`, `long_axis_mm`). The TCP source is
  selectable: `fixed` (declared parameter) or `service` (calls
  `/robot/get_current_pose`). The default in
  `cobot_perception/config/perception.yaml` is `service`.
- **Input**: `/detection/objects`,
  `/camera/camera/aligned_depth_to_color/image_raw`,
  `/camera/camera/color/camera_info`, `T_gripper2camera.npy` (path required
  via `gripper2camera_npy`), and either `fixed_tcp_*` parameters or the
  pose service.
- **Output**: `/perception/detect_once` (`cobot_msgs/srv/DetectOnce`)
  responses with `transform_valid=true` populated entries.

### 3.10 Robot control

- **Package/module**: `cobot_robot_control.robot_control_node`
  (executable `robot_control_node`).
- **Key files**:
  - `cobot_robot_control/cobot_robot_control/robot_control_node.py` — the
    action server, home/stop services, pose passthrough, place_ready
    publisher. Uses two extra in-process helper nodes
    (`robot_action_helper`, `robot_pose_helper`) on dedicated multi-threaded
    executors so action traffic and pose lookups are not starved by
    DSR_ROBOT2 spin contention.
  - `cobot_robot_control/cobot_robot_control/motion_sequence.py` — stage
    sequence (`pre_grasp_width`, `approach`, `grasp`, `verify_grip`, `lift`,
    `transit`, `place`, `retreat`, `home`) and workspace guard.
  - `cobot_robot_control/cobot_robot_control/doosan_motion_client.py` — real
    DSR_ROBOT2 wrapper plus a mock implementation.
  - `cobot_robot_control/cobot_robot_control/pose_converter.py` — point/yaw
    and ZYZ ↔ Doosan posx conversions.
  - `cobot_robot_control/config/robot_control.yaml` (mock-default) and
    `robot_control.real.yaml` (real-hardware override).
- **Responsibility**: own the robot. Provides
  `/robot/pick_and_place` (action), `/robot/home`, `/robot/stop`,
  `/robot/get_current_pose` (services). Publishes
  `/conveyor/place_ready` at 10 Hz with edge updates.
- **Input**: action goals, services, and the underlying Doosan namespace
  (`dsr01` by default).
- **Output**: action result + feedback, place_ready topic, motion to the
  Doosan controller.

### 3.11 Gripper control

- **Package/module**: lives inside `cobot_robot_control`, not its own node.
- **Key files**: `cobot_robot_control/cobot_robot_control/gripper_controller.py`.
- **Responsibility**: pluggable backend (`Protocol`) with three
  implementations:
  - `MockGripperBackend` — no hardware, instant completion.
  - Modbus RG2 backend — Modbus TCP at `192.168.1.1:502`, `force_x10` and
    `max_width_x10` parameters (default 150 → 15 N, 1100 → 110 mm).
  - Tool DIO backend — interface stub only; **Not Implemented** today.
  - `wait_until_idle` two-phase wait (busy=True → busy=False) used by the
    `verify_grip` stage.
- **Input**: width/open/close calls from `motion_sequence`.
- **Output**: physical gripper motion + `is_grip_detected()` for verify.

### 3.12 Conveyor control

- **Package/module**: `conveyor_controller.conveyor_serial_node`
  (executable `conveyor_serial_node`). Firmware: `arduino/ConveyorControl_Program/`.
- **Key files**:
  - `conveyor_controller/conveyor_controller/conveyor_serial_node.py`
  - `conveyor_controller/launch/conveyor_controller.launch.py`
  - `conveyor_controller/config/conveyor_controller.yaml`
  - `conveyor_controller/README.md`
- **Responsibility**: subscribe to `/conveyor_cmd` (`std_msgs/String`,
  values `F1`–`F100`, `R1`–`R100`, `STOP`) and forward as newline-terminated
  serial lines. Subscribe to `/conveyor/place_ready` (`std_msgs/Bool`) and
  on each **False → True edge** send `auto_command` (default `R80`) for
  `auto_run_duration_sec` (default `5.0` s), then `STOP`. A second edge
  during an active run is logged and ignored.
- **Input**: `/conveyor_cmd`, `/conveyor/place_ready`, Arduino on
  `/dev/ttyACM0` at 115200 baud.
- **Output**: serial lines to Arduino; logs `[conveyor_start]` /
  `[conveyor_stop]` for verification.

### 3.13 Firebase / status bridge

- **Package/module**: `cobot_voice.firebase_bridge` (writer library) +
  `cobot_voice.firebase_status_bridge` (ROS node, executable
  `firebase_status_bridge`).
- **Key files**:
  - `cobot_voice/cobot_voice/firebase_bridge.py` — Firestore writer with a
    background queue; defines `DISPLAY_STATES` (voice flow) and
    `ROBOT_PROGRESS_STATES` (robot pipeline) vocabularies; theme tables.
  - `cobot_voice/cobot_voice/firebase_status_bridge.py` — ROS node that
    maps `/task/status`, `/task/result`, `/conveyor/place_ready` into a
    separate `robot_state` field on `robot_session/current`.
  - Service-account JSON in `secrets_4_firebase_config/`
    (`FIREBASE_SERVICE_ACCOUNT` env var). Gitignored.
- **Responsibility**: keep the web UI in sync with both the voice flow and
  the robot pipeline, in two independent fields, so neither blocks the
  other. If `firebase_admin` is missing or credentials fail, the writer
  silently no-ops and the ROS pipeline keeps running.
- **Input**: voice-flow calls (in-process), `/task/status`, `/task/result`,
  `/conveyor/place_ready`.
- **Output**: writes to Firestore document `robot_session/current`.

---

## 4. Data Contract

### 4.1 The order on disk — `cobot_voice/output/latest_order.json`

This is the file contract between the voice pipeline and the task manager.
It is produced by
`cobot_voice.keyword_extractor.build_latest_order_from_recommendation` and
consumed by `cobot_task_manager.order_provider.FileOrderProvider`.

```json
{
  "request_id": "20260507_214930",
  "recognized_text": "1 3",
  "categories": ["fatigue"],
  "intensity": "high",
  "combo": [
    {"nut": "cashew", "count": 3}
  ],
  "combo_text": "캐슈넛 세 개",
  "success": true
}
```

Field semantics:

| Field | Type | Purpose |
|---|---|---|
| `request_id` | string (`YYYYMMDD_HHMMSS`) | de-duplication key; `FileOrderProvider` refuses to replay the same id |
| `recognized_text` | string | concatenation of state + intensity transcripts (or text input) |
| `categories` | string array | resolved condition categories (one or more of the four below) |
| `intensity` | string | one of `low` / `normal` / `high` |
| `combo` | array of `{nut, count}` | the actual order — what the robot will pick |
| `combo_text` | string | Korean confirm phrasing for TTS / UI |
| `success` | bool | `true` only when both `categories` and `combo` are non-empty; `FileOrderProvider` refuses non-success orders |

The task manager only consumes `combo` (mapped to per-class counts) and
`request_id` (for idempotency). The other fields are for the web UI and
human inspection.

### 4.2 Internal `OrderBook`

`task_manager_node` works with an `OrderBook` (in
`order_provider.py`):

```python
OrderBook(
    counts={"almond": 2, "cashew": 2, "pistachio": 2, "walnut": 2},
    consecutive_detect_misses={...},
    consecutive_grasp_failures={...},
    skipped=set(),
)
```

A class is selected via `next_class(class_priority)` from
`task_manager.yaml`. `counts` is decremented on each successful pick and
classes are added to `skipped` after `max_detect_misses` or
`max_grasp_failures`.

> The schema you proposed (`{condition, severity, tasks: [...]}`) is a
> close synonym, but the **actual on-disk schema is the one above** —
> `categories` (plural, list), `intensity`, and `combo` (with `nut` and
> `count`). Rename if you want to align names, but the file format is what
> the runtime accepts today.

### 4.3 Valid values

**Condition categories** (from `cobot_voice/config/keyword_categories.json`):

| `category` | Korean label | Default nut |
|---|---|---|
| `fatigue` | 피로/회복 | `cashew` |
| `blood_sugar` | 혈당 관리 | `almond` |
| `diet` | 다이어트/체중 | `pistachio` |
| `focus` | 집중/두뇌 | `walnut` |

**Intensity levels** (from `cobot_voice/config/nut_combo_rules.json`):

| `intensity` | Per-category count |
|---|---|
| `low` | 1 |
| `normal` | 2 |
| `high` | 3 |

`max_total_count = 6`; when multiple categories overflow the cap, the
strategy `reduce_lower_priority_categories_first` is applied with order
`[fatigue, blood_sugar, diet, focus]`.

**Nut types** (used by every layer):

`almond`, `cashew`, `pistachio`, `walnut`.

The same four strings are the YOLO class names
(`cobot_object_detection/config/object_detection.yaml`), the action
`target_class` field, and the keys in `pick_offsets.yaml`. Korean/English
aliases for STT live in `cobot_config/config/object_aliases.yaml` and
`cobot_voice/cobot_voice/object_aliases.py`.

### 4.4 Action result codes — `cobot_msgs/action/PickAndPlace`

| code | meaning |
|---|---|
| 0 | ok |
| 1 | approach_fail |
| 2 | grasp_not_detected |
| 3 | motion_fail |
| 4 | safety_stop |
| 5 | workspace_violation |

Feedback `stage` strings: `pre_grasp_width`, `approach`, `grasp`,
`verify_grip`, `lift`, `transit`, `place`, `retreat`, `home`.

### 4.5 Firestore document — `robot_session/current`

Two independent fields are written:

- `display_state` ∈ `{idle, wake_detected, asking_state, listening_state,
  asking_intensity, listening_intensity, recommending, result_ready,
  dispatching, completed, error}` — driven by the voice flow.
- `robot_state` ∈ `{detecting, picking, placing, conveyor_moving, task_done,
  error}` — driven by `firebase_status_bridge` from `/task/status`,
  `/task/result`, and `/conveyor/place_ready` edges.

Other fields: `transcript`, `categories`, `intensity`, `combo`,
`combo_text`, `confirm_message`, `success`, `theme`, `error`,
`updated_at`, plus `robot_*`-prefixed fields for robot progress
(`robot_target_class`, `robot_last_result`, `robot_error`, …).

---

## 5. Hardware Architecture

### 5.1 Topology

```
                         Host PC (Ubuntu 22.04 + ROS 2 Humble)
   ┌───────────────────────────────────────────────────────────┐
   │  ROS 2 nodes (this repo)                                  │
   │  Web UI (Vite dev server, npm)                            │
   │  cobot_voice in-process: STT + TTS + LLM                  │
   └───────────────┬─────────────────────────────────┬─────────┘
                   │                                 │
        USB mic ───┤              ┌──────────────────┤
        Speakers ──┤              │ /dev/ttyACM0     │ USB-3
                   │              │                  │
                   │              ▼                  ▼
    ┌──────────────┴──────┐  ┌──────────┐    ┌─────────────────┐
    │ Doosan controller   │  │ Arduino  │    │ Intel RealSense │
    │ M0609, 192.168.1.100│  │ UNO +    │    │ D435/D455       │
    │ port 12345 (DSR)    │  │ stepper  │    │ color 1280×720  │
    └─────────────────────┘  │ driver   │    │ depth 848×480   │
                             └──────────┘    │ aligned_depth   │
                                             └─────────────────┘
                  192.168.1.0/24 LAN
                                             ┌─────────────────┐
                                             │ OnRobot RG2     │
                                             │ Modbus TCP      │
                                             │ 192.168.1.1:502 │
                                             └─────────────────┘
```

### 5.2 Components

- **Host PC**: Ubuntu 22.04, ROS 2 Humble. Runs every node in this repo,
  the web UI dev server, and the OpenAI / ElevenLabs HTTP clients. There
  are **no Dockerfiles, no docker-compose files, and no container manifests
  in this repo** — object detection, perception, and everything else run
  natively as ROS 2 nodes on the host. The OD model
  (`experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt`)
  is loaded directly by `object_detection_node`.
- **Intel RealSense camera**: launched via the upstream `realsense2_camera`
  package with `align_depth.enable:=true`, color `1280×720@30`, depth
  `848×480@30`. Frame ids from `/camera/camera/color/camera_info`. Fed by
  `cobot_bringup/launch/perception.launch.py`.
- **Doosan robot arm**: Doosan M0609 controller at `192.168.1.100:12345`.
  Brought up by the upstream `dsr_bringup2` package
  (`dsr_bringup2_rviz.launch.py` with `gui:=false`). Our
  `robot_control_node` runs **inside** the Doosan namespace (`dsr01`) so
  that the `DSR_ROBOT2` Python module's `DR_init` binding finds the right
  rclpy node.
- **OnRobot RG2 gripper**: Modbus TCP at `192.168.1.1:502`. Force defaults
  to `gripper_force_x10: 150` (15 N) and the max width to
  `gripper_open_width_x10: 1100` (110 mm).
- **Conveyor / Arduino**: Arduino UNO over USB at `/dev/ttyACM0`,
  115200 baud. Wiring (per `conveyor_controller/README.md`): D2=STEP,
  D3=DIR, D4=ENABLE, GND=driver signal ground. Sketch:
  `conveyor_controller/arduino/ConveyorControl_Program/`.
- **Network/IP assumptions**: the run manual lists `ping 192.168.1.100` and
  `ping 192.168.1.1` as pre-flight checks. The host needs to be on the same
  `192.168.1.0/24` subnet as the robot and the gripper.

### 5.3 Calibration & secrets

- `T_gripper2camera.npy` — required, path passed via the
  `gripper2camera_npy` parameter in `perception.yaml`. **There is no copy
  of this file in the repo** (intentional — calibration is host-specific).
  Without it, `perception_transform_node` raises on startup.
- `cobot_voice/resource/.env` — copy from
  `cobot_voice/resource/.env.example`. Required: `OPENAI_API_KEY`.
  Optional: `FIREBASE_SERVICE_ACCOUNT`, `ELEVENLABS_API_KEY`,
  `ELEVENLABS_VOICE_ID`, `COBOT_TTS_ENABLED`, `COBOT_TTS_PROVIDER`,
  `COBOT_VOICE_PROMPT_MODE`.
- `secrets_4_firebase_config/rokey-cobot2-firebase-adminsdk-*.json` —
  Firebase Admin service-account JSON. Gitignored. Path goes into
  `FIREBASE_SERVICE_ACCOUNT`.

---

## 6. Safety Design

This system can move a real robot at meaningful speeds. The safety design
is layered: each layer can be exercised independently of the next.

### 6.1 Mock / dry-run mode

The default configuration of `robot_control_node` is **mock**:
`motion_backend: mock`, `gripper_backend: mock`. In this mode the action
server completes the full pick stage sequence, publishes feedback, and
returns success without touching DSR_ROBOT2 or Modbus. `mock_perception_node`
returns a hardcoded 8-nut scene so the entire task loop can be exercised
with no camera and no robot.

`scripts/pick_one.py --dry-run` prints what the action *would* be sent
without dispatching it. `voice_to_robot.py --no-dispatch` saves
`latest_order.json` without calling `/task/start`.

### 6.2 Real mode

Real-hardware mode is **not** the default and must be opted into
explicitly:

1. `enable_dsr_bringup:=true` and `dsr_mode:=real` — turns on the Doosan
   stack.
2. `config_robot_control:=<share>/cobot_robot_control/config/robot_control.real.yaml` —
   sets `motion_backend: real` and `gripper_backend: modbus`. The mock-default
   YAML stays intact, so a missed override falls back to mock.

### 6.3 Robot workspace guard

Workspace bounds (mm in robot base frame) are enforced in **two**
independent places:

- `task_manager_node` — `target_selector.choose_target` filters
  `DetectedObjectArray` against `workspace_xmin/xmax/ymin/ymax/zmin/zmax_mm`
  before sending a goal. Current `task_manager.yaml` z bounds are tightened
  to `40 ≤ z ≤ 80` mm so depth-dropout outliers are rejected.
- `robot_control_node` — the action server's
  `motion_sequence.WorkspaceBounds.contains` check rejects any goal whose
  `grasp_xyz` or `return_xyz` falls outside the configured box (defaults
  `200..700 × -300..300 × 0..500` mm). Set `workspace_enabled: false` in
  `robot_control.yaml` to disable; left enabled by default. A violation
  short-circuits the action with `failure_code = 5` and never moves the
  robot. This second layer exists because **any** action client can call
  `/robot/pick_and_place` directly — task-manager filtering alone is not
  sufficient.

### 6.4 Gripper state confirmation

After closing on a nut, the `verify_grip` stage runs
`gripper_controller.wait_until_idle` (busy=True → busy=False — the
two-phase wait avoids reading a stale "idle" before the close has
started) and then queries `is_grip_detected()`. If the bit is not set,
the action returns `failure_code = 2` (`grasp_not_detected`) and aborts
**before** transit, preventing a phantom-grip transit that would drop
nothing onto the conveyor.

### 6.5 Place-ready trigger

`/conveyor/place_ready` (`std_msgs/Bool`) is the single integration point
between robot motion and conveyor motion.

- Published by `robot_control_node` at 10 Hz from `_publish_place_ready`.
- Goes **True** inside the `place` stage when the TCP is at the place y
  (within `place_y_margin_mm`) and the gripper has opened.
- Goes back to **False** at the start of `retreat`, on `pick_and_place`
  finish, on `/robot/stop`, and on motion errors.

### 6.6 Conveyor trigger condition

`conveyor_serial_node` advances the belt **only on a False→True edge**.
A held-True signal will not re-trigger; a second edge during an active
run is logged and ignored. The belt then runs `auto_command` (default
`R80`) for `auto_run_duration_sec` (default `5.0` s) and an internal timer
sends `STOP`. Distance is duration-based — see §7 for the limitation.

### 6.7 Recommended safety checks before real execution

Before turning on the robot:

- **Pendant**: AUTO mode + Servo On + status indicator white. A red
  indicator silently fails motion commands (return value reads success but
  the arm does not move). See `docs/03_run_manual.md` §12 for the full
  troubleshooting note.
- **Workspace clear**: physically verify the nuts are inside the configured
  workspace box and the return location and conveyor are unobstructed.
- **Calibration sanity**: run `pick_one.py --dry-run <class>` and check
  the printed `base_xyz` looks reasonable. Run
  `ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"`
  and confirm `success: true` plus a sane TCP.
- **First-pick z**: use `pick_one.py --z-override <z>` to find the sweet
  spot, then commit it via `cobot_config/config/pick_offsets.yaml`. Do not
  start a multi-pick session until at least one pick has succeeded.
- **Estop**: be ready to hit pendant E-stop or `ros2 service call
  /robot/stop std_srvs/srv/Trigger {}`.
- **Mock first**: when changing perception, motion, or task code, run the
  mock e2e (full_system with `enable_realsense:=false`,
  `enable_dsr_bringup:=false`, `gripper_backend` left at mock) before
  re-enabling hardware.

---

## 7. Current Known Gaps / Decisions

### 7.1 Explicit menu vs freeform voice prompt

- **Status**: both modes are implemented and selected at runtime by the
  `COBOT_VOICE_PROMPT_MODE` environment variable in
  `voice_order_flow._prompt_mode()`.
  - `freeform` (default) — uses LLM analyzers (`StateAnalyzer`,
    `IntensityAnalyzer`, gpt-4o) on the STT text.
  - `menu` — narrates an explicit numbered menu ("1번 피로, 2번 혈당, …",
    "1번 약하게, 2번 보통, 3번 많이") and matches the answer with a regex
    against numeric and Korean-keyword sets. Single-digit ASCII tokens are
    matched against whitespace-separated tokens to avoid accidentally
    hitting "12". Bare Korean numerals (일/이/삼/사) are intentionally not
    matched because they collide with common particles. On a parse miss,
    one retry is offered before bailing.
- The voice flow falls back to LLM analysis if the menu match misses on
  the retry as well.

### 7.2 Conveyor movement semantics

- **Status**: implemented as a **duration-based one-shot** triggered by
  the False→True edge of `/conveyor/place_ready`. One edge → one
  `auto_command` (default `R80`) for `auto_run_duration_sec` (default
  `5.0` s) → `STOP`. Held-True does not re-trigger.
- **Limitation** (called out in `conveyor_controller/README.md`): distance
  is approximate, not deterministic. Step-mode firmware (`S<N>` command +
  ack) is documented as **future work / TODO** and intentionally out of
  scope.

### 7.3 Firestore / web robot progress bridge

- **Status**: implemented by `firebase_status_bridge`
  (`cobot_voice.firebase_status_bridge`, executable
  `firebase_status_bridge`), launched by default from
  `cobot_bringup/launch/host_system.launch.py` (toggle:
  `enable_firebase_status_bridge`, default `true`). It mirrors
  `/task/status`, `/task/result`, and `/conveyor/place_ready` False→True
  edges into the `robot_state` field on `robot_session/current`, leaving
  the voice-flow `display_state` field untouched.
- **Limitation** (called out in the module docstring): the action server
  does not expose per-stage progress externally, so `placing` is inferred
  from the same edge that fires `conveyor_moving`. Both states are
  emitted back-to-back through the writer queue.
- **Failure mode**: if `firebase_admin` or credentials are missing, the
  writer flips an internal flag and silently no-ops. The robot pipeline is
  unaffected.

### 7.4 `command_parser_node` status

- **Status**: removed. The dead code (`command_parser_node`,
  `firebase_state_bridge`) was deleted as part of the voice→robot
  integration cleanup. There is no `/voice/text` consumer in this repo
  today.
- The `voice_processing_node` executable (`voice_processing` entry point)
  still exists in `cobot_voice/setup.py` and publishes `/voice/text` and
  `/voice/status`, but **no in-tree node subscribes to those topics**. The
  production voice path is `voice_to_robot.py` →
  `voice_order_flow.run_recommendation_flow` → `task_manager_dispatcher.dispatch_to_task_manager`,
  which is in-process and bypasses ROS topics for the voice→order step.
  Treat `voice_processing_node` as legacy.

### 7.5 Per-class Z-offset config

- **Status**: single source of truth is
  `cobot_config/config/pick_offsets.yaml`:
  ```yaml
  per_class_z_offset_mm:
    almond: 0.0
    cashew: 0.0
    pistachio: 0.0
    walnut: -1.0
  ```
- **Loader**: `cobot_task_manager.pick_offsets.load_pick_offsets` resolves
  in this order: explicit path parameter → `COBOT_PICK_OFFSETS_PATH` env
  var → ament-share lookup → source-tree fallback → built-in defaults.
- **Apply point**: applied **only at the pick stage** (added to
  `goal.grasp_xyz.z`), not at place / return.
- **Note for operators**: `scripts/pick_one.py` and `scripts/pick_all.py`
  also have a `PER_CLASS_Z_OFFSET` dict at the top of each file.
  `scripts/pick_one.py` currently has all zeros, so script-mode picks do
  not pick up `walnut: -1.0` automatically. **Needs verification** whether
  the scripts should be migrated to read the YAML — not changed in this
  pass because the request was to document, not modify code.

### 7.6 Other gaps worth knowing

- **`cobot_safety` and `cobot_policy`** — both packages exist with empty
  `*.py` files. `setup.py` exposes `safety_manager` and `policy_selector`
  entry points, but the modules contain no code. **Not Implemented**; not
  referenced by any launch file.
- **`/db/get_nut_order`** — `cobot_msgs/srv/GetNutOrder` is defined and
  `DBOrderProvider` is wired up, but **the service server is not
  implemented in this repo**. Setting `order_source:=db` will time out.
- **`cobot_config/config/{slot_poses,policy_config,workspace}.yaml`** —
  defined but not loaded by any runtime node. The actual workspace bounds
  live in the `task_manager.yaml` and `robot_control.yaml` parameter
  blocks; the config-package YAMLs are **currently unused**. **Needs
  verification** whether they should be removed or wired in.
- **`cobot_bringup/config/params.yaml`** — system params (ROS_DOMAIN_ID,
  RMW, robot host/port). **Not loaded** by any of the launch files in
  `cobot_bringup/launch/`. Treat as reference until wired in.
- **Mic device index** — hard-coded to `6` in
  `cobot_voice.mic_controller.MicConfig`. **Needs verification** per host;
  there is no env var override today.
- **Workspace bounds duplicated** in `task_manager.yaml` and
  `robot_control.yaml`. They must be kept in sync manually; no
  cross-package validation today.

---

## Appendix — Files to read for deeper context

For the runtime behavior described above:

- Top-level launch: `cobot_bringup/launch/full_system.launch.py`,
  `host_system.launch.py`, `perception.launch.py`, `robot.launch.py`.
- Task loop: `cobot_task_manager/cobot_task_manager/task_manager_node.py`
  (the `_run` method) and `target_selector.py`, `retry_policy.py`.
- Action server + helper-node rationale:
  `cobot_robot_control/cobot_robot_control/robot_control_node.py`
  (lines 175–260).
- Pick stages + workspace guard:
  `cobot_robot_control/cobot_robot_control/motion_sequence.py`.
- Detection → base-frame transform:
  `cobot_perception/cobot_perception/perception_transform_node.py`
  (`_handle_detect_once`).
- Voice state machine:
  `cobot_voice/cobot_voice/voice_order_flow.py`
  (`run_recommendation_flow`, `_prompt_mode`, `_match_menu_choice`).
- Order JSON shape:
  `cobot_voice/cobot_voice/keyword_extractor.py`
  (`build_latest_order_from_recommendation`, `normalize_combo`).
- Conveyor edge semantics: `conveyor_controller/README.md`.

The companion run-order document is `docs/03_run_manual.md`. The
pre-flight test checklist is `docs/04_validation_checklist.md`.
