# Validation Checklist

A pre-flight checklist for the integrated cobot nut-picking system.
Walk through it top to bottom before each real-hardware session, and
again whenever you edit perception, motion, calibration, or
task-manager code.

## Index

1. Documentation Scope
2. Static Checks
3. ROS Graph Checks
4. Voice Pipeline Checks
5. Task Manager Checks
6. Perception Checks
7. Robot / Gripper Dry-Run Checks
8. Conveyor Checks
9. Real-Hardware Preflight
10. Acceptance Criteria

## Document set

- `docs/01_system_architecture.md` — what the system does and why.
- `docs/02_ros_node_architecture.md` — node-level interface reference,
  state machine, and debugging commands.
- `docs/03_run_manual.md` — operational run order, mock and real.
- `docs/04_validation_checklist.md` — **this file**.
- `docs/cleanup_deletion_proposal.md` and
  `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` — cleanup records.
  The static-check section §2 explicitly excludes `_archive_cleanup/`
  from grep scopes; treat it as inactive.

> **Naming convention used throughout.** The Doosan-side **node names**
> are namespaced (`/dsr01/robot_control_node`,
> `/dsr01/robot_action_helper`, `/dsr01/robot_pose_helper`), but the
> **services and actions** are absolute (`/robot/pick_and_place`,
> `/robot/home`, `/robot/stop`, `/robot/get_current_pose`). They are
> declared with a leading `/` in `robot_control.yaml` and called with
> the same absolute names from `task_manager.yaml`. See
> `docs/02_ros_node_architecture.md` §3 for the full interface table.

---

## 1. Documentation Scope

This checklist verifies that the system is **safe and ready to operate**
end-to-end:

- All packages build, all launch files load, all interfaces exist.
- The ROS graph contains the expected nodes, topics, services, and
  actions.
- The voice pipeline produces a valid order, the task manager consumes
  it, perception returns transformed candidates, and the action server
  accepts goals — all in **mock mode** before any real motion.
- A real-hardware preflight (network, USB, E-stop, workspace) passes.
- A single-nut real pick succeeds before a multi-nut run.

The checklist does **not** cover model training, hand-eye calibration,
or web/Firebase project setup.

How to use:

- Mark each item ✅ pass / ❌ fail. Do not skip ❌ items.
- Log evidence in your own session notebook (timestamps, terminal
  excerpts).
- §10 contains the exit criteria — the system is "ready" only when
  every item there passes.

---

## 2. Static Checks

### 2.1 Packages build cleanly

```bash
cd ~/cobot2_ws
colcon build --symlink-install
source install/setup.bash
```

Expected: every package finishes with `Finished <<<`. No `Failed <<<`,
no missing-dependency errors.

Run unit tests where present:

```bash
colcon test --packages-select cobot_object_detection cobot_robot_control cobot_task_manager
colcon test-result --verbose
```

Expected test files (already in the repo):

- `cobot_object_detection/test/test_model_paths.py`
- `cobot_robot_control/test/test_motion_sequence_workspace.py`
- `cobot_task_manager/test/test_order_provider_db.py`
- `cobot_task_manager/test/test_pick_offsets.py`
- Pure-Python tests in `cobot_voice/` (run with `pytest` directly):
  ```bash
  cd ~/cobot2_ws/cobot_voice
  python3 -m pytest -q
  ```
  These exercise `test_env.py`, `test_firebase_bridge.py`,
  `test_firebase_status_bridge.py`, `test_nut_recommendation.py`,
  `test_question_flow.py`, `test_web_voice_bridge_server.py`.

### 2.2 Launch files exist and are syntactically valid

```bash
# Composite + sub-launches
ls $(ros2 pkg prefix cobot_bringup)/share/cobot_bringup/launch/
# Expected:
#   full_system.launch.py
#   host_system.launch.py
#   perception.launch.py
#   robot.launch.py

# Per-package single-node launches
ls $(ros2 pkg prefix cobot_object_detection)/share/cobot_object_detection/launch/
ls $(ros2 pkg prefix cobot_perception)/share/cobot_perception/launch/
ls $(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/launch/
ls $(ros2 pkg prefix cobot_task_manager)/share/cobot_task_manager/launch/
ls $(ros2 pkg prefix conveyor_controller)/share/conveyor_controller/launch/
```

Quick syntax check (does not actually start nodes — `--show-args`
parses the description):

```bash
ros2 launch cobot_bringup full_system.launch.py --show-args
ros2 launch cobot_bringup host_system.launch.py --show-args
ros2 launch cobot_bringup perception.launch.py --show-args
ros2 launch cobot_bringup robot.launch.py --show-args
ros2 launch conveyor_controller conveyor_controller.launch.py --show-args
```

Expected: a list of declared arguments with defaults, no Python
exceptions.

### 2.3 Config files load

```bash
# Installed YAMLs land here
find $(ros2 pkg prefix cobot_object_detection)/share/cobot_object_detection/config -name '*.yaml'
find $(ros2 pkg prefix cobot_perception)/share/cobot_perception/config -name '*.yaml'
find $(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config -name '*.yaml'
find $(ros2 pkg prefix cobot_task_manager)/share/cobot_task_manager/config -name '*.yaml'
find $(ros2 pkg prefix conveyor_controller)/share/conveyor_controller/config -name '*.yaml'

# Voice JSON
find $(ros2 pkg prefix cobot_voice)/share/cobot_voice/config -name '*.json'
```

Expected at least:

- `cobot_object_detection/.../object_detection.yaml`
- `cobot_perception/.../perception.yaml`
- `cobot_robot_control/.../robot_control.yaml` and `robot_control.real.yaml`
- `cobot_task_manager/.../task_manager.yaml`
- `conveyor_controller/.../conveyor_controller.yaml`
- `cobot_voice/.../keyword_categories.json`,
  `nut_combo_rules.json`, `question_flow.json`

Spot-check parseability:

```bash
python3 -c "import yaml; yaml.safe_load(open('$(ros2 pkg prefix cobot_task_manager)/share/cobot_task_manager/config/task_manager.yaml'))"
python3 -c "import json; json.load(open('$(ros2 pkg prefix cobot_voice)/share/cobot_voice/config/keyword_categories.json'))"
```

Expected: silent success.

### 2.4 Message / service / action interfaces present

```bash
ros2 interface show cobot_msgs/msg/DetectedObject
ros2 interface show cobot_msgs/msg/DetectedObjectArray
ros2 interface show cobot_msgs/srv/DetectOnce
ros2 interface show cobot_msgs/srv/GetCurrentPose
ros2 interface show cobot_msgs/srv/GetNutOrder
ros2 interface show cobot_msgs/action/PickAndPlace
```

Expected: each command prints the interface body without a
`Could not find` error.

### 2.5 No stale `command_parser_node` references

`command_parser_node` and `firebase_state_bridge` were removed during
the voice→robot integration cleanup. They should not appear anywhere
in the runtime tree.

```bash
grep -RnE "command_parser_node|firebase_state_bridge" \
    cobot_msgs cobot_bringup cobot_object_detection cobot_perception \
    cobot_robot_control cobot_safety cobot_task_manager cobot_voice \
    conveyor_controller scripts 2>/dev/null
```

Expected: **no output**. (Hits inside `docs/` historical change-logs are
allowed and do not need to be cleaned.)

---

## 3. ROS Graph Checks

Run after launching the full system in mock mode (§5 of the run manual).

### 3.1 Nodes

```bash
ros2 node list
```

Expected entries (mock mode, `enable_realsense:=false`,
`enable_dsr_bringup:=false`, `enable_firebase_status_bridge:=true`):

- `/object_detection_node`
- `/perception_transform_node`
- `/dsr01/robot_control_node`
- `/dsr01/robot_action_helper`
- `/dsr01/robot_pose_helper`
- `/task_manager_node`
- `/firebase_status_bridge` (only if enabled)

In real mode also expect `/camera/camera` (RealSense) and the
`/dsr01/dsr_*` controllers from `dsr_bringup2`.

If you ran with `enable_firebase_status_bridge:=false`, that node
should be **absent**.

### 3.2 Topics

```bash
ros2 topic list -t
```

Required:

| Topic | Type |
|---|---|
| `/detection/objects` | `cobot_msgs/msg/DetectedObjectArray` |
| `/conveyor/place_ready` | `std_msgs/msg/Bool` |
| `/task/status` | `std_msgs/msg/String` |
| `/task/result` | `std_msgs/msg/String` |

In real mode add:

- `/camera/camera/color/image_raw`
- `/camera/camera/aligned_depth_to_color/image_raw`
- `/camera/camera/color/camera_info`

If you run the conveyor:

- `/conveyor_cmd` (`std_msgs/msg/String`)

### 3.3 Services

```bash
ros2 service list -t | grep -E "task|robot|perception|conveyor"
```

Required:

- `/task/start                std_srvs/srv/Trigger`
- `/perception/detect_once    cobot_msgs/srv/DetectOnce`
- `/robot/home                std_srvs/srv/Trigger`
- `/robot/stop                std_srvs/srv/Trigger`
- `/robot/get_current_pose    cobot_msgs/srv/GetCurrentPose`

The robot services use **absolute** names because they are declared
with a leading `/` in `robot_control.yaml`; the host helper node
(`/dsr01/robot_action_helper` for home/stop, `/dsr01/robot_pose_helper`
for the pose service) lives in the `dsr01` namespace, but the service
names themselves do not get prefixed. The Doosan-native upstream
service is at `/dsr01/system/get_current_pose` (provided by
`dsr_bringup2`).

### 3.4 Actions

```bash
ros2 action list -t
```

Required:

- `/robot/pick_and_place    cobot_msgs/action/PickAndPlace`

Verify the type:

```bash
ros2 action info /robot/pick_and_place -t
```

Expected: server `/dsr01/robot_action_helper` (a node — that one *is*
namespaced); clients include `/task_manager_node` once a task has been
started.

---

## 4. Voice Pipeline Checks

Run with the full system launched in **mock + file mode** (so the
recommendation actually flows into the task manager):

```bash
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false order_source:=file file_order_path:=/home/aes/cobot2_ws/cobot_voice/output/latest_order.json
```

Verify the T1 task-manager log contains:

```
FileOrderProvider reading /home/aes/cobot2_ws/cobot_voice/output/latest_order.json
```

### 4.1 TTS prompt

```bash
~/cobot2_ws/scripts/voice_to_robot.py --debug
```

Expected on the first prompt step:

- Console line `[TTS] 샤갈! 맞춤 견과류 콤보를 준비해드릴게요.`
- Audible playback if `COBOT_TTS_ENABLED=1` (default) **and**
  `ffplay` (ElevenLabs) or `spd-say` (fallback) is installed.

If `COBOT_TTS_PROVIDER=elevenlabs` is set, expect an HTTP request to
`api.elevenlabs.io`. Failures are logged but do not break the flow.

### 4.2 STT returns text

Two ways to verify:

- **Bypass STT** (fastest sanity check):
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이"
  ```
  Expected stdout:
  ```
  recognized_text : '피곤하고 집중이 안 돼서 많이'
  combo           : [{'nut': 'cashew', 'count': 3}, {'nut': 'walnut', 'count': 3}]
  success         : True
  dispatched      : True
  ```

- **Real Whisper** (microphone path):
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py
  ```
  Expected: console prints `STT 결과: <Korean text>` after each 5 s
  recording window. Failures usually surface as Whisper API exceptions.

### 4.3 Keyword extraction returns condition + severity

After step 4.2, inspect the JSON:

```bash
cat ~/cobot2_ws/cobot_voice/output/latest_order.json
```

Required fields and constraints:

| Field | Validation |
|---|---|
| `request_id` | Non-empty string, format `YYYYMMDD_HHMMSS` |
| `recognized_text` | Non-empty when STT/text succeeded |
| `categories` | Non-empty array; each value ∈ `{fatigue, blood_sugar, diet, focus}` |
| `intensity` | `low` / `normal` / `high` |
| `combo` | Non-empty array of `{nut, count}` with `nut ∈ {almond, cashew, pistachio, walnut}` and `count ≥ 1` |
| `combo_text` | Non-empty Korean string |
| `success` | `true` |

If `success` is `false` or `combo` is empty, the order will be **rejected
by `FileOrderProvider`** and the task manager will not pick anything
(this is intentional).

### 4.4 Order provider returns nut counts

In mock mode (no voice), this is verified by hardcoded counts in
`task_manager.yaml` (`mock_order_*`). Trigger and watch:

```bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
ros2 topic echo /task/status
```

In file mode, this is verified by the `/task/status` log lines after
`/task/start`:

```
[state] init
[state] detect
[state] select_target cashew
[state] pick_and_place cashew
...
```

The class names appearing here must match the JSON's `combo`.

> The `db` mode (`/db/get_nut_order`) is **Not Implemented** in this
> repo. Setting `order_source:=db` will time out — skip this check.

### 4.5 `latest_order.json` exists and is valid

```bash
ls -la ~/cobot2_ws/cobot_voice/output/latest_order.json
python3 -c "
import json
d = json.load(open('/home/aes/cobot2_ws/cobot_voice/output/latest_order.json'))
assert d.get('success') is True, 'success must be true'
assert d.get('combo'), 'combo empty'
assert all(c['nut'] in {'almond','cashew','pistachio','walnut'} for c in d['combo']), 'bad nut name'
assert all(int(c['count']) >= 1 for c in d['combo']), 'bad count'
print('ok')
"
```

Expected: `ok`.

---

## 5. Task Manager Checks

### 5.1 `/task/start` available

```bash
ros2 service list | grep ^/task/start$
ros2 service type /task/start            # std_srvs/srv/Trigger
```

Expected: present, type matches.

### 5.2 Fake task accepted

In mock mode (or file mode after a successful voice run):

```bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

Expected:

- First call: `success=True message='task started'`.
- Subsequent call **while the loop is still running**:
  `success=False message='task already running'`.

### 5.3 Invalid task rejected

In **file mode**, simulate a bad order and confirm the worker refuses
it. The `FileOrderProvider` rejects when `success=false` or when the
combo is empty, and tracks `request_id` to refuse replays of the same
order.

```bash
# Stash the real one
cp ~/cobot2_ws/cobot_voice/output/latest_order.json /tmp/good_order.json

# Write a deliberately-failing order
python3 - <<'PY'
import json, datetime
out = {
    "request_id": datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_invalid",
    "recognized_text": "",
    "categories": [],
    "intensity": "normal",
    "combo": [],
    "combo_text": "",
    "success": False,
}
json.dump(out, open("/home/aes/cobot2_ws/cobot_voice/output/latest_order.json", "w"), ensure_ascii=False, indent=2)
print("wrote invalid order")
PY

ros2 service call /task/start std_srvs/srv/Trigger "{}"
# Expected: task starts, then aborts almost immediately with
# /task/result: failure order_fetch_failed   (or similar refusal)
ros2 topic echo /task/result --once

# Restore the good order before continuing
cp /tmp/good_order.json ~/cobot2_ws/cobot_voice/output/latest_order.json
```

Expected: the order is refused at fetch time with a `failure
order_fetch_failed` (or comparable) message on `/task/result`. The
robot does not move.

> **Needs verification**: the exact failure string emitted depends on
> the `FileOrderProvider` exception path. Treat the absence of any
> `[state] pick_and_place ...` line as the success signal for this
> rejection check.

### 5.4 State transitions visible

```bash
ros2 topic echo /task/status
# Trigger from another terminal
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

Expected sequence (success path):

```
init
detect
select_target <class>
pick_and_place <class>
detect
...
done
```

Failure paths (must also be observed for completeness):

```
aborted home_failed
aborted order_fetch_failed
aborted action_failure
aborted failure_code=<N>
safety_stop
```

### 5.5 Task result published

```bash
ros2 topic echo /task/result --once
```

Expected: a single line ending in `success counts={...} skipped=[...]`
or `failure <reason>`. The result is published exactly **once** per
task run.

---

## 6. Perception Checks

### 6.1 Detection node running

```bash
ros2 node list | grep object_detection_node
ros2 node info /object_detection_node
```

Expected: exists; subscribed to `/camera/camera/color/image_raw`,
publishing `/detection/objects`. The boot log line
`Loading YOLO-OBB model: <path>` confirms the model resolved.

If you are running fully mock (no camera), substitute
`mock_perception_node`:

```bash
ros2 run cobot_perception mock_perception_node
ros2 node list | grep mock_perception_node
```

### 6.2 `detect_once` service works

```bash
ros2 service call /perception/detect_once cobot_msgs/srv/DetectOnce "{}"
```

Expected (real perception with a populated scene):

- `success: true`
- `message: "transformed K/N detections"` where `K, N ≥ 0`.
- `objects.objects` list (possibly empty if nothing is in the workspace).

Expected failure modes (all return `success: false`):

- `"no detection received yet"` — `object_detection_node` not running
  or no color frames yet.
- `"no depth frame received yet"` — depth alignment missing.
- `"no camera_info received yet"` — intrinsics not yet received.
- `"tcp source error: ..."` — `tcp_source: service` and
  `/robot/get_current_pose` is not responding.

If you used `mock_perception_node`, expect the hardcoded 8-object
scene with all entries `transform_valid=true`.

### 6.3 Target has valid `class_name`

For each entry returned by `detect_once`:

- `class_name ∈ {almond, cashew, pistachio, walnut}` — same vocabulary
  as `cobot_object_detection/config/object_detection.yaml`'s
  `class_names`.

Quick filter check in the response — every `objects.objects[*].class_name`
must be in that set. The proposed schema's "nut_type" name corresponds
to `class_name` in the actual `cobot_msgs/DetectedObject.msg`.

### 6.4 Target has valid base coordinate / `transform_valid`

For every entry the task manager will accept (i.e. anything passed to
`target_selector.choose_target`):

- `transform_valid: true` — the transform was successfully applied.
- `base_xyz.x`, `base_xyz.y`, `base_xyz.z` — non-zero, finite floats in
  millimeters in the robot base frame.
- `grasp_yaw` — finite radian value.
- `short_axis_mm`, `long_axis_mm` — positive floats matching real nut
  dimensions (rough range: 5–25 mm).

Spot-check sanity: a populated workspace scene should have multiple
entries with `transform_valid=true` and `base_xyz` values inside the
`task_manager.yaml` workspace box (`x ∈ [200, 700]`,
`y ∈ [-300, 300]`, `z ∈ [40, 80]`).

If every entry comes back `transform_valid: false`, see Run Manual
§12.6.

---

## 7. Robot / Gripper Dry-Run Checks

Run these in **mock mode** (`motion_backend: mock`,
`gripper_backend: mock` — the default `robot_control.yaml`).

### 7.1 Pick action receives target

```bash
ros2 action info /robot/pick_and_place
```

Expected: server node `/dsr01/robot_action_helper`; client includes
`/task_manager_node` once a task has been started.

Send a dry-run target via the helper script:

```bash
~/cobot2_ws/scripts/pick_one.py cashew --dry-run
```

Expected: prints the resolved goal (`base_xyz`, `grasp_yaw`,
`short_axis_mm`, computed pre-grasp width) and exits **without**
sending an action goal.

### 7.2 Motion stages log correctly

Without `--dry-run`, the action server walks all stages. Watch the
launch terminal:

```bash
~/cobot2_ws/scripts/pick_one.py cashew
```

Expected stage feedback (mock backend completes each instantly):

```
[stage] pre_grasp_width
[stage] approach
[stage] grasp
[stage] verify_grip
[stage] lift
[stage] transit
[stage] place
[stage] retreat
[stage] home
```

Action result: `success: True, failure_code: 0`.

### 7.3 Gripper close/open sequence logs correctly

In mock mode, the gripper backend prints debug logs from
`gripper_controller.py`. Look for:

- The `pre_grasp_width` stage triggers `move_to(...)` and waits.
- The `grasp` stage triggers `close()` and `wait_until_idle`.
- `verify_grip` calls `is_grip_detected()` (mock returns True).
- The `place` stage triggers `open()` and `wait_until_idle`.

If `verify_grip` fails (returns False on the mock) — that should not
happen unless code has changed; mock returns True by default. Treat a
failure here as a code regression.

### 7.4 No real movement occurs in dry-run

Check that the **default** YAML is in use. The launch terminal should
log:

```
Using MOCK motion backend ...
Using MOCK gripper backend ...
```

…**not**:

```
Initializing DSR_ROBOT2 ...
Initializing Modbus RG2 ...
```

If you see the latter, the **real** YAML was loaded by mistake — stop
and re-launch. The robot will move on the next pick.

Additionally, with `enable_dsr_bringup:=false`, no `dsr_*` topics
should appear:

```bash
ros2 topic list | grep ^/dsr01/ || echo "no /dsr01/ topics — expected for mock-only"
```

(Some `/dsr01/...` services exist because `robot_control_node` lives in
that namespace, but **motor commands** are stubbed.)

---

## 8. Conveyor Checks

Launch only the conveyor (real Arduino on `/dev/ttyACM0`):

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py
```

Expected boot log:

```
Connected to Arduino serial port /dev/ttyACM0 at 115200 baud
Listening on /conveyor_cmd for commands: F<1-100>, R<1-100>, STOP
Place-ready trigger: one False->True edge on /conveyor/place_ready = one movement
                     (command=R80, duration=5.00s, then STOP). Distance is approximate;
                     exact distance requires firmware step mode.
```

### 8.1 `place_ready` edge triggers exactly once

In one terminal, watch the conveyor log. In another:

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
```

Expected immediately:

```
[conveyor_start] command=R80 duration=5.00s (place_ready edge)
```

After `auto_run_duration_sec` (default `5.0` s):

```
[conveyor_stop]  command was R80, duration=5.00s elapsed
```

Send `false` to reset the edge tracker, then `true` again to verify
the **next** edge fires another single advance:

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: false}"
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
```

Expected: another `[conveyor_start] ... [conveyor_stop]` pair.

### 8.2 Conveyor stops after expected duration

Time the gap between `[conveyor_start]` and `[conveyor_stop]` log
lines — should match `auto_run_duration_sec` within ~100 ms. The
`STOP` is sent by an internal one-shot `create_timer` callback.

If you change the duration live:

```bash
ros2 param set /conveyor_serial_node auto_run_duration_sec 2.0
```

…the next edge should produce a 2-second run.

### 8.3 No repeated trigger without a new edge

Send `true` again **without** an intermediate `false`:

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"   # second message
```

Expected: only the first message produces a start log; the second is a
no-op (because `_last_place_ready` is already `True`). Confirm by
counting `[conveyor_start]` lines.

A `true` that arrives **while a previous timed run is still active**
should be logged and ignored:

```
Ignoring place_ready trigger while conveyor auto-run is active
```

(That requires sending `false → true → true` quickly, all within the
5 s window.)

---

## 9. Real-Hardware Preflight

Do not skip any of these. Each ❌ here means **stop**, no real motion.

The hardware-and-network items are also enumerated in
`docs/03_run_manual.md` §2.4 / §7.1 — re-check both, but the canonical
go/no-go gate is this section.

- [ ] **Robot ping**: `ping -c 3 192.168.1.100` returns 0 % loss.
- [ ] **Gripper ping**: `ping -c 3 192.168.1.1` returns 0 % loss.
- [ ] **RealSense USB**: `lsusb | grep -i realsense` shows the device.
- [ ] **RealSense stream alive**:
  `ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw` shows
  ~30 Hz after the camera launch reaches `RealSense Node Is Up!`.
- [ ] **Conveyor serial**: `ls /dev/ttyACM*` lists the port; current
  user is in the `dialout` group (`groups | grep dialout`); the
  conveyor launch reaches `Connected to Arduino serial port ...`.
- [ ] **Calibration files**: `gripper2camera_npy` parameter in
  `cobot_perception/config/perception.yaml` points at an existing
  `T_gripper2camera.npy` (4×4 array). The perception startup log
  includes `Loaded gripper2camera from <path>`.
- [ ] **Pendant**: AUTO mode + Servo On + status indicator **white**.
  (Red indicator → motion API silently no-ops.)
- [ ] **E-stop within reach** of the operator.
- [ ] **Workspace clear**: no fingers, cables, or tooling in the
  approach / transit / return paths; conveyor belt clear.
- [ ] **Pick offsets up to date**:
  `cat ~/cobot2_ws/cobot_config/config/pick_offsets.yaml` matches the
  most recent successful tuning.
- [ ] **Real config selected**:
  `config_robot_control:=...robot_control.real.yaml` is on the launch
  command line; the launch terminal shows
  `Initializing DSR_ROBOT2 ...` and
  `Initializing Modbus RG2 at 192.168.1.1:502`.
- [ ] **One-nut dry-run first**:
  `~/cobot2_ws/scripts/pick_one.py <class> --dry-run` returns sensible
  base coordinates **before** any non-dry-run command is issued (see
  `docs/03_run_manual.md` §8).
- [ ] **Mock dry-run passed today** — every item in §7 ticked off in
  the same session.

---

## 10. Acceptance Criteria

The system is "ready for operation" only when **all** of the following
pass in the same session:

- [ ] **Static checks (§2)** — `colcon build` is clean,
  `colcon test` passes, all interfaces resolve, no
  `command_parser_node` / `firebase_state_bridge` references remain
  outside `docs/`.
- [ ] **ROS graph (§3)** — every required node, topic, service, and
  action listed in §3 is present.
- [ ] **Voice pipeline (§4)** — text-mode and (where applicable)
  microphone-mode produce a valid `latest_order.json` with `success:
  true`. The recommended categories and intensity match the spoken
  intent on at least one sample.
- [ ] **Task manager (§5)** — `/task/start` responds; a valid order
  drives the loop to `[state] done` with `/task/result` ending in
  `success`; an invalid order is rejected without robot motion.
- [ ] **Perception (§6)** — `detect_once` returns
  `success=true` with at least one entry `transform_valid=true` whose
  `base_xyz` lies inside the `task_manager.yaml` workspace box.
- [ ] **Robot dry-run (§7)** — every pick stage logs in order, the
  action returns `success=True, failure_code=0`, and the launch terminal
  confirms MOCK backends in use.
- [ ] **Conveyor (§8)** — exactly one `[conveyor_start]/[conveyor_stop]`
  pair per `false→true` edge; held-`true` does not re-trigger.
- [ ] **Real-hardware preflight (§9)** — every checkbox ticked.
- [ ] **One-nut real test** — `~/cobot2_ws/scripts/pick_one.py <class>`
  succeeds for the chosen class without cancellation, with the
  return-pose place_ready edge firing the conveyor exactly once.
- [ ] **Multi-nut task** — `~/cobot2_ws/scripts/voice_to_robot.py
  --text "..."` (or microphone equivalent) drives the full loop to
  `[state] done` with `/task/result success counts={...}`. Every
  consumed nut produces exactly one conveyor advance.
- [ ] **Status visibility** — `/task/status`, `/task/result`,
  `/conveyor/place_ready` echo the expected messages; if Firebase is
  enabled, the web UI shows `display_state: completed` and
  `robot_state: task_done` at the end.
- [ ] **No unsafe motion observed** — no collisions, no E-stop
  invocations, no stages that exit on `failure_code` 1, 3, 4, or 5
  during the multi-nut run.

When any criterion fails, halt and route through the relevant
troubleshooting section in `docs/03_run_manual.md` §12 before
re-running.
