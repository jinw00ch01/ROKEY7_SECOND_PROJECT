# Execution Preparation and Run Manual

This is a step-by-step operator manual for the integrated cobot
nut-picking system.

## Index

1. Purpose
2. Pre-Run Checklist
3. Environment Variables
4. Build Instructions
5. Dry-Run / Mock Mode Execution
6. Voice-to-Task Test
7. Full System Run with Real Hardware
8. One-Nut First Test
9. Conveyor Test
10. Status Monitoring
11. Shutdown Procedure
12. Troubleshooting
Appendix — Quick command reference

## Document set

- `docs/01_system_architecture.md` — read this first if you have not
  seen the system before.
- `docs/02_ros_node_architecture.md` — per-node interface reference,
  parameter lists, and the full ROS debugging command surface.
- `docs/03_run_manual.md` — **this file**.
- `docs/04_validation_checklist.md` — the test/acceptance checklist
  matched to the steps below.
- `docs/cleanup_deletion_proposal.md` — deletion plan for archived /
  flagged files (read-only meta document).

The legacy `docs/run_manual.md` is **superseded** by this file. It
contains stale paths (`~/cobot_ws/...`) and outdated calibration values
(e.g. obsolete `--z-override 315`); do not use it as the source of
truth.

> **Do not source or run anything from `_archive_cleanup/`.** That
> directory holds files moved out of the active tree on
> `<YYYYMMDD>` (current batch: `20260508`). It contains no runnable
> entry points and is intentionally not built by `colcon`. See
> `docs/cleanup_deletion_proposal.md` for the plan and
> `_archive_cleanup/20260508/cleanup_manifest.md` for the per-file
> reason/evidence/risk record.

Conventions used in this document:

- Workspace path is `~/cobot2_ws`. Replace if your clone lives elsewhere.
- Each shell command is meant to be entered **on one line** — long
  `ros2 launch …` invocations break if a terminal soft-wraps them
  (bash splits at the wrap and silently drops the remaining args).
- `T1`, `T2`, … denote separate terminal tabs/windows.

---

## 1. Purpose

This manual walks an operator through:

1. Bringing up the `cobot2_ws` workspace from a fresh shell.
2. Verifying the system safely in mock / dry-run mode (no robot motion,
   no real gripper, no real camera if desired).
3. Triggering an end-to-end voice → recommendation → robot pick-up run.
4. Switching to real hardware (Doosan M0609 + OnRobot RG2 + RealSense +
   Arduino conveyor) once the mock path is healthy.
5. Monitoring, shutting down, and recovering from common failures.

It does **not** cover assembly, calibration, training the YOLO model,
or web/Firebase project setup — only the runtime steps you take each
time you operate the demo.

---

## 2. Pre-Run Checklist

Run these checks before every session. Stop and resolve anything that
fails before continuing.

### 2.1 Software environment

- [ ] Ubuntu 22.04 with ROS 2 Humble installed.
- [ ] ROS environment sourced in **every** terminal you use:
  ```bash
  source /opt/ros/humble/setup.bash
  source ~/cobot2_ws/install/setup.bash
  ```
- [ ] `ROS_DOMAIN_ID` exported (see §3).
- [ ] Workspace built without errors (see §4).
- [ ] Required Python deps available: `numpy`, `scipy`, `opencv-python`,
  `cv_bridge` (system), `ultralytics`, `pyserial`, `pyaudio`,
  `sounddevice`, `openwakeword`, `openai`, `langchain-openai`,
  `python-dotenv`, optionally `firebase-admin`.
- [ ] System binaries: `ffplay` (ElevenLabs playback) and/or `spd-say`
  (`speech-dispatcher`).

### 2.2 Credentials

- [ ] `cobot_voice/resource/.env` exists (copy from `.env.example`)
  with at minimum `OPENAI_API_KEY` set, **only** if you plan to use
  STT or the LLM analyzers.
- [ ] `FIREBASE_SERVICE_ACCOUNT` points at a valid service-account
  JSON, **only** if you want the web UI / Firestore mirror.
  Without it, the writers no-op silently and the robot pipeline still
  works.
- [ ] ElevenLabs key set, **only** if `COBOT_TTS_PROVIDER=elevenlabs`.

### 2.3 Containers / Docker

There are **no Dockerfiles or docker-compose files in this repo**. Object
detection, perception, robot control, and the voice pipeline all run as
native ROS 2 nodes on the host. If your deployment runs anything in a
container, that is out-of-tree and **needs verification** in your local
setup.

### 2.4 Hardware (real-mode only — skip for mock)

- [ ] Intel RealSense plugged into a USB-3 port:
  ```bash
  lsusb | grep -i realsense
  ```
- [ ] Doosan controller reachable:
  ```bash
  ping -c 3 192.168.1.100
  ```
- [ ] OnRobot RG2 reachable:
  ```bash
  ping -c 3 192.168.1.1
  ```
- [ ] Conveyor Arduino enumerated:
  ```bash
  ls /dev/ttyACM*       # expect /dev/ttyACM0
  ```
- [ ] Pendant: **AUTO** mode + **Servo On** + status indicator white.
  A red indicator silently fails motion (the API returns success but the
  arm does not move — known footgun).
- [ ] **E-stop within reach** of the operator running the laptop.
- [ ] **Workspace clear**: nuts inside the configured workspace box
  (`task_manager.yaml` / `robot_control.yaml`); no fingers, cables, or
  tooling in the approach / transit / return paths; conveyor belt path
  unobstructed.

---

## 3. Environment Variables

Only variables actually consulted by code in this repo are listed. The
defaults given are what the code falls back to.

### 3.1 ROS

| Variable | Used by | Required | Notes |
|---|---|---|---|
| `ROS_DOMAIN_ID` | All ROS 2 traffic | Yes | Pick a value all terminals will share. `cobot_bringup/config/params.yaml` lists `66` as a reference, but **that file is not loaded by any launch file** — the effective value is whatever you `export` in the shell. **Needs verification** if you intend to centralize this. |
| `RMW_IMPLEMENTATION` | All ROS 2 traffic | No | `cobot_bringup/config/params.yaml` lists `rmw_cyclonedds_cpp` as the team's reference RMW. Same caveat: not auto-applied. |

Example:
```bash
export ROS_DOMAIN_ID=99
# export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp   # optional
```

### 3.2 Voice / TTS / LLM

These are resolved by `cobot_voice.env.load_package_env`, which loads
`cobot_voice/resource/.env` (or the file pointed to by
`COBOT_VOICE_ENV_PATH`).

| Variable | Required | Default in code | Purpose |
|---|---|---|---|
| `COBOT_VOICE_ENV_PATH` | No | `cobot_voice/resource/.env` | Override the dotenv file location |
| `OPENAI_API_KEY` | Yes (for STT/LLM) | (none — startup raises) | Whisper transcription + gpt-4o analyzers |
| `COBOT_VOICE_PROMPT_MODE` | No | `freeform` | `freeform` (LLM analyzers) or `menu` (numbered Korean menu + regex) |
| `COBOT_TTS_ENABLED` | No | `1` | Set to `0`/`false`/`no`/`off` to silence TTS audio |
| `COBOT_TTS_PROVIDER` | No | `auto` | `auto` (ElevenLabs if key present, else `spd-say`), `elevenlabs`, or `spd-say` |
| `ELEVENLABS_API_KEY` (or `ELEVEN_LABS_API_KEY`) | If using ElevenLabs | — | Required when provider resolves to ElevenLabs |
| `ELEVENLABS_VOICE_ID` | No | `pNInz6obpgDQGcFmaJgB` (Adam) | |
| `ELEVENLABS_MODEL_ID` | No | `eleven_flash_v2_5` | |
| `ELEVENLABS_LANGUAGE_CODE` | No | `ko` | |
| `ELEVENLABS_OUTPUT_FORMAT` | No | `mp3_44100_128` | |
| `ELEVENLABS_STABILITY` | No | `0.5` | Float |
| `ELEVENLABS_SIMILARITY_BOOST` | No | `0.75` | Float |
| `ELEVENLABS_STYLE` | No | `0.0` | Float |
| `ELEVENLABS_USE_SPEAKER_BOOST` | No | `true` | Bool |

### 3.3 Firebase

| Variable | Required | Purpose |
|---|---|---|
| `FIREBASE_SERVICE_ACCOUNT` | No | Path to Admin SDK service-account JSON. If unset, the code tries `firebase_admin.initialize_app()` with default ADC. If both fail, `firebase_bridge` flips to no-op silently. |

### 3.4 Task manager

| Variable | Required | Purpose |
|---|---|---|
| `COBOT_PICK_OFFSETS_PATH` | No | Override the resolution chain for `cobot_config/config/pick_offsets.yaml`. Loader order: explicit `pick_offsets_path` parameter → this env var → ament-share lookup → source-tree fallback. If no file is found, the built-in `DEFAULT_OFFSETS_MM` (`walnut: -1.0`, others `0.0`) is used. |

### 3.5 Recommended export block (mock session)

```bash
export ROS_DOMAIN_ID=99
source /opt/ros/humble/setup.bash
source ~/cobot2_ws/install/setup.bash
# Optional: silence TTS during mock runs
export COBOT_TTS_ENABLED=0
```

### 3.6 Recommended export block (full real run with LLM voice)

```bash
export ROS_DOMAIN_ID=99
source /opt/ros/humble/setup.bash
source ~/cobot2_ws/install/setup.bash
# .env file is auto-loaded by cobot_voice; you only need this if you
# want a non-default location:
# export COBOT_VOICE_ENV_PATH=/absolute/path/to/cobot_voice.env
```

---

## 4. Build Instructions

From the workspace root:

```bash
cd ~/cobot2_ws
colcon build --symlink-install
source install/setup.bash
```

Targeted rebuilds (faster iteration):

```bash
# After editing a single Python package
colcon build --packages-select cobot_task_manager --symlink-install

# After editing the message package, rebuild everything that depends on it
colcon build --packages-select cobot_msgs
colcon build --packages-up-to cobot_bringup
```

Notes:

- `--symlink-install` is recommended so Python edits do not require a
  rebuild for runtime to pick them up. YAML config under
  `cobot_*/config/` **does** require a build to be re-installed into
  `share/`.
- `cobot_msgs` is `ament_cmake` (interfaces). Other in-repo Python
  packages are `ament_python`.
- The OD model is packaged through `cobot_object_detection/setup.py`
  from
  `experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt`.
  If that file is missing the build still succeeds, but the resolver
  falls back to the source tree at runtime.
- Marker files: `web_stt_firebase/`, `nuts_data_recording/`, `scripts/`,
  and `docs/` carry `COLCON_IGNORE`. They are never built.

After `colcon build`, **always** `source install/setup.bash` again in
each terminal so the new packages are visible.

---

## 5. Dry-Run / Mock Mode Execution

Use this mode whenever the robot, gripper, or camera are unavailable, or
whenever you have changed perception / motion / task code. It exercises
the **entire** task loop without any hardware action.

### 5.1 What "mock" means

- `motion_backend: mock` (in `cobot_robot_control/config/robot_control.yaml`,
  the **default** YAML) — DSR_ROBOT2 is never imported; the action server
  completes the full stage sequence instantly.
- `gripper_backend: mock` — no Modbus traffic; `is_grip_detected()`
  returns true so `verify_grip` always succeeds.
- `mock_perception_node` — provides `/perception/detect_once` with a
  hardcoded 8-nut scene. No camera needed.
- `task_autostart:=false` — the worker stays idle until you trigger
  `/task/start`.

### 5.2 Terminal layout

#### T1 — full system in mock

```bash
source ~/cobot2_ws/install/setup.bash
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false enable_firebase_status_bridge:=false
```

This launches the **real** `perception_transform_node` and
`object_detection_node`, but with `enable_realsense:=false` they will
have no camera frames. To test the loop end-to-end without a camera,
swap in the mock perception node — see §5.3.

Expected boot lines:

- `Initializing MOCK motion backend ...` *(if it logs the warning)*
- `Initializing MOCK gripper backend ...`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `Service /perception/detect_once ready`
- `Subscribed to /camera/camera/color/image_raw, publishing on /detection/objects`
- `[state] idle` (task manager waiting for `/task/start`)

#### T2 (alternative) — substitute mock perception

If you want the loop to actually return targets, run the mock perception
node instead of the real one. This requires launching the system without
the real perception transform node — easiest path is to launch the
sub-systems individually:

```bash
# T1 — robot stack only (mock backends), no perception
source ~/cobot2_ws/install/setup.bash
ros2 launch cobot_robot_control robot_control.launch.py
```

```bash
# T2 — mock perception
source ~/cobot2_ws/install/setup.bash
ros2 run cobot_perception mock_perception_node
```

```bash
# T3 — task manager (autostart false so we control trigger)
source ~/cobot2_ws/install/setup.bash
ros2 launch cobot_task_manager task_manager.launch.py
```

> **Needs verification**: `task_manager.launch.py` does not pass
> `task_autostart` through; the YAML default is `autostart: true`. If
> you need an idle-then-trigger pattern in this layout, run the node
> directly:
> ```bash
> ros2 run cobot_task_manager task_manager_node --ros-args -p autostart:=false
> ```

#### T4 — fake task sender

```bash
source ~/cobot2_ws/install/setup.bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

Expected reply:
```
response:
std_srvs.srv.Trigger_Response(success=True, message='task started')
```

Then, in the T1 (or T3) terminal, you should see the loop emit:

```
[state] init
[state] detect
[state] select_target almond
[state] pick_and_place almond
[state] detect
...
[state] done
```

…with `/task/result` ending in `success counts={...} skipped=[...]`.

### 5.3 Conveyor in mock mode

The conveyor node tries to open `/dev/ttyACM0` on startup. If you do not
have an Arduino, **omit it entirely**. The `place_ready` topic is still
published by `robot_control_node` and is harmless without a subscriber.

If you do want to exercise the conveyor logic without an Arduino, you
can inspect the topic and the auto-stop timer would still be set up if
the node could open the port — but it will simply log the open failure
and run with `serial_port=None`. **Needs verification** whether sending
commands while the port is `None` produces any meaningful behavior.

---

## 6. Voice-to-Task Test

This section verifies the voice pipeline → JSON file → `/task/start`
hand-off. The robot stack can stay in mock mode while you do this.

### 6.1 Pre-conditions

- T1 launched in **file mode** (so the task manager actually consumes
  `latest_order.json`):
  ```bash
  source ~/cobot2_ws/install/setup.bash
  ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false enable_firebase_status_bridge:=false order_source:=file file_order_path:=/home/aes/cobot2_ws/cobot_voice/output/latest_order.json
  ```
  Verify in the T1 log:
  ```
  FileOrderProvider reading /home/aes/cobot2_ws/cobot_voice/output/latest_order.json
  ```
  If that line is missing, the task manager fell back to `mock` —
  re-check the `order_source:=file` argument and that you didn't soft-wrap
  the launch line.

- `OPENAI_API_KEY` set (in `cobot_voice/resource/.env`) for the LLM
  analyzers and Whisper STT.

### 6.2 Text mode (no microphone)

The fastest way to verify the integration end-to-end:

```bash
source ~/cobot2_ws/install/setup.bash
~/cobot2_ws/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이 도움 필요해요"
```

Expected stdout:

```
recognized_text : '피곤하고 집중이 안 돼서 많이 도움 필요해요'
combo           : [{'nut': 'cashew', 'count': 3}, {'nut': 'walnut', 'count': 3}]
success         : True
dispatched      : True
```

Verify the JSON contract:

```bash
cat ~/cobot2_ws/cobot_voice/output/latest_order.json
```

Should contain `success: true` and a non-empty `combo` array. The
`request_id` is a `YYYYMMDD_HHMMSS` timestamp.

Verify the `/task/start` trigger fired — the T1 task manager log should
move from `idle` to `init` → `detect` → `select_target <class>` → … →
`done`.

### 6.3 Debug-mode voice (keyboard, no mic)

Step through the prompt flow with terminal input instead of STT:

```bash
~/cobot2_ws/scripts/voice_to_robot.py --debug
```

You will be prompted for the state and intensity strings.

### 6.4 Microphone mode (full voice)

```bash
~/cobot2_ws/scripts/voice_to_robot.py
```

1. Say the wake word ("Hello Rokey" — the bundled
   `hello_rokey_8332_32.tflite` model).
2. Wait for the TTS prompt asking your condition; speak for ~5 s.
3. Wait for the intensity prompt; speak for ~5 s.
4. The TTS will confirm the combo, then the task manager auto-starts.

### 6.5 Web bridge variant

To drive the voice flow from the React web UI:

```bash
# T1 — task manager + perception in file mode (as in §6.1)

# T2 — local HTTP bridge for the web UI
source ~/cobot2_ws/install/setup.bash
ros2 run cobot_voice web_voice_bridge_server
# Server listens on http://127.0.0.1:8765 (override with --host/--port)

# T3 — Vite dev server for the UI
cd ~/cobot2_ws/web_stt_firebase
npm install     # first time only
npm run dev
```

The web UI's start button POSTs to `/voice-audio/start`; the bridge
runs the same `voice_order_flow` and writes `latest_order.json` and
Firestore. The robot trigger path is the same as §6.2.

### 6.6 Skip the robot trigger (validation only)

```bash
~/cobot2_ws/scripts/voice_to_robot.py --text "..." --no-dispatch
```

Saves `latest_order.json` but does **not** call `/task/start`.

---

## 7. Full System Run with Real Hardware

> ⚠ **Real-hardware mode moves a 6-DOF arm.** Verify §2.4 and §6.4 in
> mock mode first. Keep an E-stop in reach. Set `gripper_force_x10` no
> higher than necessary (current default `150` → 15 N).
>
> Real mode is opted into explicitly. Mock is the default.

### 7.1 Network check

```bash
ping -c 3 192.168.1.100   # Doosan controller
ping -c 3 192.168.1.1     # OnRobot RG2 gripper
lsusb | grep -i realsense
ls /dev/ttyACM*           # Arduino conveyor
```

All four must respond before continuing.

### 7.2 Recommended terminal layout

#### T1 — Doosan bring-up

```bash
source ~/cobot2_ws/install/setup.bash
ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=192.168.1.100 port:=12345
```

Wait for:

- `Connected to DRCF`
- `ROBOT_STATE : STATE_STANDBY`
- `Configured and activated dsr_controller2`
- `Configured and activated joint_state_broadcaster`

Leave this terminal alone; closing it disconnects the robot.

If you see `Controller already loaded`, a zombie `ros2_control_node` is
alive — Ctrl-C T1, then in any terminal:
```bash
pkill -9 -f ros2_control_node
```
…and re-launch T1.

#### T2 — RealSense

```bash
source ~/cobot2_ws/install/setup.bash
ros2 launch realsense2_camera rs_launch.py enable_color:=true enable_depth:=true align_depth.enable:=true
```

Wait for `RealSense Node Is Up!` then sanity-check from T6 (or any spare
terminal):

```bash
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw
# expect ~30 Hz; Ctrl-C
```

#### T3 — full cobot stack in real mode

> ⚠ This is the line that activates real motion + real gripper. Keep
> the E-stop in your hand. Type/paste in **one line**.

```bash
source ~/cobot2_ws/install/setup.bash
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false dsr_mode:=real config_robot_control:=$(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config/robot_control.real.yaml order_source:=file file_order_path:=/home/aes/cobot2_ws/cobot_voice/output/latest_order.json
```

Notes on the args:

- `enable_realsense:=false` — already running in T2.
- `enable_dsr_bringup:=false` — already running in T1.
- `dsr_mode:=real` — propagated to sub-launches; not strictly needed
  here because `enable_dsr_bringup:=false`, but kept for documentation.
- `config_robot_control:=...real.yaml` — **this** is the line that
  switches `motion_backend` from mock to real and `gripper_backend`
  from mock to modbus. Without it, you run a mock robot regardless of
  T1.

Wait for:

- `Initializing DSR_ROBOT2 (id=dsr01, model=m0609)`
- `Initializing Modbus RG2 at 192.168.1.1:502 (force=15.0N)`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `Service /perception/detect_once ready`
- `FileOrderProvider reading /home/aes/cobot2_ws/cobot_voice/output/latest_order.json`

#### T4 — conveyor (real Arduino)

```bash
source ~/cobot2_ws/install/setup.bash
ros2 launch conveyor_controller conveyor_controller.launch.py
```

Wait for:

- `Connected to Arduino serial port /dev/ttyACM0 at 115200 baud`
- `Listening on /conveyor_cmd for commands: F<1-100>, R<1-100>, STOP`
- `Place-ready trigger: one False->True edge on /conveyor/place_ready ...`

If you see `Failed to open serial port /dev/ttyACM0`, see §12.

#### T5 — operator terminal (sanity → trigger)

```bash
source ~/cobot2_ws/install/setup.bash

# Live TCP read works?
ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"

# One detection cycle (no motion)
ros2 service call /perception/detect_once cobot_msgs/srv/DetectOnce "{}"

# Dry-run a single pick (prints, does not move the robot)
~/cobot2_ws/scripts/pick_one.py cashew --dry-run
```

Once those look healthy:

- For a **single-nut** test, see §8.
- For voice-driven full pickup:
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이"
  ```
  or microphone mode (§6.4).

---

## 8. One-Nut First Test

**Always** run a single-nut pick before any multi-nut session, especially
after editing perception / motion / calibration code or moving the camera.

```bash
~/cobot2_ws/scripts/pick_one.py cashew --dry-run
```

Confirm the printed `base_xyz` is sensible (workspace bounds say
`x ∈ [200, 700]`, `y ∈ [-300, 300]`, `z` near the nut height range
`40–80` mm). If it is not, **stop** and recalibrate before attempting
a real pick.

Then:

```bash
~/cobot2_ws/scripts/pick_one.py cashew
# or, when tuning Z:
~/cobot2_ws/scripts/pick_one.py cashew --z-override 315
# or, when tuning the gripper pre-position:
~/cobot2_ws/scripts/pick_one.py cashew --pre-grasp-width 35
```

Watch the action feedback in the T3 log:

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

Result-code reminder (from `cobot_msgs/action/PickAndPlace`):

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | approach_fail |
| 2 | grasp_not_detected |
| 3 | motion_fail |
| 4 | safety_stop |
| 5 | workspace_violation |

Iterate `--z-override` in 5 mm steps until you find a value that grips
without pressing the table. Then commit it via
`cobot_config/config/pick_offsets.yaml` (per-class `_z_offset_mm`) so
the task-manager path uses the same value on the next run.

---

## 9. Conveyor Test

You can verify the conveyor wiring + edge logic without running the
robot.

### 9.1 Manually fire one place_ready edge

In one terminal, watch the conveyor node logs (T4 from §7). In another:

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: false}"
```

Expected behavior:

- The True message triggers exactly one belt advance:
  ```
  [conveyor_start] command=R80 duration=5.00s (place_ready edge)
  ```
- After `auto_run_duration_sec` seconds (default `5.0`), the timer
  expires and the node sends `STOP`:
  ```
  [conveyor_stop]  command was R80, duration=5.00s elapsed
  ```
- The False message resets `_last_place_ready` so the next True will be
  a new edge.

A second `True` posted while the timer is active is logged
`Ignoring place_ready trigger while conveyor auto-run is active` and is
ignored — this is intentional (one edge = one movement).

### 9.2 Manual command override

Same terminal:

```bash
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'F30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'STOP'}"
```

These bypass the edge logic entirely.

### 9.3 Tuning the per-pick distance

Movement is **duration-based, not step-based** (see
`conveyor_controller/README.md`). Distance ≈ belt speed × duration.

To slow down or shorten the advance without rebuilding:

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py auto_command:=R30 auto_run_duration_sec:=2.0
```

Or live, on a running node:

```bash
ros2 param set /conveyor_serial_node auto_run_duration_sec 3.0
ros2 param set /conveyor_serial_node auto_command R50
```

**Step-mode firmware** (exact distance per trigger) is documented as
future work in `conveyor_controller/README.md`. Until that lands,
verify per-pick distance with a tape measure on first install.

---

## 10. Status Monitoring

### 10.1 ROS topics

```bash
# Per-state transitions of the task loop
ros2 topic echo /task/status

# One terminal line per task run, success or failure
ros2 topic echo /task/result

# Conveyor edge stream (10 Hz baseline + edge updates)
ros2 topic echo /conveyor/place_ready

# Action stage feedback (task_manager already publishes status, but
# the action server also emits per-stage feedback)
ros2 action list -t
ros2 action info /robot/pick_and_place
```

Useful one-shots:

```bash
ros2 topic hz /detection/objects
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw

ros2 node list
ros2 service list -t
```

### 10.2 Web UI / Firestore

If `enable_firebase_status_bridge:=true` (the default) and Firebase
credentials are loaded:

- The web UI subscribes to `robot_session/current` and renders both
  `display_state` (voice flow) and `robot_state` (robot pipeline).
- `robot_state` values you will see during a run:
  `detecting → picking → placing → conveyor_moving → task_done`
  (or `error` with a `robot_error` field on failure).

### 10.3 Mark a single pick visually

Use the rqt YOLO overlay:

```bash
~/cobot2_ws/scripts/yolo_rqt_view.py
# Then in another terminal:
ros2 run rqt_image_view rqt_image_view /yolo/annotated
```

This subscribes to the same color stream, runs YOLO independently, and
publishes annotated frames — does **not** affect the production
`object_detection_node` pipeline.

---

## 11. Shutdown Procedure

Reverse of bring-up. The goal is to leave the arm safe and not strand
zombie processes.

1. **Stop new task input.**
   - Stop the voice flow (Ctrl-C the `voice_to_robot.py` terminal, or
     close the web UI tab).
   - If the task loop is running, wait for `[state] done` if possible.
     Otherwise:
     ```bash
     ros2 service call /robot/stop std_srvs/srv/Trigger "{}"
     ```

2. **Return the robot home** (real mode only; mock has no effect):
   ```bash
   ros2 service call /robot/home std_srvs/srv/Trigger "{}"
   ```
   Wait for `success: True`. Or pause the task loop and use the pendant.

3. **Stop the cobot stack (T3).** Ctrl-C in the launch terminal.
   Wait for the launch to fully tear down (all `process has finished
   cleanly` lines).

4. **Stop the conveyor (T4).** Ctrl-C. The serial port closes; the
   Arduino keeps running its idle state.

5. **Stop the camera (T2).** Ctrl-C.

6. **Stop the Doosan bring-up (T1).** Ctrl-C. This disconnects from the
   controller. If you see "Controller already loaded" on the next run:
   ```bash
   pkill -9 -f ros2_control_node
   ```

7. **Stop the web bridge / npm dev server.** Ctrl-C in those terminals.

8. **Last resort** if processes are wedged:
   ```bash
   pkill -9 -f 'ros2 launch'
   pkill -9 -f ros2_control_node
   pkill -9 -f realsense2_camera_node
   ```

---

## 12. Troubleshooting

### 12.1 No STT result (Whisper)

- Verify mic device. `MicConfig.device_index` is hard-coded to `6` in
  `cobot_voice/cobot_voice/mic_controller.py`. **Needs verification**
  per host:
  ```bash
  python3 -c "import sounddevice as sd; print(sd.query_devices())"
  ```
- Verify `OPENAI_API_KEY` is loaded:
  ```bash
  python3 -c "from cobot_voice.env import get_required_env; print(bool(get_required_env('OPENAI_API_KEY')))"
  ```
- Use text mode to bypass STT and isolate the failure:
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py --text "피곤해요"
  ```

### 12.2 Keyword extraction failed (no `categories`)

- The `voice_order_flow` saves `success: false` and a `categories: []`
  on the JSON when it cannot resolve a state.
- Symptoms: `dispatched: True` but the task manager logs
  `FileOrderProvider` rejecting the order, or `voice_to_robot.py`
  exits with non-zero.
- In freeform mode, retry with a clearer keyword:
  `피곤`, `집중`, `혈당`, `다이어트`.
- Or switch to menu mode for the session:
  ```bash
  export COBOT_VOICE_PROMPT_MODE=menu
  ```

### 12.3 `latest_order.json` not created

- Verify the path exists:
  ```bash
  ls -la ~/cobot2_ws/cobot_voice/output/
  ```
- Verify the dotenv is reachable:
  ```bash
  cat ~/cobot2_ws/cobot_voice/resource/.env       # should have OPENAI_API_KEY
  ```
- Run with logging:
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py --debug
  ```
  Watch for the `[INFO] save_recommendation_order` line near the end.

### 12.4 `/task/start` not available

```bash
ros2 service list | grep task
# Expect /task/start
```

If absent:

- Confirm `task_manager_node` is running: `ros2 node list | grep task_manager`.
- If it crashed at startup, look for these in T3:
  - `unknown order_source=...`
  - `order_source='file' requires file_order_path parameter`
- Re-launch with the corrected `order_source`/`file_order_path`.

### 12.5 No detection result (perception)

- `ros2 topic hz /detection/objects` — should be > 0 Hz when nuts are
  visible.
- If 0 Hz, check the camera:
  ```bash
  ros2 topic hz /camera/camera/color/image_raw
  ```
- If the camera is up but detections are 0, lower the gate temporarily:
  ```bash
  ros2 param set /object_detection_node conf_threshold 0.40
  ```
- Verify the YOLO model loaded — T1/T3 should log
  `Loading YOLO-OBB model: ...`.

### 12.6 `transform_valid: false` on every detection

`perception_transform_node` returns `transform_valid=false` when:

- Depth is missing inside the OBB (`median_inside_obb` returns
  non-finite). Increase the OBB or lower `min_depth_camera_mm` in
  `cobot_perception/config/perception.yaml`.
- TCP read failed (only when `tcp_source: service`). Symptoms in the
  T3 log:
  - `tcp source error: /robot/get_current_pose not ready`
  - `get_current_pose call timed out`
- Hand-eye file not loaded — startup raises:
  `gripper2camera_npy is required.` Set the path in
  `perception.yaml`.

For initial bring-up before robot_control is healthy, fall back to a
fixed TCP:

```bash
ros2 param set /perception_transform_node tcp_source fixed
```

…with `fixed_tcp_xyz_mm` / `fixed_tcp_zyz_deg` set in the YAML.

### 12.7 Robot action unavailable

```bash
ros2 action list | grep pick_and_place
# Expect /robot/pick_and_place
```

If absent:

- Is `robot_control_node` up? `ros2 node list | grep robot_control_node`.
- In real mode, was the right config selected? Check the T3 log for
  `Initializing DSR_ROBOT2 ...` (real) vs `Using MOCK motion backend`
  (mock).
- The action server is hosted on the in-process `robot_action_helper`
  node — its presence in `ros2 node list` is normal, not a duplicate.

### 12.8 Gripper not responding

- Ping the gripper:
  ```bash
  ping -c 3 192.168.1.1
  ```
- Verify `gripper_backend: modbus` (real-mode YAML) — the **default**
  YAML uses `mock`.
- Inspect Modbus connectivity. **Needs verification** for your
  network — there is no in-tree Modbus diagnostic command.
- A close that never settles surfaces as
  `failure_code=3 motion_fail "gripper close did not settle in time"`.
  Check the RG2 power LED + air-pressure (if your variant uses it).

### 12.9 Conveyor serial permission error

Symptom in T4: `Failed to open serial port /dev/ttyACM0: ... Permission denied`.

```bash
sudo usermod -aG dialout $USER
# log out, log back in for the group change to take effect
```

Or, just for this session:

```bash
sudo chmod a+rw /dev/ttyACM0
```

Verify:

```bash
ls -l /dev/ttyACM0
groups | grep dialout
```

If the port is busy:

```bash
sudo fuser -v /dev/ttyACM0
```

Close the offending process (often the Arduino IDE serial monitor).

### 12.10 `ROS_DOMAIN_ID` mismatch

Symptoms: `ros2 node list` empty, or only sees a subset of expected
nodes; topics from one terminal don't appear in another.

- Every terminal must export the same `ROS_DOMAIN_ID` **before**
  sourcing the workspace.
- Check effective value in each terminal:
  ```bash
  echo $ROS_DOMAIN_ID
  ```
- If you need to share with a remote host, both must match. RMW
  implementations must also match (default `rmw_fastrtps_cpp` on
  Humble; the team's reference is `rmw_cyclonedds_cpp` per
  `cobot_bringup/config/params.yaml`, but that file is **not loaded**
  automatically — set `RMW_IMPLEMENTATION` in the shell if you want it
  enforced).

### 12.11 Docker cannot see ROS topics

This repo does not use Docker (see §2.3). If you have introduced a
container locally, `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION` must match
the host **and** networking must allow multicast (or use FastDDS
discovery server). **Needs verification** for your setup; nothing in
this repo configures it.

### 12.12 Firebase unavailable

- The writers (`firebase_bridge.py`) silently no-op when
  `firebase_admin` cannot initialize. The robot pipeline is unaffected.
- To diagnose:
  ```bash
  python3 -c "from cobot_voice.firebase_bridge import _ensure_session_ref; _ensure_session_ref(); print('ok')"
  ```
  An exception will surface here even though it is swallowed during
  normal runs.
- Common causes:
  - `FIREBASE_SERVICE_ACCOUNT` not set or pointing at a missing file.
  - Service-account JSON does not have Firestore access in the project.
  - No outbound internet from the host.
- Disable the bridge entirely if needed:
  ```bash
  ros2 launch cobot_bringup full_system.launch.py enable_firebase_status_bridge:=false ...
  ```

### 12.13 Other operational footguns (already documented elsewhere)

- **Pendant red light** → motion commands silently succeed without
  moving. Switch to AUTO + Servo On.
- **Line wrap in `ros2 launch`** → bash splits and drops trailing args.
  Type/paste in one line.
- **Zombie `ros2_control_node`** → `pkill -9 -f ros2_control_node`.
- **Camera disconnected mid-run** → `The device has been disconnected!`
  in T2. Replug into a different USB-3 port and restart T2.
- **Workspace mismatch** between `task_manager.yaml` and
  `robot_control.yaml` will cause goals that pass the task filter to be
  rejected at the action server with `failure_code=5`. Keep both
  bounds-blocks in sync until they share a single source of truth.

---

## Appendix — Quick command reference

```bash
# Build + source
cd ~/cobot2_ws && colcon build --symlink-install && source install/setup.bash

# Mock e2e (one terminal)
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false enable_firebase_status_bridge:=false

# Real e2e (T1: dsr_bringup2; T2: realsense; T3: this)
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false dsr_mode:=real config_robot_control:=$(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config/robot_control.real.yaml order_source:=file file_order_path:=/home/aes/cobot2_ws/cobot_voice/output/latest_order.json

# Conveyor
ros2 launch conveyor_controller conveyor_controller.launch.py

# Trigger task with a fake order (mock-mode quick check)
ros2 service call /task/start std_srvs/srv/Trigger "{}"

# Voice → robot end-to-end
~/cobot2_ws/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이"

# Single nut
~/cobot2_ws/scripts/pick_one.py cashew --dry-run
~/cobot2_ws/scripts/pick_one.py cashew

# Status
ros2 topic echo /task/status
ros2 topic echo /task/result
ros2 topic echo /conveyor/place_ready

# Stop
ros2 service call /robot/stop std_srvs/srv/Trigger "{}"
```

For deeper inspection commands (parameters, action goals, etc.) see
`docs/02_ros_node_architecture.md` §8.
