# ROS2 노드 아키텍처

이 문서는 실행 중인 ROS 2 그래프의 형태를 설명한다. 어떤 노드들이
존재하는지, 무엇을 publish/subscribe 하는지, 노출하는 서비스와
액션, 동작을 좌우하는 파라미터, 그리고 이들을 묶는 런타임 흐름을
다룬다.

## 목차

1. 노드 개요 표
2. 메인 실행 그래프
3. ROS 인터페이스 (토픽 / 서비스 / 액션)
4. Task Manager 상태 머신
5. Pick-and-Place 시퀀스
6. 컨베이어 트리거 로직
7. 설정 및 파라미터
8. 디버깅 토픽 및 명령어

## 문서 구성

- `docs/01_system_architecture.md` — 시스템 수준 설계 및 근거.
- `docs/02_ros_node_architecture.md` — **이 파일**.
- `docs/03_run_manual.md` — 운영자용 실행 절차.
- `docs/04_validation_checklist.md` — 사전 점검 체크리스트.
- `docs/cleanup_deletion_proposal.md` 및
  `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` — 메타/정리
  기록. `_archive_cleanup/` 디렉토리는 **실제 코드가 아니며** 이
  파일에서 설명하는 런타임 그래프에서는 제외된다.

ROS 배포판: ROS 2 Humble. 이 저장소의 모든 Python 노드는
`ament_python`이며, `cobot_msgs`와 `cobot_bringup`은 `ament_cmake`이다.

> **이 문서 전반에서 사용하는 명명 규칙.** Doosan 측 노드들은
> `dsr01` 네임스페이스에 위치하므로 그 **노드 이름**은
> `/dsr01/robot_control_node`, `/dsr01/robot_action_helper`,
> `/dsr01/robot_pose_helper`이다. **서비스 및 액션 이름은 이
> 저장소에서 절대 경로로 사용된다** — `robot_control.yaml`에 선두
> `/`를 붙여 선언되며 (예: `/robot/pick_and_place`, `/robot/home`,
> `/robot/stop`, `/robot/get_current_pose`), 따라서 런타임에서
> `/dsr01/`이 **접두되지 않는다**. task manager는 `task_manager.yaml`
> 에서 동일한 절대 이름으로 호출한다.

---

## 1. 노드 개요 표

이 표는 `cobot_bringup/launch/full_system.launch.py`로 띄우는
프로덕션 런타임 노드와, 별도로 실행되는 컨베이어, 그리고 상위
RealSense / Doosan 패키지를 다룬다.

> **Actions** 열에는 노드가 *클라이언트*로 호출하는 주요 외부
> 인터페이스(전송하는 액션 goal과 알아둘 가치가 있는 소수의 외부
> 서비스 클라이언트 — 예: Doosan `/dsr01/system/get_current_pose`
> passthrough)도 함께 나열한다. 이렇게 같은 행에 두면 §3 인터페이스
> 표를 교차 참조하지 않고 각 노드를 끝까지 읽어낼 수 있다.
> *(server)* 표시는 노드가 호스트하는 것이고, *(client)* 표시는 노드가
> 소비하는 것이다.

| Node | Package | Key file | 역할 | Publishes | Subscribes | Services (server) | Actions | Parameters |
|---|---|---|---|---|---|---|---|---|
| `task_manager_node` | `cobot_task_manager` | `cobot_task_manager/task_manager_node.py` | 주문 기반 오케스트레이터: detect → select → pick 루프 | `/task/status` (`std_msgs/String`), `/task/result` (`std_msgs/String`) | — | `/task/start` (`std_srvs/Trigger`) | `/robot/pick_and_place` *(client)*, `/perception/detect_once` *(client)*, `/robot/home` *(client)*, `/db/get_nut_order` *(client when `order_source=db`)* | `order_source` (`mock`/`db`/`file`), `mock_order_*`, `db_service_name`, `file_order_path`, `file_order_require_success`, `class_priority`, `conf_gate`, `min_depth_mm`, `workspace_*_mm`, `return_xyz_mm`, `return_zyz_deg`, `pre_grasp_margin_mm`/`min_mm`/`max_mm`, `pick_offsets_path`, `perception_service_name`, `pick_action_name`, `home_service_name`, `max_detect_misses`, `max_grasp_failures`, `service_timeout_sec`, `action_timeout_sec`, `inter_pick_delay_sec`, `autostart` |
| `object_detection_node` | `cobot_object_detection` | `cobot_object_detection/object_detection_node.py` | RealSense 컬러 스트림 위에서 YOLOv8-OBB 추론, 멀티 프레임 융합 | `/detection/objects` (`cobot_msgs/DetectedObjectArray`) | `/camera/camera/color/image_raw` (`sensor_msgs/Image`, sensor QoS) | — | — | `model_path`, `class_names`, `imgsz`, `conf_threshold`, `iou_threshold`, `device`, `multi_frame_window_sec`, `cluster_distance_threshold_px`, `color_topic`, `output_topic`, `publish_when_empty` |
| `perception_transform_node` | `cobot_perception` | `cobot_perception/perception_transform_node.py` | OBB 내부의 깊이 조회, hand-eye + 핀홀 lift, 베이스 프레임 xyz + grasp yaw | — | `/detection/objects`, `/camera/camera/aligned_depth_to_color/image_raw`, `/camera/camera/color/camera_info` | `/perception/detect_once` (`cobot_msgs/srv/DetectOnce`) | `/robot/get_current_pose` *(client when `tcp_source=service`)* | `gripper2camera_npy`, `min_depth_camera_mm`, `max_depth_camera_mm`, `depth_offset_mm`, `min_depth_base_mm`, `tcp_source` (`fixed`/`service`), `fixed_tcp_xyz_mm`, `fixed_tcp_zyz_deg`, `tcp_service_name`, `tcp_service_timeout_sec`, `detection_topic`, `depth_topic`, `camera_info_topic`, `service_name` |
| `mock_perception_node` | `cobot_perception` | `cobot_perception/mock_perception_node.py` | 하드웨어 없는 `/perception/detect_once` 서버 (8개 너트 하드코딩 씬) | — | — | `/perception/detect_once` | — | — |
| `robot_control_node` | `cobot_robot_control` | `cobot_robot_control/robot_control_node.py` | Pick-and-place 액션 서버, 모션 + 그리퍼 파사드, place-ready 비콘 | `/conveyor/place_ready` (`std_msgs/Bool`, 10 Hz) | — | `/robot/home`, `/robot/stop` (both `std_srvs/Trigger`), `/robot/get_current_pose` (`cobot_msgs/srv/GetCurrentPose`) | `/robot/pick_and_place` *(server)*, `/dsr01/system/get_current_pose` *(client)* | `robot_id`, `robot_model`, `motion_backend` (`real`/`mock`), `gripper_backend` (`modbus`/`mock`/`tool_dio`), `gripper_ip`, `gripper_port`, `gripper_force_x10`, `gripper_open_width_x10`, `home_joints_deg`, `approach_offset_z_mm`, `velocity`/`acceleration`/`*_slow`, `grip_settle_timeout_sec`, `grasp_local_offset_xy_mm`, `action_name`, `home_service_name`, `stop_service_name`, `pose_service_name`, `doosan_pose_service`, `pose_passthrough_timeout_sec`, `place_ready_topic`, `place_y_margin_mm`, `place_ready_publish_period_sec`, `workspace_enabled`, `workspace_*_mm` |
| *그리퍼 제어* | `cobot_robot_control` | `cobot_robot_control/gripper_controller.py` | **ROS 노드가 아님** — 세 개의 백엔드(`MockGripperBackend`, Modbus RG2, `tool_dio` 스텁)를 가진 Python `Protocol`. `robot_control_node` 내에서 in-process로 사용된다. | — | — | — | — | — |
| `firebase_status_bridge` | `cobot_voice` | `cobot_voice/firebase_status_bridge.py` | 로봇 파이프라인 진행 상태를 Firestore `robot_state` 필드로 미러링 | — | `/task/status`, `/task/result`, `/conveyor/place_ready` | — | — | `status_topic`, `result_topic`, `place_ready_topic` |
| `voice_processing_node` | `cobot_voice` | `cobot_voice/voice_processing_node.py` | **legacy** wake word + STT 게시자. in-tree 노드에서 소비하지 않으며, 프로덕션 음성 경로는 `voice_to_robot.py` (in-process) 이다. | `/voice/text` (`std_msgs/String`), `/voice/status` (`std_msgs/String`) | (마이크 캡처, ROS 토픽 아님) | — | — | (ROS 파라미터 없음) |
| `web_voice_bridge_server` | `cobot_voice` | `cobot_voice/web_voice_bridge_server.py` | **ROS 노드가 아님** — 웹 UI용 음성 흐름을 구동하는 `127.0.0.1:8765`의 로컬 `ThreadingHTTPServer`. | — | — | — | — | CLI: `--host`, `--port` |
| `conveyor_serial_node` | `conveyor_controller` | `conveyor_controller/conveyor_serial_node.py` | `/conveyor_cmd` 문자열을 Arduino UNO로 전달; `/conveyor/place_ready` False→True 에지를 한 번의 시간 기반 진행으로 전환 | — | `/conveyor_cmd` (`std_msgs/String`), `/conveyor/place_ready` (`std_msgs/Bool`) | — | — | `port`, `baudrate`, `serial_timeout`, `arduino_reset_delay`, `command_topic`, `place_ready_topic`, `auto_command`, `auto_run_duration_sec` |
| `realsense2_camera_node` (`/camera/camera`) | `realsense2_camera` (upstream) | `rs_launch.py` | RealSense 컬러 + 정렬된 깊이 + camera_info | `/camera/camera/color/image_raw`, `/camera/camera/aligned_depth_to_color/image_raw`, `/camera/camera/color/camera_info`, `/camera/camera/depth/color/points` | — | — | — | `enable_color`, `enable_depth`, `rgb_camera.color_profile` (`1280x720x30`), `depth_module.depth_profile` (`848x480x30`), `align_depth.enable`, `enable_rgbd`, `pointcloud.enable`, `initial_reset` |
| `dsr_bringup2` 스택 (`/dsr01/...`) | `dsr_bringup2` (upstream) | `dsr_bringup2_rviz.launch.py` | Doosan 컨트롤러 bring-up: `ros2_control_node`, `dsr_controller2`, `joint_state_broadcaster`, 시스템 서비스 (`/dsr01/system/get_current_pose` 포함) | `/dsr01/joint_states`, 컨트롤러 토픽 | — | `/dsr01/system/get_current_pose` (그 외 다수) | — | `name=dsr01`, `host`, `port`, `mode` (`real`/`virtual`), `model` (`m0609`), `gui=false` |

`robot_control_node` **내부**에서 spawn 되는 in-process helper
노드들 (`ros2 node list`에 일반 노드처럼 보인다):

- `robot_action_helper` — `/robot/pick_and_place` 액션 서버,
  `/robot/home`, `/robot/stop` 서비스를 소유한다. 4-스레드 executor.
- `robot_pose_helper` — `/robot/get_current_pose`와
  `/dsr01/system/get_current_pose` 클라이언트를 소유한다. 2-스레드
  executor.

이 helper들은 메인 노드의 executor에서 발생하는 DSR_ROBOT2 트래픽이
액션 수락 또는 pose 서비스 응답을 굶기지 못하도록 존재한다 (전체
근거는 `robot_control_node.py` 175–260 줄 참고).

빈 스텁 (구현 없음, 어디에서도 launch 되지 않음): `cobot_safety`
(`safety_manager_node`), `cobot_policy` (`policy_selector_node`).

---

## 2. 메인 실행 그래프

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

실제 하드웨어 경로에서 `robot_control_node`는 `dsr01` 네임스페이스에
위치하며, `/dsr01/system/get_current_pose`와 DSR_ROBOT2 Python
모듈을 통해 `dsr_bringup2`와 통신하고, OnRobot RG2를 Modbus TCP
`192.168.1.1:502`로 구동한다 (그리퍼 자체에는 ROS 인터페이스가 없다).

---

## 3. ROS 인터페이스

### 3.1 토픽

| Topic | Type | Producer | Consumer(s) | payload 의미 | 사용 시점 |
|---|---|---|---|---|---|
| `/camera/camera/color/image_raw` | `sensor_msgs/Image` | `realsense2_camera_node` | `object_detection_node`, `scripts/yolo_rqt_view.py` | RGB 컬러 프레임, 1280×720@30, sensor QoS (best-effort, depth=2) | RealSense가 켜져 있는 동안 지속 |
| `/camera/camera/aligned_depth_to_color/image_raw` | `sensor_msgs/Image` | `realsense2_camera_node` | `perception_transform_node` | 컬러에 정렬된 깊이 (mm 단위 uint16), 848×480@30 | 지속 발행; `_on_depth` 콜백에서 latch |
| `/camera/camera/color/camera_info` | `sensor_msgs/CameraInfo` | `realsense2_camera_node` | `perception_transform_node` | 핀홀 내재 파라미터 (`K`로부터 fx, fy, ppx, ppy) | 지속; 첫 변경 시 캐시 |
| `/detection/objects` | `cobot_msgs/DetectedObjectArray` | `object_detection_node` | `perception_transform_node` | 융합된 2D OBB (`class_name`, `confidence`, `cx/cy/width/height/theta`); 여기서는 `transform_valid=false` | 처리된 컬러 프레임마다 한 메시지 (`_processing` 플래그로 게이트) |
| `/perception/detect_once` *(서비스 — 완전성을 위해 여기 나열)* | `cobot_msgs/srv/DetectOnce` | `perception_transform_node` | `task_manager_node`, `scripts/pick_*.py` | 베이스 프레임으로 lift된 최신 감지 (`base_xyz` mm, `grasp_yaw` rad, `short_axis_mm`, `long_axis_mm`, `transform_valid=true`) | task 루프 반복마다 1회 |
| `/conveyor/place_ready` | `std_msgs/Bool` | `robot_control_node` | `conveyor_serial_node`, `firebase_status_bridge` | place pose에서 그리퍼가 열려 있고 TCP가 place-y의 `place_y_margin_mm` 이내 | 10 Hz 기본 + `place`/`retreat` 단계 동안의 에지 전환 |
| `/conveyor_cmd` | `std_msgs/String` | (운영자 / 스크립트) | `conveyor_serial_node` | 벨트 명령: `F1`–`F100`, `R1`–`R100`, 또는 `STOP` (대문자, 시리얼에서는 newline 종결) | 수동 제어 / 디버깅 |
| `/task/status` | `std_msgs/String` | `task_manager_node` | `firebase_status_bridge` | `<state> [<info>]` — `init`, `detect`, `select_target <class>`, `pick_and_place <class>`, `done`, `aborted <reason>`, `safety_stop` | `_set_state`의 모든 상태 전환마다 |
| `/task/result` | `std_msgs/String` | `task_manager_node` | `firebase_status_bridge` | `success <info>` 또는 `failure <reason>` (예: `home_failed`, `action_failure`, `safety_stop`, `failure_code=N`) | task 실행당 1회, 종단 상태에서 |
| `/voice/text` | `std_msgs/String` | `voice_processing_node` (legacy) | (in-tree에 없음) | Whisper transcript | legacy; 프로덕션 음성 경로에서는 사용하지 않음 |
| `/voice/status` | `std_msgs/String` | `voice_processing_node` (legacy) | (in-tree에 없음) | `idle`, `wake_detected`, `listening`, `transcribing`, `processing`, `error` | legacy |

### 3.2 서비스

| Service | Type | Server | Client(s) | payload 의미 | 사용 시점 |
|---|---|---|---|---|---|
| `/task/start` | `std_srvs/Trigger` | `task_manager_node` | `voice_to_robot.py` (`cobot_voice.task_manager_dispatcher` → `ros2 service call` 경유), 운영자 | 워커가 아직 실행 중이 아니라면 시작한다. 이미 실행 중이면 `success=False`와 메시지 `"task already running"`을 반환한다. | `task_autostart:=false`이고 외부 트리거가 발화될 때 |
| `/perception/detect_once` | `cobot_msgs/srv/DetectOnce` | `perception_transform_node` (또는 `mock_perception_node`) | `task_manager_node`, `scripts/pick_one.py`, `scripts/pick_all.py` | 단발 감지 사이클. 응답에는 베이스 프레임 xyz, grasp yaw, mm 크기를 가진 `objects.objects[]`가 실린다; 깊이 + 내재 파라미터 + 감지가 모두 채워졌을 때만 `success=True`. | 픽 시도당 1회 |
| `/robot/home` | `std_srvs/Trigger` | `robot_control_node` (`robot_action_helper`에서) | `task_manager_node` | `move_joint`로 팔을 `home_joints_deg`로 이동. | task 시작 시 루프 진입 전 1회 |
| `/robot/stop` | `std_srvs/Trigger` | `robot_control_node` (`robot_action_helper`에서) | (운영자) | 내부 stop 이벤트 설정, place_ready 해제, 그리퍼 열기. | 수동 정지. 픽 액션은 `is_cancelled`로 이벤트를 관찰한다. |
| `/robot/get_current_pose` | `cobot_msgs/srv/GetCurrentPose` | `robot_control_node` (`robot_pose_helper`에서) | `perception_transform_node` (`tcp_source=service`일 때), 스크립트 | 현재 Doosan TCP를 반환 — `xyz_mm`과 `zyz_deg` (ZYZ Euler 도). | `tcp_source=service`일 때 (`perception.yaml`의 프로덕션 기본값) 매 `detect_once` 호출 |
| `/dsr01/system/get_current_pose` | `dsr_msgs2/srv/GetCurrentPose` | `dsr_bringup2` | `robot_control_node` (passthrough 소스) | Doosan 네이티브 pose 서비스 (`space_type=1` → ROBOT_SPACE_TASK, posx 반환). | `/robot/get_current_pose`의 백엔드 |
| `/db/get_nut_order` | `cobot_msgs/srv/GetNutOrder` | **(이 저장소에 서버 없음 — 미구현)** | `task_manager_node` (`order_source=db`일 때) | 너트 클래스별 개수 (`almond`, `cashew`, `pistachio`, `walnut`)와 `success`/`message`. | task 실행당 1회로 의도되었지만, 현재 `order_source:=db`로 설정하면 타임아웃됨. |

### 3.3 액션

| Action | Type | Server | Client(s) | payload 의미 | 사용 시점 |
|---|---|---|---|---|---|
| `/robot/pick_and_place` | `cobot_msgs/action/PickAndPlace` | `robot_control_node` (`robot_action_helper`에서) | `task_manager_node`, `scripts/pick_one.py`, `scripts/pick_all.py` | Goal: `target_class`, `grasp_xyz` (mm), `grasp_yaw` (rad), `pre_grasp_width_mm` (≤0이면 사전 위치 비활성화), `return_xyz`, `return_zyz_deg`. Feedback: `stage` ∈ {`pre_grasp_width`, `approach`, `grasp`, `verify_grip`, `lift`, `transit`, `place`, `retreat`, `home`}. Result: `success`, `failure_code` ∈ {0 ok, 1 approach_fail, 2 grasp_not_detected, 3 motion_fail, 4 safety_stop, 5 workspace_violation}, `message`. | 주문의 너트마다 1회; `_busy_lock`이 동시 goal을 거부 |

---

## 4. Task Manager 상태 머신

실제 상태들은 `cobot_task_manager/cobot_task_manager/task_state.py`에
`TaskState` (`str`-Enum)로 존재한다. `task_manager_node.py`의
`_set_state`를 통해 `/task/status`로 발행된다. 전체 집합은 다음과
같다:

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

**task manager에는 별도의 `WAITING_FOR_TASK`, `PLACING`,
`CONVEYOR_MOVING`, `TASK_DONE`, `ERROR` 상태가 존재하지 않는다.**
제안된 모델과의 매핑은 다음과 같다:

| 제안 상태 | 가장 가까운 TaskState | 비고 |
|---|---|---|
| `IDLE` | `IDLE` | 워커가 시작되기 전 `__init__`에서 설정 |
| `WAITING_FOR_TASK` | `IDLE` | `autostart=false`이면 노드는 `/task/start`까지 `IDLE`에 머무른다 |
| `DETECTING` | `DETECT` | `_detect_once` 직전에 설정 |
| `PICKING` | `PICK_AND_PLACE` | approach → grasp → verify_grip → lift를 포괄 |
| `PLACING` | `PICK_AND_PLACE` | `/conveyor/place_ready` 에지에서 외부적으로 추론 |
| `CONVEYOR_MOVING` | `PICK_AND_PLACE` | 동일: `firebase_status_bridge`가 동일 에지로부터 도출 |
| `TASK_DONE` | `DONE` | 성공 시 최종 상태 |
| `ERROR` | `ABORTED` (취소의 경우 `SAFETY_STOP`) | `aborted`는 info 필드에 사유를 담는다 |

### 4.1 전환 (실제 이름)

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

재시도 결정은 `cobot_task_manager/cobot_task_manager/retry_policy.py`에
인코딩되어 있다:

- `on_detect_miss(consecutive_misses)` → `max_detect_misses`까지
  `RETRY_DETECT`, 이후 `SKIP_CLASS`.
- `on_action_failure(failure_code, consecutive_grasp)`:
  - 코드 2 (`grasp_not_detected`) → `max_grasp_failures`까지
    `RETRY_PICK`, 이후 `SKIP_CLASS`.
  - 코드 1, 3, 4, 5 (`approach_fail`, `motion_fail`, `safety_stop`,
    `workspace_violation`) → `ABORT` (사람의 개입 필요).

---

## 5. Pick-and-Place 시퀀스

액션 서버는 `robot_control_node`에 위치하며, 실제 단계 시퀀스는
`cobot_robot_control/cobot_robot_control/motion_sequence.py`의
`execute_pick_and_place`에 있다. 성공적인 픽은 다음 단계들을
발생시킨다 (피드백으로 발행되는 문자열):

1. **요청된 너트 감지** — `task_manager_node`가
   `/perception/detect_once`를 호출한다. (액션 외부.)
2. **타겟을 베이스 프레임으로 변환** — `perception_transform_node`가
   각 감지에 대해 `base_xyz`, `grasp_yaw`, `short_axis_mm`,
   `long_axis_mm`을 계산하고, task manager가
   `target_selector.choose_target` (클래스 + 워크스페이스 + 신뢰도 +
   깊이 + transform-valid 필터; OBB 면적 후 신뢰도로 동점 처리)을
   통해 후보를 선택한다.
3. **`pre_grasp_width`** — 그리퍼가 `pre_grasp_width_mm` (단축 + 마진,
   클램프 적용)으로 열린다. `≤0`이면 건너뛴다.
4. **`approach`** — `[grasp_x, grasp_y, grasp_z + approach_offset_z_mm]`로
   기본 속도의 직선 이동. 워크스페이스 가드는 이미 실행되었다 (모든
   모션 전에 `failure_code=5`로 거부).
5. **`grasp`** — `grasp_pose`까지 저속 직선 이동, 이후
   `gripper.close()`, 그 다음 `wait_until_idle` (busy=True →
   busy=False).
6. **`verify_grip`** — `gripper.is_grip_detected()`; false이면
   그리퍼를 열고, approach pose로 후퇴하고, `failure_code=2`
   (`grasp_not_detected`)로 abort한다.
7. **`lift`** — 기본 속도로 approach pose까지 직선 이동하여 다시 위로
   올린다.
8. **`transit`** — `above_return = [return_x, return_y,
   return_z + approach_offset_z_mm]`로 직선 이동.
9. **`place`** — `place_pose` (`[return_x, return_y, return_z]`)까지
   저속 직선 이동, `gripper.open()`, `wait_until_idle`, 이후
   `is_tcp_at_place_y()` (TCP y가 `return_y`로부터 `place_y_margin_mm`
   이내)를 평가한다. 성공 시
   `place_ready_cb(True, "gripper_open_at_place")`가 발화 —
   `robot_control_node`가 `/conveyor/place_ready`를 True로 뒤집는다.
10. **place-ready 이벤트** — `conveyor_serial_node`가
    `/conveyor/place_ready`의 False→True 에지를 감지하고 한 번의 시간
    기반 진행을 시작한다.
11. **`retreat`** — `above_return`까지 직선 이동;
    `place_ready_cb(False, "retreat")`가 토픽을 다시 False로 뒤집는다
    (컨베이어 에지가 캡처된 이후에만).
12. **`home`** — `home_joints_deg`로 조인트 이동. 액션은
    `success=True, failure_code=0`을 반환한다.

이후 `task_manager_node`는 `inter_pick_delay_sec` (기본 `0.5` s) 동안
sleep 하여, 다음 `detect_once`를 발행하기 전 모션 중 카메라 프레임이
`perception_transform_node`의 버퍼에서 비워지도록 한다.

---

## 6. 컨베이어 트리거 로직

- **게시자**: `robot_control_node`. 토픽은 `/conveyor/place_ready`
  (`std_msgs/Bool`). 타이머에 의해 `place_ready_publish_period_sec`
  (기본 `0.1` s, 즉 10 Hz)으로 발행되며, 추가로 `_set_place_ready`
  내부의 모든 상태 변화에서 즉시 발행된다. True 전환은 `place`
  단계에서 `is_tcp_at_place_y()`가 true이고 그리퍼가 열렸을 때
  설정된다. False 전환은 `retreat`, `pick_and_place` 종료,
  `/robot/stop`, 모션 오류 / TCP 읽기 실패 시 설정된다.
- **구독자**: `conveyor_serial_node` (실제 하드웨어 드라이버)와
  `firebase_status_bridge` (에지를 Firestore의 `placing` +
  `conveyor_moving` `robot_state` 쓰기로 연속해서 미러링).
- **에지 트리거인 이유**: 토픽이 10 Hz로 지속 발행되므로, 컨베이어는
  레벨 의미를 사용할 수 없다 — 그러면 매 사이클마다 재트리거된다.
  `conveyor_serial_node._place_ready_callback`은
  `self._last_place_ready` 플래그를 유지하며 `False → True`에서만
  동작한다. 이전 실행이 여전히 활성 상태인 동안 도착하는 두 번째
  에지는 로그(`Ignoring place_ready trigger while conveyor auto-run is active`)에
  남기고 무시한다. True 유지 상태는 재트리거하지 않는다.
- **이동은 시간 기반이며 스텝 기반이 아니다.** True 에지에서 노드는
  `auto_command` (기본 `R80`)를 시리얼로 전송하고, 일회성
  `create_timer(auto_run_duration_sec, _auto_stop_callback)`를
  시작하며, 타이머 만료 시 `STOP`을 보낸다. Arduino 스케치
  (`conveyor_controller/arduino/ConveyorControl_Program/`)는
  `F<1-100>`, `R<1-100>`, `STOP`을 사용한다 — 현재 "N 스텝 동안
  실행" 명령은 없다. 스텝 모드 펌웨어 (`S<N>` + ack)는
  `conveyor_controller/README.md`에 **future work**로 문서화되어
  있다; 픽당 진행 거리는 근사치로 취급하고 처음 설정 시 줄자로
  검증해야 한다.

---

## 7. 설정 및 파라미터

이 절은 mock 와 real 하드웨어 사이를 전환할 때 가장 자주 만지게 될
설정값을 나열한다. 각 항목은 권위 있는 기본값이 위치한 파일을
가리킨다.

### 7.1 mock 와 real 모드

dry-run / mock / real 동작을 함께 선택하는 세 개의 독립 다이얼이
있다:

| Dial | File | 값 | 효과 |
|---|---|---|---|
| `motion_backend` | `cobot_robot_control/config/robot_control.yaml` (mock 기본) 또는 `robot_control.real.yaml` | `mock` \| `real` | `mock`은 즉시 반환; `real`은 DSR_ROBOT2를 바인딩하고 Doosan을 움직인다 |
| `gripper_backend` | 동일 | `mock` \| `modbus` \| `tool_dio` (스텁) | `modbus`는 RG2에 Modbus TCP 클라이언트를 연다 |
| `tcp_source` | `cobot_perception/config/perception.yaml` | `fixed` \| `service` | `service`는 detect 사이클마다 `/robot/get_current_pose`를 호출한다 (real 모드의 기본값) |

`cobot_bringup/launch/full_system.launch.py`의 최상위 launch 토글:

- `enable_realsense:=true|false`
- `enable_dsr_bringup:=true|false`
- `dsr_mode:=virtual|real`
- `task_autostart:=true|false`
- `order_source:=mock|db|file`
- `file_order_path:=<latest_order.json의 절대 경로>`
- `enable_firebase_status_bridge:=true|false`
- `config_robot_control:=<share>/cobot_robot_control/config/robot_control.real.yaml`

real 하드웨어로 **들어가려면**
`enable_dsr_bringup:=true dsr_mode:=real` *과* real-config 경로를
*함께* 전달해야 한다 — 그렇지 않으면 안전한 mock 기본 YAML이
이긴다.

### 7.2 로봇 IP 와 포트

- Doosan 컨트롤러 — `host:=192.168.1.100`, `port:=12345`
  (`robot.launch.py`의 기본값). 환경에 따라 필요시 오버라이드.
- OnRobot RG2 — `gripper_ip: 192.168.1.1`, `gripper_port: 502`
  (`robot_control.yaml`). Modbus TCP.

### 7.3 컨베이어 시리얼 포트

- `port: /dev/ttyACM0`
  (`conveyor_controller/config/conveyor_controller.yaml`의 기본값).
- `baudrate: 115200` — Arduino 스케치와 일치해야 한다.
- `arduino_reset_delay: 2.0` — 포트를 연 후 UNO가 USB-reset 부팅을
  마치도록 대기.
- `ros2 launch conveyor_controller conveyor_controller.launch.py port:=/dev/ttyACMx baudrate:=...`로
  오버라이드.

### 7.4 Place 지점 (return / drop pose)

- `cobot_task_manager/config/task_manager.yaml`에서:
  ```yaml
  return_xyz_mm:  [367.0, -150.0, 90.0]
  return_zyz_deg: [168.0, 179.0, 168.0]
  ```
  이는 액션 goal의 `return_xyz` / `return_zyz_deg` 필드이다.
- `place_y_margin_mm: 3.0` (`robot_control.yaml`) — place_ready를
  True로 뒤집을지 결정할 때 `is_tcp_at_place_y()`가 사용하는 허용
  오차.
- `approach_offset_z_mm: 80.0` (`robot_control.yaml`) — approach 와
  `above_return` 모두에 사용되는 lift.

### 7.5 클래스별 Z 오프셋

- 단일 정보 출처: `cobot_config/config/pick_offsets.yaml`.
- 로더: `cobot_task_manager.pick_offsets.load_pick_offsets`는 다음
  순서로 해석한다:
  1. 명시적 `pick_offsets_path` 파라미터 (`task_manager.yaml`),
  2. `COBOT_PICK_OFFSETS_PATH` 환경 변수,
  3. `ament_index` share 조회,
  4. 소스 트리 fallback.

  이 후보들 중 어떤 것도 읽을 수 있는 파일을 가리키지 않으면,
  로더는 `DEFAULT_OFFSETS_MM` (`almond=0`, `cashew=0`, `pistachio=0`,
  `walnut=-1.0`)을 반환한다. *로드된* YAML에서 누락된 클래스별
  항목은 동일한 기본값으로 fallback 된다.
- pick 단계에서**만** 적용되며, `goal.grasp_xyz.z`에 더해진다.
- 현재 값:
  ```yaml
  per_class_z_offset_mm:
    almond: 0.0
    cashew: 0.0
    pistachio: 0.0
    walnut: -1.0
  ```
- 참고: `scripts/pick_one.py`와 `scripts/pick_all.py`는 상단에 자체
  `PER_CLASS_Z_OFFSET` 딕셔너리를 유지하며, YAML에서 자동으로
  로드되지 **않는다**. 그래야 하는지 **검증 필요** (현재 코드 기준
  의도적으로 이 방식을 유지).

### 7.6 ROS_DOMAIN_ID

- 참조 값 `66`은 `cobot_bringup/config/params.yaml`에 기록되어
  있지만, **그 파일은 `cobot_bringup/launch/`의 어떤 launch 파일에도
  로드되지 않는다.** 유효 도메인은 launch 시점에 운영자 셸의
  `ROS_DOMAIN_ID` 값이다. 중앙에서 강제하고 싶다면 **검증 필요**.

### 7.7 객체 감지 모델 경로

- `cobot_object_detection/config/object_detection.yaml`:
  ```yaml
  model_path: ""
  device: ""    # "" auto, "cpu", "cuda:0"
  imgsz: 800
  conf_threshold: 0.75
  ```
- 해석 순서 (`cobot_object_detection/cobot_object_detection/model_paths.py`):
  1. 명시적 `model_path` (절대 경로, 또는 CWD 기준 상대, 또는 ament
     share 기준 상대),
  2. ament share `models/best.pt`
     (`experiments/cobot_OD_obb_nano/.../weights/best.pt` 심볼릭
     링크에서 `cobot_object_detection/setup.py`로 설치),
  3. `experiments/` 아래의 소스 트리 fallback.

### 7.8 캘리브레이션 설정

- `cobot_perception/config/perception.yaml` — `gripper2camera_npy`는
  **필수** (`T_gripper2camera.npy` 경로); `depth_offset_mm` 기본값
  `-35.0`; `min_depth_camera_mm`/`max_depth_camera_mm`/`min_depth_base_mm`
  게이트.
- `cobot_config/config/handeye.yaml` — 참조 값; 현재
  `perception_transform_node`에서는 실제로 로드되지 않음.
- `cobot_config/config/workspace.yaml` — 참조 값; 런타임 워크스페이스는
  `task_manager.yaml`과 `robot_control.yaml`에 위치한다.

---

## 8. 디버깅 토픽 및 명령어

### 8.1 라이브 그래프 검사

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

### 8.2 task manager 관찰

```bash
ros2 topic echo /task/status
ros2 topic echo /task/result
ros2 topic echo /conveyor/place_ready
```

`/task/status`는 상태 전환마다 한 줄; `/task/result`는 task 실행마다
종단에서만 한 줄.

### 8.3 "가짜" task 시작 트리거

`task_autostart:=false`이면 워커는 외부 트리거를 기다린다:

```bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

기대 응답: `success=True message='task started'` (또는
`success=False message='task already running'`).

파일 모드 JSON을 완전히 우회하고 하드코딩된 개수로 전체 루프를
테스트하려면, `order_source:=mock`과 `task_manager.yaml`의
`mock_order_*` 파라미터로 launch 한다.

### 8.4 place-ready 에지 수동 발화 (로봇 불필요)

```bash
# Flip True (one edge → one belt advance)
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
# Reset to False so the next True is a new edge
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: false}"
```

`conveyor_serial_node`는 `auto_run_duration_sec` 동안 `auto_command`를
실행하고 STOP 한다. 로봇을 돌리지 않고 컨베이어 배선을 검증하는 데
유용하다.

### 8.5 컨베이어 수동 구동

```bash
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'F30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'R30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'STOP'}"
```

### 8.6 perception 과 robot 정상 점검

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

### 8.7 단일 픽 액션을 수동으로 전송

저장소에는 `detect_once` 응답으로부터 `PickAndPlace` goal을
조립하는 스크립트가 포함되어 있다 — goal yaml을 직접 작성하기보다
이쪽이 권장된다:

```bash
~/cobot_ws/scripts/pick_one.py cashew --dry-run         # print only
~/cobot_ws/scripts/pick_one.py cashew --z-override 315  # send action
```

프로그래밍적 CLI 형식:

```bash
ros2 action send_goal -f /robot/pick_and_place cobot_msgs/action/PickAndPlace \
  "{target_class: 'cashew',
    grasp_xyz: {x: 400.0, y: 0.0, z: 60.0},
    grasp_yaw: 0.0,
    pre_grasp_width_mm: 30.0,
    return_xyz: {x: 367.0, y: -150.0, z: 90.0},
    return_zyz_deg: [168.0, 179.0, 168.0]}"
```

> 실제 로봇 대상으로는 항상 먼저 `--dry-run` 한다. 액션 서버의
> 워크스페이스 가드는 박스 밖 goal을 모션 전에 `failure_code=5`로
> 거부하지만, 운영자는 여전히 숫자가 합리적인지 검증해야 한다.

### 8.8 런타임 파라미터 검사

```bash
ros2 param list /task_manager_node
ros2 param get  /task_manager_node order_source
ros2 param get  /dsr01/robot_control_node motion_backend
ros2 param get  /perception_transform_node tcp_source
ros2 param set  /conveyor_serial_node auto_run_duration_sec 3.0
```

### 8.9 노드 로그 추적

이 저장소에서는 `ros2 launch ... output:=screen`이 기본값이지만, 사후
확인이 필요하다면:

```bash
ls -t ~/.ros/log/                 # newest run first
ros2 launch cobot_bringup full_system.launch.py | tee /tmp/run.log
```

부팅 시 다음 마커들을 살펴본다 (기존 운영 매뉴얼의 미러):

- `Subscribed to /camera/camera/color/image_raw, publishing on /detection/objects`
- `Service /perception/detect_once ready`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `FileOrderProvider reading /.../latest_order.json` (`order_source:=file`
  일 때만)

동반 문서 `docs/03_run_manual.md`은 이 점검들을 권장 부팅 순서로
연결하고, `docs/04_validation_checklist.md`는 정확한 통과/실패
기준을 나열한다.
