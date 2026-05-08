# 시스템 아키텍처

이 문서는 `cobot_ws` 워크스페이스의 최종 상태를 기술한다. 시스템이 무엇을 하는지, 그것을 가능하게 하는 런타임 구성요소, 그들 간의 데이터 계약, 기대되는 하드웨어, 그리고 안전 설계를 다룬다. 이 문서는 시스템을 실행하기 **전에** 이해해야 하는 팀원을 위해 작성되었다.

## 목차

1. 프로젝트 목표
2. End-to-End 흐름
3. 런타임 구성요소
4. 데이터 계약
5. 하드웨어 아키텍처
6. 안전 설계
7. 현재 알려진 갭 / 결정 사항

## 문서 세트

| 문서 | 목적 |
|---|---|
| `docs/01_system_architecture.md` (이 파일) | 시스템이 무엇을 하는지와 그 이유 |
| `docs/02_ros_node_architecture.md` | 노드별 ROS 인터페이스 레퍼런스 |
| `docs/03_run_manual.md` | 단계별 운영자 실행 순서 |
| `docs/04_validation_checklist.md` | 사전 점검 테스트 체크리스트 |
| `docs/cleanup_deletion_proposal.md` | 아카이브되었거나 제거 대상으로 표시된 파일에 대한 삭제 계획 |
| `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` | cleanup 배치별 manifest — 아카이브된 모든 파일에 대한 사유 / 근거 / 리스크 |

설계 이력 파일들(`docs/_archive/run_manual.md`, `docs/_archive/voice_to_robot_integration_plan.md`, `docs/_archive/three_firebase_bridge_*.md`, `docs/_archive/nut_recommendation_*.md`, `docs/_archive/stt_db_tts_robot_integration.md`)은 위 네 개의 문서로 **대체**되어 `docs/_archive/`로 이전되었다. 이력 보존을 위해 git 트리에 남아 있지만 구식 캘리브레이션 값과 이미 도입된 통합에 대한 참조를 포함한다. 1차 레퍼런스로 사용하지 말 것.

`_archive_cleanup/<YYYYMMDD>/` 디렉토리(현재 `20260508/`)는 **활성 코드가 아니다**. 삭제 결정 보류 중인 파일들을 런타임 트리 밖으로 옮겨 보관한다. 거기에서 `source`, `colcon build`, `import` 또는 다른 어떤 실행도 하지 말 것. 아카이브의 목적은 활성 트리를 깨끗하게 유지하면서 git history를 보존하는 것이다. 삭제 계획은 `docs/cleanup_deletion_proposal.md`를 참고할 것.

---

## 1. 프로젝트 목표

이 시스템은 Doosan M0609 6-DOF cobot에 OnRobot RG2 그리퍼, Intel RealSense 카메라, 그리고 Arduino로 제어되는 stepper 컨베이어를 결합한, 음성 기반 견과류 픽 앤 플레이스 데모이다.

완전한 사용자 상호작용은 다음과 같다.

1. 사용자가 웹 UI를 열고 음성 세션을 시작한다(또는 `voice_to_robot.py` CLI를 실행한다).
2. 음성 파이프라인이 wake word를 감지한 다음, 사용자에게 (TTS로) **컨디션**("오늘 컨디션은?")과 **강도**("얼마나 드릴까요?")를 묻는다.
3. 사용자는 음성으로 답하고, STT(Whisper)가 각 답변을 전사한다.
4. 키워드/카테고리 분석기가 답변을 네 개의 컨디션 카테고리 중 하나, 그리고 세 개의 강도 레벨 중 하나로 매핑한다.
5. 콤보 룰 엔진이 견과류 개수 리스트(**주문**)를 생성하고, `cobot_voice/output/latest_order.json`에 기록하며, Firestore에 진행 상황을 미러링하여 웹 UI가 상태를 렌더링할 수 있게 한다.
6. `voice_to_robot.py`가 `task_manager_node`의 `/task/start`를 호출하고, task manager는 `FileOrderProvider`를 통해 같은 JSON 파일을 읽는다.
7. 주문에 남은 각 견과류에 대해, task manager는 `/perception/detect_once`를 호출하고 워크스페이스 내에서 요청된 클래스의 최선 후보를 픽한 뒤 `/robot/pick_and_place` 액션 goal을 보낸다.
8. `robot_control_node`는 픽 단계(approach → grasp → verify_grip → lift → transit → place → retreat → home)를 실행하고, 플레이스 자세에서 RG2 그리퍼를 열고 `/conveyor/place_ready`를 assert한다.
9. 컨베이어 노드는 그 **False → True** 엣지를 한 번의 시간 기반 벨트 전진으로 변환한 뒤 정지하여, 다음 견과류를 받을 준비를 한다.
10. 주문이 비면 task manager가 `/task/status`와 `/task/result`에 `done`을 게시하고, `firebase_status_bridge`가 이를 Firestore에 미러링하여 웹 UI가 "completed"를 표시할 수 있게 한다.

---

## 2. End-to-End 흐름

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

## 3. 런타임 구성요소

이 절은 본 repo에 포함된 모든 런타임 구성요소를 나열한다. 비어 있는 스텁 패키지(`cobot_safety`, `cobot_policy`)는 §7에 명시되어 있으며, 오늘날 런타임 구성요소가 **아니다**.

### 3.1 웹 UI / 시작 버튼

- **패키지/모듈**: `web_stt_firebase/` (Vite + React 19 + Three.js + Firebase 12). 워크스페이스 루트에 위치하며 `COLCON_IGNORE`가 적용되어 있다.
- **주요 파일**: `src/App.tsx`, `src/components/`, `firebase.json`, `firestore.rules`, `package.json`.
- **책임**: 데모 상태(idle, listening, recommending, completed, error)를 렌더링하고, 호스트의 오디오 워크플로를 트리거하는 시작 affordance를 제공한다.
- **입력**: Firestore 문서 `robot_session/current` (실시간 listener).
- **출력**: `127.0.0.1:8765`의 `web_voice_bridge_server`(§3.2 참고)로 보내는 HTTP POST.

### 3.2 웹 음성 브릿지 서버

- **패키지/모듈**: `cobot_voice.web_voice_bridge_server` (실행파일 `web_voice_bridge_server`).
- **주요 파일**: `cobot_voice/cobot_voice/web_voice_bridge_server.py`, `cobot_voice/cobot_voice/voice_web_demo.py`.
- **책임**: `POST /voice-state`, `POST /voice-command`, `POST /voice-audio/start`, `POST /voice-audio/stop`, `GET /health`를 노출하는 `ThreadingHTTPServer`. wake word/STT 루프를 호스팅하고 Firestore 업데이트를 푸시하는 `VoiceWebDemo`를 구동한다.
- **입력**: 웹 UI로부터의 HTTP 요청.
- **출력**: `firebase_bridge`를 통해 Firestore에 기록하고, 추천 흐름을 호출한다.

### 3.3 TTS

- **패키지/모듈**: `cobot_voice.voice_order_flow.speak()` (in-process, 노드가 아님).
- **주요 파일**: `cobot_voice/cobot_voice/voice_order_flow.py`.
- **책임**: 한국어 프롬프트와 최종 확인 메시지를 음성으로 출력한다. provider는 환경변수로 결정된다: `COBOT_TTS_PROVIDER` (`auto` / `elevenlabs` / `spd-say`), `COBOT_TTS_ENABLED`. ElevenLabs는 `ELEVENLABS_API_KEY`를 사용하며, 기본 voice는 `pNInz6obpgDQGcFmaJgB` (Adam), 한국어, MP3는 `ffplay`로 재생한다. 실패 시 `spd-say`로 fallback한다.
- **입력**: `cobot_voice/config/question_flow.json`의 프롬프트 문자열과 계산된 콤보 텍스트.
- **출력**: 호스트의 기본 사운드 디바이스로의 오디오 출력.

### 3.4 STT

- **패키지/모듈**: `cobot_voice.stt.STT` (in-process). 별도의 ROS 노드 `voice_processing_node`가 존재하지만 legacy이다 — §7 참고.
- **주요 파일**: `cobot_voice/cobot_voice/stt.py`, `cobot_voice/cobot_voice/mic_controller.py`, `cobot_voice/cobot_voice/wakeup_word.py`.
- **책임**: 5초간 마이크 캡처(16 kHz mono int16) → OpenAI Whisper(`whisper-1`) → 텍스트. wake word는 번들된 `hello_rokey_8332_32.tflite` 모델을 실행하는 `openwakeword`이다.
- **입력**: 마이크 디바이스(`MicConfig.device_index=6`, 48 kHz로 캡처 후 16 kHz로 리샘플; 호스트별로 **검증 필요**).
- **출력**: 전사된 한국어 텍스트.

### 3.5 키워드 추출 / 추천

- **패키지/모듈**: `cobot_voice` (in-process; ROS 인터페이스 없음).
- **주요 파일**:
  - `cobot_voice/cobot_voice/voice_order_flow.py` — 최상위 상태머신 (wake → ask state → STT → ask intensity → STT → combo → save + dispatch).
  - `cobot_voice/cobot_voice/keyword_extractor.py` — `StateAnalyzer`와 `IntensityAnalyzer` (langchain을 통한 gpt-4o), `save_recommendation_order`.
  - `cobot_voice/cobot_voice/nut_recommendation.py` — 키워드 기반 추출, 강도별 개수, 콤보 룰, 한국어 콤보 텍스트.
  - `cobot_voice/config/keyword_categories.json` — 카테고리 → 키워드 + 견과.
  - `cobot_voice/config/nut_combo_rules.json` — 강도별 개수와 `per_category_intensity_count_capped_by_max_total` 전략.
  - `cobot_voice/config/question_flow.json` — 한국어 TTS 프롬프트.
- **책임**: STT 텍스트를 `(categories, intensity, combo)` 추천으로 변환한다. 두 가지 프롬프트 모드는 `COBOT_VOICE_PROMPT_MODE`로 선택된다 (§7 참고):
  - `freeform` (기본) — LLM 분석기.
  - `menu` — 명시적 메뉴 프롬프트와 regex 매칭.
- **입력**: 두 개의 STT 전사(컨디션 + 강도).
- **출력**: `cobot_voice/output/latest_order.json`과 Firestore `robot_session/current`에 기록되는 주문 dict.

### 3.6 주문 provider / 데이터베이스

- **패키지/모듈**: `cobot_task_manager.order_provider`.
- **주요 파일**: `cobot_task_manager/cobot_task_manager/order_provider.py`.
- **책임**: `task_manager_node`에 `OrderBook`을 제공한다. selector는 `order_source` 파라미터이다:
  - `mock` — `MockOrderProvider`. `mock_order_almond/cashew/pistachio/walnut` 파라미터의 하드코드된 개수.
  - `db` — `DBOrderProvider`. `/db/get_nut_order`에서 `cobot_msgs/srv/GetNutOrder`를 호출한다. **이 repo에는 서버 측이 구현되어 있지 않다. 클라이언트 배선은 존재하지만 서버를 누군가 제공하지 않으면 timeout된다.**
  - `file` — `FileOrderProvider`. `latest_order.json`을 읽는다. `success=false`이거나 `combo`가 비어 있는 주문은 거절한다. 동일한 주문을 재트리거 시 재실행하지 않도록 `request_id`를 추적한다.
- **입력**: JSON 파일(file 모드), 서비스(db 모드), 또는 설정된 개수(mock 모드).
- **출력**: task 루프에서 소비되는 `OrderBook` (`{class: count}`).

### 3.7 Task manager

- **패키지/모듈**: `cobot_task_manager.task_manager_node` (실행파일 `task_manager_node`).
- **주요 파일**:
  - `cobot_task_manager/cobot_task_manager/task_manager_node.py` — 루프.
  - `cobot_task_manager/cobot_task_manager/target_selector.py` — 워크스페이스 + confidence + depth 필터링.
  - `cobot_task_manager/cobot_task_manager/retry_policy.py` — 검출/grasp 미스 처리 (`max_detect_misses`, `max_grasp_failures`).
  - `cobot_task_manager/cobot_task_manager/pick_offsets.py` — `cobot_config/config/pick_offsets.yaml` 로더.
  - `cobot_task_manager/config/task_manager.yaml` — 기본값.
- **책임**: 전체 픽 루프를 오케스트레이션한다. `/robot/home`을 호출한 다음, 주문에 항목이 있는 동안: `detect_once` → `choose_target` → `pick_and_place`를 수행하며, goal 시점에 클래스별 z 오프셋을 적용한다. `/task/status`와 `/task/result` (`std_msgs/String`)을 게시한다. `task_autostart:=false`로 시작한 후 워커를 트리거할 수 있도록 `/task/start`를 노출한다.
- **입력**: §3.6의 주문; 서비스 `/perception/detect_once`; 액션 `/robot/pick_and_place`; 서비스 `/robot/home`.
- **출력**: 액션 goal; status/result 토픽.

### 3.8 객체 검출

- **패키지/모듈**: `cobot_object_detection.object_detection_node` (실행파일 `object_detection_node`).
- **주요 파일**:
  - `cobot_object_detection/cobot_object_detection/object_detection_node.py`
  - `cobot_object_detection/cobot_object_detection/yolo_detector.py`
  - `cobot_object_detection/cobot_object_detection/detection_postprocess.py` (multi-frame 융합 / 클러스터링).
  - `cobot_object_detection/cobot_object_detection/model_paths.py` — 설정된 경로, 그 다음 `ament` share `models/best.pt`, 그 다음 source-tree 학습 출력 순으로 resolve한다.
  - `cobot_object_detection/config/object_detection.yaml`.
  - 모델 가중치: `experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt` (`.gitignore` allow-list로 `best.pt` 파일만 커밋된다).
- **책임**: RealSense color를 구독하고, YOLOv8-OBB(Ultralytics)를 실행하여 융합된 2D OBB 검출 결과를 게시한다. 여기서 `transform_valid`는 **false**로 남겨지며 perception transform이 채운다.
- **입력**: `/camera/camera/color/image_raw` (sensor QoS).
- **출력**: `/detection/objects` (`cobot_msgs/DetectedObjectArray`).

### 3.9 Perception transform

- **패키지/모듈**: `cobot_perception.perception_transform_node` (실행파일 `perception_transform_node`). 동일 패키지에 하드웨어 없이 e2e 테스트를 위한 `mock_perception_node`가 함께 포함된다.
- **주요 파일**:
  - `cobot_perception/cobot_perception/perception_transform_node.py`
  - `cobot_perception/cobot_perception/depth_filter.py` (OBB 내부의 median)
  - `cobot_perception/cobot_perception/handeye_transform.py` (`load_gripper2camera`, `tcp_to_base2gripper`, `compose_base2camera`, `transform_camera_to_base`).
  - `cobot_perception/cobot_perception/grasp_pose_generator.py` (`yaw_from_obb`).
  - `cobot_perception/config/perception.yaml`.
- **책임**: 매 `/perception/detect_once` 호출마다 최신 검출 결과를 가져와 각 OBB 내부의 median depth를 조회하고, 핀홀 모델로 카메라 프레임으로 lift하며, `T_gripper2camera.npy`를 사용해 로봇 base 프레임으로 변환하고, OBB theta로부터 `grasp_yaw`를 계산하며, 물리 OBB 사이즈(`short_axis_mm`, `long_axis_mm`)를 emit한다. TCP 소스는 선택 가능하다: `fixed`(선언된 파라미터) 또는 `service`(`/robot/get_current_pose` 호출). `cobot_perception/config/perception.yaml`의 기본값은 `service`이다.
- **입력**: `/detection/objects`, `/camera/camera/aligned_depth_to_color/image_raw`, `/camera/camera/color/camera_info`, `T_gripper2camera.npy` (`gripper2camera_npy`로 경로 필수), 그리고 `fixed_tcp_*` 파라미터 또는 pose 서비스.
- **출력**: `transform_valid=true`로 채워진 항목을 가진 `/perception/detect_once` (`cobot_msgs/srv/DetectOnce`) 응답.

### 3.10 로봇 제어

- **패키지/모듈**: `cobot_robot_control.robot_control_node` (실행파일 `robot_control_node`).
- **주요 파일**:
  - `cobot_robot_control/cobot_robot_control/robot_control_node.py` — 액션 서버, home/stop 서비스, pose passthrough, place_ready 게시자. 액션 트래픽과 pose 조회가 DSR_ROBOT2 spin 경합으로 starve되지 않도록, 전용 multi-threaded executor에서 동작하는 두 개의 추가 in-process helper 노드(`robot_action_helper`, `robot_pose_helper`)를 사용한다.
  - `cobot_robot_control/cobot_robot_control/motion_sequence.py` — 단계 시퀀스(`pre_grasp_width`, `approach`, `grasp`, `verify_grip`, `lift`, `transit`, `place`, `retreat`, `home`)와 워크스페이스 가드.
  - `cobot_robot_control/cobot_robot_control/doosan_motion_client.py` — 실제 DSR_ROBOT2 wrapper 및 mock 구현.
  - `cobot_robot_control/cobot_robot_control/pose_converter.py` — point/yaw 및 ZYZ ↔ Doosan posx 변환.
  - `cobot_robot_control/config/robot_control.yaml` (mock 기본값) 및 `robot_control.real.yaml` (실 하드웨어 override).
- **책임**: 로봇을 소유한다. `/robot/pick_and_place` (액션), `/robot/home`, `/robot/stop`, `/robot/get_current_pose` (서비스)를 제공한다. `/conveyor/place_ready`를 10 Hz로 엣지 업데이트와 함께 게시한다.
- **입력**: 액션 goal, 서비스, 그리고 기본 Doosan 네임스페이스(`dsr01`).
- **출력**: 액션 결과 + feedback, place_ready 토픽, Doosan 컨트롤러로의 모션.

### 3.11 그리퍼 제어

- **패키지/모듈**: 별도의 노드가 아니라 `cobot_robot_control` 내부에 위치한다.
- **주요 파일**: `cobot_robot_control/cobot_robot_control/gripper_controller.py`.
- **책임**: 세 가지 구현을 가진 플러그형 백엔드(`Protocol`):
  - `MockGripperBackend` — 하드웨어 없이 즉시 완료.
  - Modbus RG2 백엔드 — `192.168.1.1:502`의 Modbus TCP, `force_x10`과 `max_width_x10` 파라미터(기본값 150 → 15 N, 1100 → 110 mm).
  - Tool DIO 백엔드 — 인터페이스 스텁만 존재; 오늘 기준 **Not Implemented**.
  - `wait_until_idle` 두 단계 wait(busy=True → busy=False)는 `verify_grip` 단계에서 사용된다.
- **입력**: `motion_sequence`로부터의 width/open/close 호출.
- **출력**: 물리 그리퍼 모션 + verify를 위한 `is_grip_detected()`.

### 3.12 컨베이어 제어

- **패키지/모듈**: `conveyor_controller.conveyor_serial_node` (실행파일 `conveyor_serial_node`). 펌웨어: `arduino/ConveyorControl_Program/`.
- **주요 파일**:
  - `conveyor_controller/conveyor_controller/conveyor_serial_node.py`
  - `conveyor_controller/launch/conveyor_controller.launch.py`
  - `conveyor_controller/config/conveyor_controller.yaml`
  - `conveyor_controller/README.md`
- **책임**: `/conveyor_cmd` (`std_msgs/String`, 값은 `F1`–`F100`, `R1`–`R100`, `STOP`)을 구독하여 줄바꿈으로 종료된 시리얼 라인으로 전달한다. `/conveyor/place_ready` (`std_msgs/Bool`)을 구독하고, 매 **False → True 엣지**마다 `auto_command`(기본 `R80`)를 `auto_run_duration_sec`(기본 `5.0` s) 동안 송신한 뒤 `STOP`을 보낸다. 활성 실행 중의 두 번째 엣지는 로깅되고 무시된다.
- **입력**: `/conveyor_cmd`, `/conveyor/place_ready`, `/dev/ttyACM0` 115200 baud의 Arduino.
- **출력**: Arduino로의 시리얼 라인; 검증을 위한 `[conveyor_start]` / `[conveyor_stop]` 로그.

### 3.13 Firebase / status bridge

- **패키지/모듈**: `cobot_voice.firebase_bridge` (writer 라이브러리) + `cobot_voice.firebase_status_bridge` (ROS 노드, 실행파일 `firebase_status_bridge`).
- **주요 파일**:
  - `cobot_voice/cobot_voice/firebase_bridge.py` — 백그라운드 큐를 가진 Firestore writer; `DISPLAY_STATES`(음성 흐름)와 `ROBOT_PROGRESS_STATES`(로봇 파이프라인) 어휘 정의; theme 테이블.
  - `cobot_voice/cobot_voice/firebase_status_bridge.py` — `/task/status`, `/task/result`, `/conveyor/place_ready`를 `robot_session/current` 상의 별도 `robot_state` 필드에 매핑하는 ROS 노드.
  - `secrets_4_firebase_config/`의 service-account JSON (`FIREBASE_SERVICE_ACCOUNT` 환경변수). Gitignored.
- **책임**: 두 개의 독립된 필드를 통해 음성 흐름과 로봇 파이프라인 양쪽으로 웹 UI를 동기화하며, 어느 한쪽이 다른 쪽을 막지 않도록 한다. `firebase_admin`이 없거나 자격증명이 실패하면, writer는 조용히 no-op이 되고 ROS 파이프라인은 계속 실행된다.
- **입력**: 음성 흐름 호출(in-process), `/task/status`, `/task/result`, `/conveyor/place_ready`.
- **출력**: Firestore 문서 `robot_session/current`로의 기록.

---

## 4. 데이터 계약

### 4.1 디스크 상의 주문 — `cobot_voice/output/latest_order.json`

이는 음성 파이프라인과 task manager 사이의 파일 계약이다. `cobot_voice.keyword_extractor.build_latest_order_from_recommendation`이 생성하고 `cobot_task_manager.order_provider.FileOrderProvider`가 소비한다.

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

필드 의미:

| 필드 | 타입 | 목적 |
|---|---|---|
| `request_id` | string (`YYYYMMDD_HHMMSS`) | 중복 제거 키; `FileOrderProvider`는 동일 id의 재실행을 거절한다 |
| `recognized_text` | string | 컨디션 + 강도 전사(또는 텍스트 입력)의 연결 |
| `categories` | string array | 결정된 컨디션 카테고리 (아래 네 개 중 하나 이상) |
| `intensity` | string | `low` / `normal` / `high` 중 하나 |
| `combo` | array of `{nut, count}` | 실제 주문 — 로봇이 픽할 대상 |
| `combo_text` | string | TTS / UI를 위한 한국어 확인 문구 |
| `success` | bool | `categories`와 `combo`가 모두 비어 있지 않을 때만 `true`; `FileOrderProvider`는 non-success 주문을 거절한다 |

task manager는 오직 `combo`(클래스별 개수로 매핑)와 `request_id`(idempotency용)만 소비한다. 다른 필드는 웹 UI와 사람의 점검을 위한 것이다.

### 4.2 내부 `OrderBook`

`task_manager_node`는 (`order_provider.py`의) `OrderBook`을 사용해 동작한다:

```python
OrderBook(
    counts={"almond": 2, "cashew": 2, "pistachio": 2, "walnut": 2},
    consecutive_detect_misses={...},
    consecutive_grasp_failures={...},
    skipped=set(),
)
```

`task_manager.yaml`의 `next_class(class_priority)`로 클래스가 선택된다. 픽이 성공할 때마다 `counts`가 감소하며, `max_detect_misses`나 `max_grasp_failures`를 넘기면 클래스가 `skipped`에 추가된다.

> 제안된 스키마 (`{condition, severity, tasks: [...]}`)는 비슷한 동의어이지만, **실제 디스크 스키마는 위의 것이다** — `categories`(복수, 리스트), `intensity`, 그리고 (`nut`과 `count`를 가진) `combo`. 이름을 맞추고 싶다면 rename 가능하지만, 오늘날 런타임이 받아들이는 파일 형식은 위와 같다.

### 4.3 유효한 값

**컨디션 카테고리** (`cobot_voice/config/keyword_categories.json` 출처):

| `category` | 한국어 라벨 | 기본 견과 |
|---|---|---|
| `fatigue` | 피로/회복 | `cashew` |
| `blood_sugar` | 혈당 관리 | `almond` |
| `diet` | 다이어트/체중 | `pistachio` |
| `focus` | 집중/두뇌 | `walnut` |

**강도 레벨** (`cobot_voice/config/nut_combo_rules.json` 출처):

| `intensity` | 카테고리당 개수 |
|---|---|
| `low` | 1 |
| `normal` | 2 |
| `high` | 3 |

`max_total_count = 6`; 여러 카테고리가 cap을 넘기면 `[fatigue, blood_sugar, diet, focus]` 순서로 `reduce_lower_priority_categories_first` 전략이 적용된다.

**견과 종류** (모든 레이어에서 사용):

`almond`, `cashew`, `pistachio`, `walnut`.

이 동일한 네 개의 문자열은 YOLO 클래스명(`cobot_object_detection/config/object_detection.yaml`), 액션의 `target_class` 필드, 그리고 `pick_offsets.yaml`의 키로 사용된다. STT용 한/영 alias는 `cobot_config/config/object_aliases.yaml`과 `cobot_voice/cobot_voice/object_aliases.py`에 있다.

### 4.4 액션 결과 코드 — `cobot_msgs/action/PickAndPlace`

| 코드 | 의미 |
|---|---|
| 0 | ok |
| 1 | approach_fail |
| 2 | grasp_not_detected |
| 3 | motion_fail |
| 4 | safety_stop |
| 5 | workspace_violation |

Feedback `stage` 문자열: `pre_grasp_width`, `approach`, `grasp`, `verify_grip`, `lift`, `transit`, `place`, `retreat`, `home`.

### 4.5 Firestore 문서 — `robot_session/current`

두 개의 독립된 필드가 기록된다:

- `display_state` ∈ `{idle, wake_detected, asking_state, listening_state, asking_intensity, listening_intensity, recommending, result_ready, dispatching, completed, error}` — 음성 흐름이 구동.
- `robot_state` ∈ `{detecting, picking, placing, conveyor_moving, task_done, error}` — `/task/status`, `/task/result`, `/conveyor/place_ready` 엣지로부터 `firebase_status_bridge`가 구동.

기타 필드: `transcript`, `categories`, `intensity`, `combo`, `combo_text`, `confirm_message`, `success`, `theme`, `error`, `updated_at`, 그리고 로봇 진행을 위한 `robot_*` 접두사 필드 (`robot_target_class`, `robot_last_result`, `robot_error`, …).

---

## 5. 하드웨어 아키텍처

### 5.1 토폴로지

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

### 5.2 구성요소

- **Host PC**: Ubuntu 22.04, ROS 2 Humble. 본 repo의 모든 노드, 웹 UI 개발 서버, OpenAI / ElevenLabs HTTP 클라이언트를 실행한다. **본 repo에는 Dockerfile, docker-compose 파일, 컨테이너 manifest가 없다** — 객체 검출, perception, 그리고 그 외 모든 것이 호스트 위에서 ROS 2 노드로 네이티브 실행된다. OD 모델(`experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt`)은 `object_detection_node`가 직접 로드한다.
- **Intel RealSense 카메라**: 상위 `realsense2_camera` 패키지로 `align_depth.enable:=true`, color `1280×720@30`, depth `848×480@30`으로 launch된다. 프레임 id는 `/camera/camera/color/camera_info`에서 온다. `cobot_bringup/launch/perception.launch.py`로 구동된다.
- **Doosan 로봇 암**: `192.168.1.100:12345`의 Doosan M0609 컨트롤러. 상위 `dsr_bringup2` 패키지(`dsr_bringup2_rviz.launch.py` with `gui:=false`)가 띄운다. `DSR_ROBOT2` 파이썬 모듈의 `DR_init` 바인딩이 올바른 rclpy 노드를 찾도록, 우리의 `robot_control_node`는 Doosan 네임스페이스(`dsr01`) **안에서** 동작한다.
- **OnRobot RG2 그리퍼**: `192.168.1.1:502`의 Modbus TCP. 힘 기본값은 `gripper_force_x10: 150` (15 N), 최대 폭은 `gripper_open_width_x10: 1100` (110 mm).
- **컨베이어 / Arduino**: USB로 연결된 Arduino UNO (`/dev/ttyACM0`, 115200 baud). 배선(`conveyor_controller/README.md` 참고): D2=STEP, D3=DIR, D4=ENABLE, GND=드라이버 신호 접지. 스케치: `conveyor_controller/arduino/ConveyorControl_Program/`.
- **네트워크/IP 가정**: run manual은 사전 점검으로 `ping 192.168.1.100`과 `ping 192.168.1.1`을 나열한다. 호스트는 로봇 및 그리퍼와 동일한 `192.168.1.0/24` 서브넷에 있어야 한다.

### 5.3 캘리브레이션 & secret

- `T_gripper2camera.npy` — 필수, 경로는 `perception.yaml`의 `gripper2camera_npy` 파라미터로 전달된다. **이 파일의 사본은 repo에 없다**(의도된 것 — 캘리브레이션은 호스트별이다). 없으면 `perception_transform_node`가 시작 시 raise한다.
- `cobot_voice/resource/.env` — `cobot_voice/resource/.env.example`에서 복사한다. 필수: `OPENAI_API_KEY`. 선택: `FIREBASE_SERVICE_ACCOUNT`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `COBOT_TTS_ENABLED`, `COBOT_TTS_PROVIDER`, `COBOT_VOICE_PROMPT_MODE`.
- `secrets_4_firebase_config/rokey-cobot2-firebase-adminsdk-*.json` — Firebase Admin service-account JSON. Gitignored. 경로는 `FIREBASE_SERVICE_ACCOUNT`에 들어간다.

---

## 6. 안전 설계

이 시스템은 실제 로봇을 의미 있는 속도로 움직일 수 있다. 안전 설계는 계층화되어 있으며, 각 레이어는 다음 레이어와 독립적으로 검증할 수 있다.

### 6.1 Mock / dry-run 모드

`robot_control_node`의 기본 설정은 **mock**이다: `motion_backend: mock`, `gripper_backend: mock`. 이 모드에서 액션 서버는 DSR_ROBOT2나 Modbus를 건드리지 않고, 픽 단계 시퀀스 전체를 완료하고 feedback을 게시하며 성공을 반환한다. `mock_perception_node`는 하드코드된 8-nut 장면을 반환하므로, 카메라와 로봇 없이 task 루프 전체를 검증할 수 있다.

`scripts/pick_one.py --dry-run`은 액션을 *디스패치하지 않고* 보낼 내용을 출력한다. `voice_to_robot.py --no-dispatch`는 `/task/start`를 호출하지 않고 `latest_order.json`만 저장한다.

### 6.2 Real 모드

실 하드웨어 모드는 기본값이 **아니며**, 명시적으로 opt-in해야 한다:

1. `enable_dsr_bringup:=true` 및 `dsr_mode:=real` — Doosan 스택을 켠다.
2. `config_robot_control:=<share>/cobot_robot_control/config/robot_control.real.yaml` — `motion_backend: real`과 `gripper_backend: modbus`로 설정한다. mock 기본 YAML은 그대로 두므로, override를 빠뜨리면 mock으로 fallback한다.

### 6.3 로봇 워크스페이스 가드

워크스페이스 경계(로봇 base 프레임의 mm)는 **두 곳**에서 독립적으로 강제된다:

- `task_manager_node` — `target_selector.choose_target`가 goal을 보내기 전에 `DetectedObjectArray`를 `workspace_xmin/xmax/ymin/ymax/zmin/zmax_mm`로 필터링한다. 현재 `task_manager.yaml`의 z 경계는 depth 드롭아웃 outlier가 거절되도록 `40 ≤ z ≤ 80` mm로 좁혀져 있다.
- `robot_control_node` — 액션 서버의 `motion_sequence.WorkspaceBounds.contains` 검사가 `grasp_xyz` 또는 `return_xyz`가 설정 박스(기본 `200..700 × -300..300 × 0..500` mm)를 벗어나는 모든 goal을 거절한다. `robot_control.yaml`에서 `workspace_enabled: false`로 비활성화 가능하며, 기본은 활성화이다. 위반은 액션을 `failure_code = 5`로 단락시키며 로봇은 절대 움직이지 않는다. 이 두 번째 레이어가 존재하는 이유는 **임의의** 액션 클라이언트가 `/robot/pick_and_place`를 직접 호출할 수 있기 때문이다 — task-manager 단의 필터링만으로는 충분하지 않다.

### 6.4 그리퍼 상태 확인

견과를 클로즈한 뒤, `verify_grip` 단계는 `gripper_controller.wait_until_idle`(busy=True → busy=False — 두 단계 wait는 close가 시작되기 전의 stale "idle"을 읽지 않도록 한다)을 실행한 다음 `is_grip_detected()`를 조회한다. 비트가 set되어 있지 않으면 액션은 `failure_code = 2` (`grasp_not_detected`)를 반환하며 transit **이전에** abort하여, 컨베이어에 아무것도 떨어뜨리지 않는 phantom-grip transit을 방지한다.

### 6.5 Place-ready 트리거

`/conveyor/place_ready` (`std_msgs/Bool`)는 로봇 모션과 컨베이어 모션 사이의 단일 통합 지점이다.

- `robot_control_node`가 `_publish_place_ready`로부터 10 Hz로 게시한다.
- `place` 단계 안에서 TCP가 place y에 도달하고(`place_y_margin_mm` 이내) 그리퍼가 열렸을 때 **True**가 된다.
- `retreat` 시작 시, `pick_and_place` 종료 시, `/robot/stop` 시, 모션 오류 시 다시 **False**로 돌아간다.

### 6.6 컨베이어 트리거 조건

`conveyor_serial_node`는 **오직 False→True 엣지에서만** 벨트를 전진시킨다. True가 유지되어도 재트리거되지 않으며, 활성 실행 중의 두 번째 엣지는 로깅되고 무시된다. 이후 벨트는 `auto_command`(기본 `R80`)를 `auto_run_duration_sec`(기본 `5.0` s) 동안 실행하고, 내부 타이머가 `STOP`을 보낸다. 거리는 시간 기반이며 — 한계는 §7 참고.

### 6.7 실 실행 전 권장 안전 점검

로봇을 켜기 전에:

- **Pendant**: AUTO 모드 + Servo On + 상태 표시등 흰색. 빨간 표시등은 모션 명령을 조용히 실패시킨다(반환값은 success로 읽히지만 암은 움직이지 않는다). 자세한 트러블슈팅 노트는 `docs/03_run_manual.md` §12 참고.
- **워크스페이스 클리어**: 견과가 설정된 워크스페이스 박스 안에 있고, 반환 위치와 컨베이어가 막혀 있지 않은지 물리적으로 확인한다.
- **캘리브레이션 sanity**: `pick_one.py --dry-run <class>`를 실행하고 출력된 `base_xyz`가 합리적으로 보이는지 확인한다. `ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"`를 실행하고 `success: true`와 정상적인 TCP를 확인한다.
- **첫 픽 z**: `pick_one.py --z-override <z>`로 적정 지점을 찾고, `cobot_config/config/pick_offsets.yaml`로 커밋한다. 적어도 한 번의 픽이 성공할 때까지 multi-pick 세션을 시작하지 말 것.
- **E-stop**: pendant E-stop이나 `ros2 service call /robot/stop std_srvs/srv/Trigger {}`를 칠 준비를 한다.
- **Mock 우선**: perception, 모션, task 코드를 변경할 때는 하드웨어를 다시 켜기 전에 mock e2e(full_system with `enable_realsense:=false`, `enable_dsr_bringup:=false`, `gripper_backend`는 mock으로 둠)를 실행한다.

---

## 7. 현재 알려진 갭 / 결정 사항

### 7.1 명시적 메뉴 vs freeform 음성 프롬프트

- **상태**: 두 모드 모두 구현되어 있으며, `voice_order_flow._prompt_mode()`에서 `COBOT_VOICE_PROMPT_MODE` 환경변수로 런타임에 선택된다.
  - `freeform` (기본) — STT 텍스트에 LLM 분석기(`StateAnalyzer`, `IntensityAnalyzer`, gpt-4o)를 사용한다.
  - `menu` — 명시적 번호 메뉴("1번 피로, 2번 혈당, …", "1번 약하게, 2번 보통, 3번 많이")를 안내하고, 숫자 및 한국어 키워드 셋에 대해 regex로 답변을 매칭한다. ASCII 한 자리 토큰은 공백으로 구분된 토큰에 대해 매칭되어 "12"에 우연히 걸리는 것을 방지한다. 한글 숫자(일/이/삼/사) 단독은 흔한 조사와 충돌하므로 의도적으로 매칭하지 않는다. 파싱 미스 시 bail 전에 한 번의 재시도를 제공한다.
- 메뉴 매칭이 재시도에서도 미스이면, 음성 흐름은 LLM 분석으로 fallback한다.

### 7.2 컨베이어 동작 의미론

- **상태**: `/conveyor/place_ready`의 False→True 엣지에 의해 트리거되는 **시간 기반 one-shot**으로 구현되어 있다. 한 번의 엣지 → `auto_command`(기본 `R80`) `auto_run_duration_sec`(기본 `5.0` s) 동안 → `STOP`. True가 유지되어도 재트리거되지 않는다.
- **한계**(`conveyor_controller/README.md`에 명시): 거리는 근사적이며 결정적이지 않다. 스텝 모드 펌웨어(`S<N>` 명령 + ack)는 **future work / TODO**로 문서화되어 있으며 의도적으로 범위 밖이다.

### 7.3 Firestore / 웹 로봇 진행 브릿지

- **상태**: `firebase_status_bridge` (`cobot_voice.firebase_status_bridge`, 실행파일 `firebase_status_bridge`)에 의해 구현되어 있으며, `cobot_bringup/launch/host_system.launch.py`에서 기본 launch된다(toggle: `enable_firebase_status_bridge`, 기본 `true`). `/task/status`, `/task/result`, 그리고 `/conveyor/place_ready`의 False→True 엣지를 `robot_session/current`의 `robot_state` 필드로 미러링하며, 음성 흐름의 `display_state` 필드는 그대로 둔다.
- **한계**(모듈 docstring에 명시): 액션 서버가 단계별 진행을 외부에 노출하지 않으므로, `placing`은 `conveyor_moving`을 발사하는 동일 엣지에서 추론된다. 두 상태는 writer 큐를 통해 연달아 emit된다.
- **실패 모드**: `firebase_admin`이나 자격증명이 없으면, writer는 내부 플래그를 뒤집고 조용히 no-op이 된다. 로봇 파이프라인은 영향을 받지 않는다.

### 7.4 `command_parser_node` 상태

- **상태**: 제거됨. dead code(`command_parser_node`, `firebase_state_bridge`)는 voice→robot 통합 cleanup의 일환으로 삭제되었다. 오늘날 이 repo에는 `/voice/text` 소비자가 없다.
- `voice_processing_node` 실행파일(`voice_processing` entry point)은 여전히 `cobot_voice/setup.py`에 존재하며 `/voice/text`와 `/voice/status`를 게시하지만, **트리 안의 어떤 노드도 그 토픽들을 구독하지 않는다**. 프로덕션 음성 경로는 `voice_to_robot.py` → `voice_order_flow.run_recommendation_flow` → `task_manager_dispatcher.dispatch_to_task_manager`이며, in-process로 동작하며 음성→주문 단계에서 ROS 토픽을 우회한다. `voice_processing_node`는 legacy로 취급할 것.

### 7.5 클래스별 Z-offset 설정

- **상태**: 단일 진실 공급원은 `cobot_config/config/pick_offsets.yaml`이다:
  ```yaml
  per_class_z_offset_mm:
    almond: 0.0
    cashew: 0.0
    pistachio: 0.0
    walnut: -1.0
  ```
- **로더**: `cobot_task_manager.pick_offsets.load_pick_offsets`는 다음 순서로 resolve한다: 명시적 path 파라미터 → `COBOT_PICK_OFFSETS_PATH` 환경변수 → ament-share lookup → source-tree fallback → 빌트인 기본값.
- **적용 시점**: **픽 단계에서만** 적용된다(`goal.grasp_xyz.z`에 더해진다). 플레이스 / 반환에서는 적용되지 않는다.
- **운영자 노트**: `scripts/pick_one.py`와 `scripts/pick_all.py`도 각 파일 상단에 `PER_CLASS_Z_OFFSET` dict를 가지고 있다. `scripts/pick_one.py`는 현재 모두 0이므로, 스크립트 모드 픽은 `walnut: -1.0`을 자동으로 가져오지 않는다. 스크립트가 YAML을 읽도록 마이그레이션해야 하는지 **검증 필요** — 이번 작업의 요청은 문서화이지 코드 수정이 아니었기 때문에 변경하지 않았다.

### 7.6 알아둘 만한 기타 갭

- **`cobot_safety` 및 `cobot_policy`** — 두 패키지 모두 빈 `*.py` 파일과 함께 존재한다. `setup.py`는 `safety_manager`와 `policy_selector` entry point를 노출하지만, 모듈에는 코드가 없다. **Not Implemented**; 어떤 launch 파일도 참조하지 않는다.
- **`/db/get_nut_order`** — `cobot_msgs/srv/GetNutOrder`가 정의되어 있고 `DBOrderProvider`가 배선되어 있지만, **이 repo에는 서비스 서버가 구현되어 있지 않다**. `order_source:=db`로 설정하면 timeout된다.
- **`cobot_config/config/{slot_poses,policy_config,workspace}.yaml`** — 정의되어 있지만 어떤 런타임 노드도 로드하지 않는다. 실제 워크스페이스 경계는 `task_manager.yaml`과 `robot_control.yaml`의 파라미터 블록에 있다; config 패키지의 YAML들은 **현재 사용되지 않는다**. 제거할지 또는 wire-in할지 **검증 필요**.
- **`cobot_bringup/config/params.yaml`** — 시스템 파라미터(ROS_DOMAIN_ID, RMW, robot host/port). `cobot_bringup/launch/`의 어떤 launch 파일도 **로드하지 않는다**. wire-in 될 때까지 참고용으로 취급할 것.
- **마이크 디바이스 인덱스** — `cobot_voice.mic_controller.MicConfig`에 `6`으로 하드코드되어 있다. 호스트별로 **검증 필요**; 오늘날 환경변수 override는 없다.
- **워크스페이스 경계 중복** — `task_manager.yaml`과 `robot_control.yaml`에 중복되어 있다. 수동으로 동기화를 유지해야 하며, 오늘날 패키지 간 검증은 없다.

---

## 부록 — 깊이 있는 맥락을 위해 읽을 파일

위에 기술된 런타임 동작에 대해:

- 최상위 launch: `cobot_bringup/launch/full_system.launch.py`, `host_system.launch.py`, `perception.launch.py`, `robot.launch.py`.
- Task 루프: `cobot_task_manager/cobot_task_manager/task_manager_node.py` (`_run` 메서드)와 `target_selector.py`, `retry_policy.py`.
- 액션 서버 + helper 노드 근거: `cobot_robot_control/cobot_robot_control/robot_control_node.py` (175–260 라인).
- 픽 단계 + 워크스페이스 가드: `cobot_robot_control/cobot_robot_control/motion_sequence.py`.
- 검출 → base 프레임 변환: `cobot_perception/cobot_perception/perception_transform_node.py` (`_handle_detect_once`).
- 음성 상태머신: `cobot_voice/cobot_voice/voice_order_flow.py` (`run_recommendation_flow`, `_prompt_mode`, `_match_menu_choice`).
- 주문 JSON shape: `cobot_voice/cobot_voice/keyword_extractor.py` (`build_latest_order_from_recommendation`, `normalize_combo`).
- 컨베이어 엣지 의미론: `conveyor_controller/README.md`.

동반 실행 순서 문서는 `docs/03_run_manual.md`이다. 사전 점검 테스트 체크리스트는 `docs/04_validation_checklist.md`이다.
