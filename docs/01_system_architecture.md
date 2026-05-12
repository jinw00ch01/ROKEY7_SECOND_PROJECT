# 시스템 아키텍처

이 문서는 `cobot2_ws` 워크스페이스의 최종 상태를 기술한다. 시스템이 무엇을 하는지, 그것을 가능하게 하는 런타임 구성요소, 그들 간의 데이터 계약, 기대되는 하드웨어, 그리고 안전 설계를 다룬다. 이 문서는 시스템을 실행하기 **전에** 이해해야 하는 팀원을 위해 작성되었다.

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
| `docs/01_system_architecture.md` (이 파일) | 시스템이 무엇을 하는지와 그 이유 (**Supabase 경로 기준**) |
| `docs/02_ros_node_architecture.md` | 노드별 ROS 인터페이스 레퍼런스 |
| `docs/03_run_manual.md` | 단계별 운영자 실행 순서 |
| `docs/09_supabase_migration.md` | Supabase 스키마/RLS/RPC 레퍼런스 |
| `docs/cleanup_deletion_proposal.md` | 아카이브되었거나 제거 대상으로 표시된 파일에 대한 삭제 계획 |
| `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` | cleanup 배치별 manifest — 아카이브된 모든 파일에 대한 사유 / 근거 / 리스크 |

> **백엔드 선택**: 영속화/실시간 동기화는 **Supabase**(Postgres + Realtime + RPC)가 최종 결정 사항이다. 디폴트 launch (`bringup_supabase`, `full_system.launch.py`, `host_system.launch.py`)는 Supabase 브릿지를 켠 채로 시작한다. 본문은 Supabase 경로만 기술한다.

설계 이력 파일들은 위 문서 세트로 **대체**되어 `docs/_archive/`로 이전되었다. 이력 보존을 위해 git 트리에 남아 있지만 오래된 경로(`~/cobot_ws/...` vs 실제 `~/cobot2_ws/...`), 구식 캘리브레이션 값, 그리고 현재 구조와 다른 과거 통합 설명을 포함한다. 1차 레퍼런스로 사용하지 말 것.

`_archive_cleanup/<YYYYMMDD>/` 디렉토리(현재 `20260508/`)는 **활성 코드가 아니다**. 삭제 결정 보류 중인 파일들을 런타임 트리 밖으로 옮겨 보관한다. 거기에서 `source`, `colcon build`, `import` 또는 다른 어떤 실행도 하지 말 것. 아카이브의 목적은 활성 트리를 깨끗하게 유지하면서 git history를 보존하는 것이다. 삭제 계획은 `docs/cleanup_deletion_proposal.md`를 참고할 것.

---

## 1. 프로젝트 목표

이 시스템은 Doosan M0609 6-DOF cobot에 OnRobot RG2 그리퍼, Intel RealSense 카메라, 그리고 Arduino로 제어되는 stepper 컨베이어를 결합한, 음성 기반 견과류 픽 앤 플레이스 데모이다.

완전한 사용자 상호작용은 다음과 같다.

1. 사용자가 `web_stt_supabase_v2` 웹 UI를 열고 음성 세션을 시작한다.
2. 브라우저 음성 파이프라인이 wake word를 감지한 다음, 사용자에게 (TTS로) **직업**("당신의 직업은 무엇인가요?")과 **포만감**("현재 포만감은 어느 정도인가요?")을 묻는다.
3. 사용자는 음성으로 답하고, STT(Whisper)가 각 답변을 전사한다.
4. 직업 분석기가 추천 견과류 목록을 만들고, 포만감 분석기가 `low`/`normal`/`high` 중 하나로 매핑한다.
5. 콤보 룰 엔진이 견과류 개수 리스트(**주문**)를 생성하고, Supabase `robot_session.current` 행에 upsert하며, 웹 UI는 Realtime `postgres_changes` 구독으로 즉시 갱신된다.
6. `task_manager_node`가 `/task/start` 호출을 받으면 `SupabaseOrderProvider`로 `robot_session.current`의 `combo`/`request_id`를 읽어 주문 큐를 만든다. 동일한 `request_id`는 재실행되지 않는다.
7. 주문에 남은 각 견과류에 대해, task manager는 `/perception/detect_once`를 호출하고 워크스페이스 내에서 요청된 클래스의 최선 후보를 픽한 뒤 `/robot/pick_and_place` 액션 goal을 보낸다.
8. `robot_control_node`는 픽 단계(approach → grasp → verify_grip → lift → transit → place → retreat → home)를 실행하고, 플레이스 자세에서 RG2 그리퍼를 열고 `/conveyor/place_ready`를 assert한다.
9. 컨베이어 노드는 그 **False → True** 엣지를 한 번의 시간 기반 벨트 전진으로 변환한 뒤 정지하여, 다음 견과류를 받을 준비를 한다.
10. 주문이 비면 task manager가 `/task/status`와 `/task/result`에 `done`을 게시하고, `supabase_status_bridge`가 이를 `robot_session.current.robot_state`로 미러링한다. 픽 성공 시마다 `cobot_db`가 RPC `update_inventory_atomic`으로 재고를 차감하고 `inventory_logs`에 append한다. 픽 실패/검증 실패는 `exception_logs`에 적재된다.

---

## 2. End-to-End 흐름

```
            ┌─────────────────────────┐
            │  Web UI / Start         │  React 19 + Vite + Three.js
            │  (web_stt_supabase_v2)  │  Browser voice flow +
            │                         │  supabase.channel('robot_session')
            └─────────┬───────────────┘
                      │ supabase.from('robot_session').upsert({id:'current', ...})
                      │   (브라우저 → Postgres 직접 write, anon publishable key)
                      ▼
┌────────────────────────────────────────────┐
│ Supabase (Postgres + Realtime + RPC)       │
│   robot_session.current  (단일 행)          │
│   inventory / inventory_logs               │
│   exception_logs                           │
│   RPC update_inventory_atomic              │
└────────┬───────────────────────────────────┘
         │ Realtime postgres_changes
         ▼ (UI 즉시 반영)
            ┌─────────────────────────┐
            │  Web UI 렌더링          │
            └─────────────────────────┘

(브라우저-측 음성 흐름)
        ┌─────────────────────────────┐
        ▼                             ▼
┌──────────────────┐         ┌──────────────────┐
│  MediaRecorder + │         │  TTS (브라우저)  │
│  Whisper STT     │         │  ElevenLabs +    │
│                  │         │  speechSynthesis │
└────────┬─────────┘         └──────────────────┘
         │ job text + satiety text
         ▼
┌────────────────────────────────────────────┐
│ Job/Satiety 분석 + Combo 룰 (브라우저 측)   │
│   src/lib/voice/llm.ts                     │
│   src/lib/voice/recommendation.ts          │
│   추천 견과류, 포만감별 개수, combo         │
└────────┬───────────────────────────────────┘
         │ {categories, intensity, combo, request_id}
         ▼
┌────────────────────────────────────────────┐
│ supabase.upsert(robot_session.current)     │
│   success=true, combo=[...]                │
└────────┬───────────────────────────────────┘
         │ rosbridge 또는 운영자: /task/start
         ▼
┌────────────────────────────────────────────┐
│  ROS Task Manager  (task_manager_node)     │
│   SupabaseOrderProvider 가 robot_session    │
│     읽어 OrderBook 생성                     │
│   loop:                                    │
│     /perception/detect_once  ──┐           │
│     target_selector            │           │
│     /robot/pick_and_place ◄────┘           │
│   /task/status, /task/result publishes     │
│   픽 성공 → cobot_db.update_inventory(-1)   │
│   픽 실패 → cobot_db.log_robot_exception()  │
└────────┬─────────────────────────┬─────────┘
         │                         │ status/result
         ▼                         ▼
┌────────────────────────┐ ┌────────────────────────┐
│ Perception /           │ │ supabase_status_bridge │
│ Object Detection       │ │ /task/status,          │
│  realsense2_camera     │ │ /task/result,          │
│  object_detection_node │ │ /conveyor/place_ready  │
│  perception_transform_ │ │   → robot_session.     │
│  node                  │ │     robot_state 필드   │
└────────┬───────────────┘ └────────────────────────┘
         │ DetectedObjectArray (base-frame xyz, grasp yaw, mm sizes)
         ▼
┌────────────────────────────────────────────┐
│  Robot Arm + Gripper (robot_control_node)  │
│   pick_and_place stages:                   │
│     pre_grasp_width → approach → grasp     │
│     → verify_grip → lift → transit         │
│     → place → retreat → home               │
│   Doosan DSR_ROBOT2                         │
│   OnRobot RG2 via Modbus TCP                │
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

- **패키지/모듈**: `web_stt_supabase_v2/` (Vite + React 19 + Three.js + `@supabase/supabase-js`). 워크스페이스 루트에 위치하며 `COLCON_IGNORE`가 적용되어 있다.
- **주요 파일**: `src/App.tsx`, `src/components/`, `src/hooks/useRobotSession.ts`, `src/lib/supabase.ts`, `src/lib/voice/orchestrator.ts`, `src/lib/voice/session.ts`, `package.json`.
- **책임**: 데모 상태(`idle`, `wake_detected`, `asking_job`, `listening_job`, `transcribing_job`, `asking_satiety`, `listening_satiety`, `transcribing_satiety`, `recommending`, `result_ready`, `dispatching`, `completed`, `error`)를 렌더링한다. 브라우저에서 wake-word, 마이크 녹음, STT, LLM 분석, TTS, 주문 publish까지 처리한다.
- **입력**: Supabase `robot_session` 테이블의 `id='current'` 행. 첫 렌더에서 `select(...).maybeSingle()`로 현재 값을 읽고, 이후 Realtime `postgres_changes` 채널을 구독한다.
- **출력**: `supabase.from('robot_session').upsert({id:'current', ...}, {onConflict:'id'})`. `VITE_ROSBRIDGE_URL`이 설정되어 있으면 `rosbridge_websocket`을 통해 `/task/start`도 호출한다.

### 3.2 TTS

- **패키지/모듈**: `web_stt_supabase_v2/src/lib/voice/tts.ts` (브라우저 in-process).
- **주요 파일**: `web_stt_supabase_v2/src/lib/voice/tts.ts`, `web_stt_supabase_v2/public/config/question_flow.json`.
- **책임**: 한국어 프롬프트와 최종 확인 메시지를 음성으로 출력한다. `VITE_ELEVENLABS_API_KEY`가 있으면 ElevenLabs TTS를 호출하고, 인증/쿼터/네트워크 실패 또는 키 미설정 시 브라우저 `speechSynthesis`로 fallback한다.
- **입력**: `question_flow.json`의 프롬프트 문자열과 계산된 콤보 텍스트.
- **출력**: 브라우저 오디오 출력.

### 3.3 STT

- **패키지/모듈**: `web_stt_supabase_v2/src/lib/voice/recorder.ts`, `whisper.ts`, `wakeWord.ts` (브라우저 in-process).
- **주요 파일**: `web_stt_supabase_v2/src/lib/voice/orchestrator.ts`, `recorder.ts`, `whisper.ts`, `wakeWord.ts`.
- **책임**: Web Speech API로 wake word("샤갈", "hello rokey" 등)를 감지한 뒤, `MediaRecorder`로 5초 오디오를 캡처하고 OpenAI Whisper API로 전사한다. Wake-word는 Chrome/Edge의 `SpeechRecognition`/`webkitSpeechRecognition`에 의존한다.
- **입력**: 브라우저 마이크 권한과 `VITE_OPENAI_API_KEY`.
- **출력**: 전사된 한국어 텍스트.

### 3.4 키워드 추출 / 추천

- **패키지/모듈**: `web_stt_supabase_v2/src/lib/voice` (브라우저 in-process; ROS 인터페이스 없음).
- **주요 파일**:
  - `orchestrator.ts` — 최상위 상태머신 (wake → ask job → STT → job analysis → ask satiety → STT → satiety analysis → combo → Supabase publish → optional dispatch).
  - `llm.ts` — `analyzeJob`, `analyzeSatiety`, menu mode matcher. OpenAI `gpt-4o` Chat Completions를 JSON 모드로 호출한다.
  - `recommendation.ts` — 추천 견과류 목록 + 포만감(`Intensity`)을 `combo`로 변환하고 한국어 콤보 텍스트를 만든다.
  - `public/config/nut_combo_rules.json` — 포만감별 개수(`low=3`, `normal=2`, `high=1`)와 `max_total_count`.
  - `public/config/question_flow.json` — 한국어 TTS 프롬프트.
  - `session.ts` — Supabase `robot_session.current` write, completion wait, error/idle reset.
- **책임**: 두 개의 STT 텍스트를 `(categories, intensity, combo)` 주문으로 변환한다. 여기서 `categories`는 과거 컨디션 카테고리가 아니라, 웹 타입 기준 `NutClass[]`(추천된 견과류 이름 목록)이다. 두 가지 프롬프트 모드는 `VITE_PROMPT_MODE`로 선택된다 (§7 참고):
  - `freeform` (기본) — LLM 분석기.
  - `menu` — 직업 4종/포만감 3종 메뉴와 regex 매칭.
- **입력**: 두 개의 STT 전사(직업 + 포만감).
- **출력**: Supabase `robot_session.current`에 기록되는 주문 dict.

### 3.5 주문 provider / 데이터베이스

- **패키지/모듈**: `cobot_task_manager.order_provider`.
- **주요 파일**: `cobot_task_manager/cobot_task_manager/order_provider.py`, `cobot_db/cobot_db/cobot_db_manager.py`, `cobot_db/sql/init.sql`.
- **책임**: `task_manager_node`에 `OrderBook`을 제공한다. Supabase 경로의 provider는 `SupabaseOrderProvider`이며, `CobotDbManager.read_robot_session()`으로 Supabase `robot_session.current` 행을 읽고 `success=true`, non-empty `combo`, 새 `request_id`일 때만 주문으로 변환한다. `bringup_supabase.launch.py`의 기본값은 `order_source:=supabase`이다.
- **입력**: Supabase `robot_session.current` 단일 행.
- **출력**: task 루프에서 소비되는 `OrderBook` (`{class: count}`).
- **영속화**: `cobot_db`는 같은 Supabase 프로젝트의 `inventory`, `inventory_logs`, `exception_logs`, `robot_session`을 다룬다. 픽 성공은 RPC `update_inventory_atomic`으로 재고 차감 + 로그 append를 한 트랜잭션으로 처리한다.

### 3.6 Task manager

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

### 3.7 객체 검출

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

### 3.8 Perception transform

- **패키지/모듈**: `cobot_perception.perception_transform_node` (실행파일 `perception_transform_node`).
- **주요 파일**:
  - `cobot_perception/cobot_perception/perception_transform_node.py`
  - `cobot_perception/cobot_perception/depth_filter.py` (OBB 내부의 median)
  - `cobot_perception/cobot_perception/handeye_transform.py` (`load_gripper2camera`, `tcp_to_base2gripper`, `compose_base2camera`, `transform_camera_to_base`).
  - `cobot_perception/cobot_perception/grasp_pose_generator.py` (`yaw_from_obb`).
  - `cobot_perception/config/perception.yaml`.
- **책임**: 매 `/perception/detect_once` 호출마다 최신 검출 결과를 가져와 각 OBB 내부의 median depth를 조회하고, 핀홀 모델로 카메라 프레임으로 lift하며, `T_gripper2camera.npy`를 사용해 로봇 base 프레임으로 변환하고, OBB theta로부터 `grasp_yaw`를 계산하며, 물리 OBB 사이즈(`short_axis_mm`, `long_axis_mm`)를 emit한다. TCP 소스는 선택 가능하다: `fixed`(선언된 파라미터) 또는 `service`(`/robot/get_current_pose` 호출). `cobot_perception/config/perception.yaml`의 기본값은 `service`이다.
- **입력**: `/detection/objects`, `/camera/camera/aligned_depth_to_color/image_raw`, `/camera/camera/color/camera_info`, `T_gripper2camera.npy` (`gripper2camera_npy`로 경로 필수), 그리고 `fixed_tcp_*` 파라미터 또는 pose 서비스.
- **출력**: `transform_valid=true`로 채워진 항목을 가진 `/perception/detect_once` (`cobot_msgs/srv/DetectOnce`) 응답.

### 3.9 로봇 제어

- **패키지/모듈**: `cobot_robot_control.robot_control_node` (실행파일 `robot_control_node`).
- **주요 파일**:
  - `cobot_robot_control/cobot_robot_control/robot_control_node.py` — 액션 서버, home/stop 서비스, pose passthrough, place_ready 게시자. 액션 트래픽과 pose 조회가 DSR_ROBOT2 spin 경합으로 starve되지 않도록, 전용 multi-threaded executor에서 동작하는 두 개의 추가 in-process helper 노드(`robot_action_helper`, `robot_pose_helper`)를 사용한다.
  - `cobot_robot_control/cobot_robot_control/motion_sequence.py` — 단계 시퀀스(`pre_grasp_width`, `approach`, `grasp`, `verify_grip`, `lift`, `transit`, `place`, `retreat`, `home`)와 워크스페이스 가드.
  - `cobot_robot_control/cobot_robot_control/doosan_motion_client.py` — DSR_ROBOT2 wrapper.
  - `cobot_robot_control/cobot_robot_control/pose_converter.py` — point/yaw 및 ZYZ ↔ Doosan posx 변환.
  - `cobot_robot_control/config/robot_control.real.yaml` — 실 하드웨어 설정.
- **책임**: 로봇을 소유한다. `/robot/pick_and_place` (액션), `/robot/home`, `/robot/stop`, `/robot/get_current_pose` (서비스)를 제공한다. `/conveyor/place_ready`를 10 Hz로 엣지 업데이트와 함께 게시한다.
- **입력**: 액션 goal, 서비스, 그리고 기본 Doosan 네임스페이스(`dsr01`).
- **출력**: 액션 결과 + feedback, place_ready 토픽, Doosan 컨트롤러로의 모션.

### 3.10 그리퍼 제어

- **패키지/모듈**: 별도의 노드가 아니라 `cobot_robot_control` 내부에 위치한다.
- **주요 파일**: `cobot_robot_control/cobot_robot_control/gripper_controller.py`.
- **책임**: 세 가지 구현을 가진 플러그형 백엔드(`Protocol`):
  - Modbus RG2 백엔드 — `192.168.1.1:502`의 Modbus TCP, `force_x10`과 `max_width_x10` 파라미터(기본값 150 → 15 N, 1100 → 110 mm).
  - Tool DIO 백엔드 — 인터페이스 스텁만 존재; 오늘 기준 **Not Implemented**.
  - `wait_until_idle` 두 단계 wait(busy=True → busy=False)는 `verify_grip` 단계에서 사용된다.
- **입력**: `motion_sequence`로부터의 width/open/close 호출.
- **출력**: 물리 그리퍼 모션 + verify를 위한 `is_grip_detected()`.

### 3.11 컨베이어 제어

- **패키지/모듈**: `conveyor_controller.conveyor_serial_node` (실행파일 `conveyor_serial_node`). 펌웨어: `arduino/ConveyorControl_Program/`.
- **주요 파일**:
  - `conveyor_controller/conveyor_controller/conveyor_serial_node.py`
  - `conveyor_controller/launch/conveyor_controller.launch.py`
  - `conveyor_controller/config/conveyor_controller.yaml`
  - `conveyor_controller/README.md`
- **책임**: `/conveyor_cmd` (`std_msgs/String`, 값은 `F1`–`F100`, `R1`–`R100`, `STOP`)을 구독하여 줄바꿈으로 종료된 시리얼 라인으로 전달한다. `/conveyor/place_ready` (`std_msgs/Bool`)을 구독하고, 매 **False → True 엣지**마다 `auto_command`(기본 `R80`)를 `auto_run_duration_sec`(기본 `5.0` s) 동안 송신한 뒤 `STOP`을 보낸다. 활성 실행 중의 두 번째 엣지는 로깅되고 무시된다.
- **입력**: `/conveyor_cmd`, `/conveyor/place_ready`, `/dev/ttyACM0` 115200 baud의 Arduino.
- **출력**: Arduino로의 시리얼 라인; 운영 확인을 위한 `[conveyor_start]` / `[conveyor_stop]` 로그.

### 3.12 Supabase / status bridge

- **패키지/모듈**: `cobot_voice.supabase_status_bridge` (ROS 노드, 실행파일 `supabase_status_bridge`) + `cobot_db.CobotDbManager` (writer 라이브러리).
- **주요 파일**:
  - `cobot_voice/cobot_voice/supabase_status_bridge.py` — `/task/status`, `/task/result`, `/conveyor/place_ready`를 `robot_session.current.robot_state`와 관련 `robot_*` 필드에 매핑하는 ROS 노드.
  - `cobot_db/cobot_db/cobot_db_manager.py` — Supabase lazy client, `set_robot_state`, `read_robot_session`, `update_inventory`, `log_robot_exception`.
  - `cobot_db/sql/init.sql` — `robot_session`, `inventory`, `inventory_logs`, `exception_logs`, RLS, Realtime publication, `update_inventory_atomic` RPC.
- **책임**: 웹 음성 흐름(`display_state`)과 로봇 파이프라인(`robot_state`)을 같은 Supabase 단일 행 위에서 분리해 동기화한다. Supabase 의존성이나 자격증명이 없으면 bridge는 warning만 남기고 no-op이 되며, 로봇 파이프라인은 계속 실행된다.
- **입력**: `/task/status`, `/task/result`, `/conveyor/place_ready`.
- **출력**: Supabase `robot_session` 테이블의 `id='current'` 행으로의 upsert.

---

## 4. 데이터 계약

### 4.1 Supabase 세션 행 — `robot_session.current`

Supabase 기본 경로의 중심 계약은 Postgres `robot_session` 테이블의 단일 행이다. `id='current'` CHECK 제약으로 singleton 운영을 강제한다. `web_stt_supabase_v2`가 음성 흐름과 주문 필드를 쓰고, `supabase_status_bridge`가 로봇 진행 필드를 쓴다.

주요 필드:

| 필드 | 타입 | 작성자 | 목적 |
|---|---|---|---|
| `id` | text | seed/upsert | 항상 `current` |
| `display_state` | text | 웹 음성 흐름 | UI 음성 단계 |
| `question` | text | 웹 음성 흐름 | 현재 사용자에게 안내 중인 문장 |
| `transcript` | text | 웹 음성 흐름 | 직업 + 포만감 전사 텍스트 |
| `categories` | jsonb array | 웹 음성 흐름 | 웹 타입 기준 `NutClass[]`; 추천된 견과류 목록 |
| `intensity` | text | 웹 음성 흐름 | 포만감 레벨: `low` / `normal` / `high` |
| `combo` | jsonb array | 웹 음성 흐름 | 실제 주문: `[{nut, count}, ...]` |
| `combo_text` | text | 웹 음성 흐름 | TTS/UI용 한국어 콤보 문구 |
| `confirm_message` | text | 웹 음성 흐름 | 최종 확인 문장 |
| `success` | boolean | 웹 음성 흐름 | `SupabaseOrderProvider`가 주문 수락 여부 판단에 사용 |
| `theme` | jsonb | 웹 음성 흐름 | Three.js 화면 색상/테마 |
| `error` | text | 웹/bridge | 사용자 표시용 오류 |
| `robot_state` | text/null | `supabase_status_bridge` | 로봇 진행 상태 |
| `robot_target_class` | text/null | `supabase_status_bridge` | 현재 픽 대상 |
| `request_id` | text/null | 웹 음성 흐름 | 중복 실행 방지 키 |
| `updated_at` | timestamptz | DB trigger | `touch_updated_at`가 서버에서 갱신 |

`display_state` 값:

`idle`, `wake_detected`, `asking_job`, `listening_job`, `transcribing_job`, `asking_satiety`, `listening_satiety`, `transcribing_satiety`, `recommending`, `result_ready`, `dispatching`, `completed`, `error`.

`robot_state` 값:

`detecting`, `picking`, `placing`, `conveyor_moving`, `task_done`, `error`.

`SupabaseOrderProvider`는 오직 `combo`, `success`, `request_id`만 로봇 실행 판단에 사용한다. `success=false`, 빈 `combo`, 이전에 처리한 `request_id`는 거절한다.

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

### 4.3 유효한 값

**추천 견과류 / `categories`** (`web_stt_supabase_v2/src/lib/types.ts` 기준):

Supabase 웹 경로에서 `categories`는 `NutClass[]`이며 의미는 "추천된 견과류 목록"이다.

`almond`, `cashew`, `pistachio`, `walnut`.

**포만감 / 강도 레벨** (`web_stt_supabase_v2/public/config/nut_combo_rules.json` 출처):

| `intensity` | 의미 | 견과류당 개수 |
|---|---|---|
| `low` | 포만감 낮음 / 배고픔 | 3 |
| `normal` | 보통 | 2 |
| `high` | 포만감 높음 / 배부름 | 1 |

웹 설정의 `max_total_count = 20`이지만, 현재 `recommendation.ts`의 `buildCombo()`는 추천된 각 견과류에 포만감별 개수를 곱해 `combo`를 만들며 별도 cap/reduction 단계는 적용하지 않는다.

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

---

## 5. 하드웨어 아키텍처

### 5.1 토폴로지

```
                         Host PC (Ubuntu 22.04 + ROS 2 Humble)
   ┌───────────────────────────────────────────────────────────┐
   │  ROS 2 nodes (this repo)                                  │
   │  Web UI (Vite dev server + browser voice flow)             │
   │  ROS nodes + cobot_db Supabase client                      │
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

- **Host PC**: Ubuntu 22.04, ROS 2 Humble. 본 repo의 모든 ROS 노드, 웹 UI 개발 서버, 브라우저 기반 OpenAI/ElevenLabs 클라이언트, Supabase 클라이언트를 실행한다. **본 repo에는 Dockerfile, docker-compose 파일, 컨테이너 manifest가 없다** — 객체 검출, perception, 그리고 그 외 모든 것이 호스트 위에서 ROS 2 노드로 네이티브 실행된다. OD 모델(`experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt`)은 `object_detection_node`가 직접 로드한다.
- **Intel RealSense 카메라**: 상위 `realsense2_camera` 패키지로 `align_depth.enable:=true`, color `1280×720@30`, depth `848×480@30`으로 launch된다. 프레임 id는 `/camera/camera/color/camera_info`에서 온다. `cobot_bringup/launch/perception.launch.py`로 구동된다.
- **Doosan 로봇 암**: `192.168.1.100:12345`의 Doosan M0609 컨트롤러. 상위 `dsr_bringup2` 패키지(`dsr_bringup2_rviz.launch.py` with `gui:=false`)가 띄운다. `DSR_ROBOT2` 파이썬 모듈의 `DR_init` 바인딩이 올바른 rclpy 노드를 찾도록, 우리의 `robot_control_node`는 Doosan 네임스페이스(`dsr01`) **안에서** 동작한다.
- **OnRobot RG2 그리퍼**: `192.168.1.1:502`의 Modbus TCP. 힘 기본값은 `gripper_force_x10: 150` (15 N), 최대 폭은 `gripper_open_width_x10: 1100` (110 mm).
- **컨베이어 / Arduino**: USB로 연결된 Arduino UNO (`/dev/ttyACM0`, 115200 baud). 배선(`conveyor_controller/README.md` 참고): D2=STEP, D3=DIR, D4=ENABLE, GND=드라이버 신호 접지. 스케치: `conveyor_controller/arduino/ConveyorControl_Program/`.
- **네트워크/IP 가정**: 호스트는 로봇 및 그리퍼와 동일한 `192.168.1.0/24` 서브넷에 있어야 하며, 로봇 `192.168.1.100`과 그리퍼 `192.168.1.1`에 도달 가능해야 한다.

### 5.3 캘리브레이션 & secret

- `T_gripper2camera.npy` — 필수, 경로는 `perception.yaml`의 `gripper2camera_npy` 파라미터로 전달된다. **이 파일의 사본은 repo에 없다**(의도된 것 — 캘리브레이션은 호스트별이다). 없으면 `perception_transform_node`가 시작 시 raise한다.
- `cobot_db/.env` — Supabase ROS/Python 클라이언트용. 필수: `SUPABASE_URL`, `SUPABASE_KEY`. `bringup_supabase.launch.py`는 기본적으로 이 파일을 읽어 launch process 환경변수로 주입한다(`db_env_path`로 override 가능).
- `web_stt_supabase_v2/.env` — 브라우저/Vite용. 필수: `VITE_SUPABASE_URL`, `VITE_SUPABASE_KEY`, `VITE_OPENAI_API_KEY`. 선택: `VITE_ELEVENLABS_API_KEY`, `VITE_PROMPT_MODE`, `VITE_TTS_ENABLED`, `VITE_ROSBRIDGE_URL`.

---

## 6. 안전 설계

이 시스템은 실제 로봇을 의미 있는 속도로 움직일 수 있다. 안전 설계는 계층화되어 있으며, 각 레이어는 다음 레이어와 독립적으로 검증할 수 있다.

### 6.1 Real 모드

실 하드웨어 실행은 명시적으로 opt-in해야 한다:

1. `enable_dsr_bringup:=true` 및 `dsr_mode:=real` — Doosan 스택을 켠다.
2. `config_robot_control:=<share>/cobot_robot_control/config/robot_control.real.yaml` — `motion_backend: real`과 `gripper_backend: modbus`로 설정한다.

### 6.2 로봇 워크스페이스 가드

워크스페이스 경계(로봇 base 프레임의 mm)는 **두 곳**에서 독립적으로 강제된다:

- `task_manager_node` — `target_selector.choose_target`가 goal을 보내기 전에 `DetectedObjectArray`를 `workspace_xmin/xmax/ymin/ymax/zmin/zmax_mm`로 필터링한다. 현재 `task_manager.yaml`의 z 경계는 depth 드롭아웃 outlier가 거절되도록 `40 ≤ z ≤ 80` mm로 좁혀져 있다.
- `robot_control_node` — 액션 서버의 `motion_sequence.WorkspaceBounds.contains` 검사가 `grasp_xyz` 또는 `return_xyz`가 설정 박스(기본 `200..700 × -300..300 × 0..500` mm)를 벗어나는 모든 goal을 거절한다. `robot_control.yaml`에서 `workspace_enabled: false`로 비활성화 가능하며, 기본은 활성화이다. 위반은 액션을 `failure_code = 5`로 단락시키며 로봇은 절대 움직이지 않는다. 이 두 번째 레이어가 존재하는 이유는 **임의의** 액션 클라이언트가 `/robot/pick_and_place`를 직접 호출할 수 있기 때문이다 — task-manager 단의 필터링만으로는 충분하지 않다.

### 6.3 그리퍼 상태 확인

견과를 클로즈한 뒤, `verify_grip` 단계는 `gripper_controller.wait_until_idle`(busy=True → busy=False — 두 단계 wait는 close가 시작되기 전의 stale "idle"을 읽지 않도록 한다)을 실행한 다음 `is_grip_detected()`를 조회한다. 비트가 set되어 있지 않으면 액션은 `failure_code = 2` (`grasp_not_detected`)를 반환하며 transit **이전에** abort하여, 컨베이어에 아무것도 떨어뜨리지 않는 phantom-grip transit을 방지한다.

### 6.4 Place-ready 트리거

`/conveyor/place_ready` (`std_msgs/Bool`)는 로봇 모션과 컨베이어 모션 사이의 단일 통합 지점이다.

- `robot_control_node`가 `_publish_place_ready`로부터 10 Hz로 게시한다.
- `place` 단계 안에서 TCP가 place y에 도달하고(`place_y_margin_mm` 이내) 그리퍼가 열렸을 때 **True**가 된다.
- `retreat` 시작 시, `pick_and_place` 종료 시, `/robot/stop` 시, 모션 오류 시 다시 **False**로 돌아간다.

### 6.5 컨베이어 트리거 조건

`conveyor_serial_node`는 **오직 False→True 엣지에서만** 벨트를 전진시킨다. True가 유지되어도 재트리거되지 않으며, 활성 실행 중의 두 번째 엣지는 로깅되고 무시된다. 이후 벨트는 `auto_command`(기본 `R80`)를 `auto_run_duration_sec`(기본 `5.0` s) 동안 실행하고, 내부 타이머가 `STOP`을 보낸다. 거리는 시간 기반이며 — 한계는 §7 참고.

### 6.6 실 실행 전 권장 안전 점검

로봇을 켜기 전에:

- **Pendant**: AUTO 모드 + Servo On + 상태 표시등 흰색. 빨간 표시등은 모션 명령을 조용히 실패시킨다(반환값은 success로 읽히지만 암은 움직이지 않는다). 자세한 트러블슈팅 노트는 `docs/03_run_manual.md` §12 참고.
- **워크스페이스 클리어**: 견과가 설정된 워크스페이스 박스 안에 있고, 반환 위치와 컨베이어가 막혀 있지 않은지 물리적으로 확인한다.
- **캘리브레이션 sanity**: `ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"`를 실행하고 `success: true`와 정상적인 TCP를 확인한다.
- **첫 픽 z**: `cobot_config/config/pick_offsets.yaml`의 클래스별 z offset이 현재 세팅에 맞는지 확인한다. 적어도 한 번의 단일 픽이 성공할 때까지 multi-pick 세션을 시작하지 말 것.
- **E-stop**: pendant E-stop이나 `ros2 service call /robot/stop std_srvs/srv/Trigger {}`를 칠 준비를 한다.

---

## 7. 현재 알려진 갭 / 결정 사항

### 7.1 명시적 메뉴 vs freeform 음성 프롬프트

- **상태**: Supabase 웹 경로에는 두 모드 모두 구현되어 있으며, `web_stt_supabase_v2`의 `VITE_PROMPT_MODE`로 선택된다.
  - `freeform` (기본) — 직업/포만감 STT 텍스트를 `llm.ts`의 `analyzeJob`, `analyzeSatiety`가 OpenAI `gpt-4o` JSON 모드로 분석한다.
  - `menu` — 직업 메뉴(교사, 개발자, 운동선수, 학생)와 포만감 메뉴(적음, 보통, 배부름)를 안내하고, 번호/한국어 키워드를 regex로 매칭한다.
- 메뉴 직업 매칭이 재시도에서도 미스이면 AI fallback이 아니라 추천 견과류 2종을 무작위로 선택해 세션을 계속 진행한다. 포만감 메뉴 매칭 실패는 `normal`로 fallback한다.

### 7.2 컨베이어 동작 의미론

- **상태**: `/conveyor/place_ready`의 False→True 엣지에 의해 트리거되는 **시간 기반 one-shot**으로 구현되어 있다. 한 번의 엣지 → `auto_command`(기본 `R80`) `auto_run_duration_sec`(기본 `5.0` s) 동안 → `STOP`. True가 유지되어도 재트리거되지 않는다.
- **한계**(`conveyor_controller/README.md`에 명시): 거리는 근사적이며 결정적이지 않다. 스텝 모드 펌웨어(`S<N>` 명령 + ack)는 **future work / TODO**로 문서화되어 있으며 의도적으로 범위 밖이다.

### 7.3 Supabase / 웹 로봇 진행 브릿지

- **상태**: `supabase_status_bridge` (`cobot_voice.supabase_status_bridge`, 실행파일 `supabase_status_bridge`)에 의해 구현되어 있으며, `bringup_supabase.launch.py`에서 기본 launch된다(toggle: `enable_supabase_status_bridge`, 기본 `true`). `/task/status`, `/task/result`, 그리고 `/conveyor/place_ready`의 False→True 엣지를 Supabase `robot_session.current.robot_state` 필드로 미러링하며, 음성 흐름의 `display_state` 필드는 그대로 둔다.
- **한계**(모듈 docstring에 명시): 액션 서버가 단계별 진행을 외부에 노출하지 않으므로, `placing`은 `conveyor_moving`을 발사하는 동일 엣지에서 추론된다. 두 상태는 writer 큐를 통해 연달아 emit된다.
- **실패 모드**: `cobot_db`/`supabase-py`가 없거나 `SUPABASE_URL`/`SUPABASE_KEY`가 없으면 bridge는 warning 또는 no-op으로 계속 spin한다. 로봇 파이프라인은 영향을 받지 않는다.

### 7.4 클래스별 Z-offset 설정

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

### 7.5 알아둘 만한 기타 갭

- **`cobot_safety` 및 `cobot_policy`** — 두 패키지 모두 빈 `*.py` 파일과 함께 존재한다. `setup.py`는 `safety_manager`와 `policy_selector` entry point를 노출하지만, 모듈에는 코드가 없다. **Not Implemented**; 어떤 launch 파일도 참조하지 않는다.
- **`cobot_config/config/{slot_poses,policy_config,workspace}.yaml`** — 정의되어 있지만 어떤 런타임 노드도 로드하지 않는다. 실제 워크스페이스 경계는 `task_manager.yaml`과 `robot_control.yaml`의 파라미터 블록에 있다; config 패키지의 YAML들은 **현재 사용되지 않는다**.
- **`cobot_bringup/config/params.yaml`** — 시스템 파라미터(ROS_DOMAIN_ID, RMW, robot host/port). `cobot_bringup/launch/`의 어떤 launch 파일도 **로드하지 않는다**. wire-in 될 때까지 참고용으로 취급할 것.
- **워크스페이스 경계 중복** — `task_manager.yaml`과 `robot_control.yaml`에 중복되어 있다. 수동으로 동기화를 유지해야 하며, 오늘날 패키지 간 검증은 없다.

---

## 부록 — 깊이 있는 맥락을 위해 읽을 파일

위에 기술된 런타임 동작에 대해:

- 최상위 launch: `cobot_bringup/launch/full_system.launch.py`, `host_system.launch.py`, `perception.launch.py`, `robot.launch.py`.
- Task 루프: `cobot_task_manager/cobot_task_manager/task_manager_node.py` (`_run` 메서드)와 `target_selector.py`, `retry_policy.py`.
- 액션 서버 + helper 노드 근거: `cobot_robot_control/cobot_robot_control/robot_control_node.py` (175–260 라인).
- 픽 단계 + 워크스페이스 가드: `cobot_robot_control/cobot_robot_control/motion_sequence.py`.
- 검출 → base 프레임 변환: `cobot_perception/cobot_perception/perception_transform_node.py` (`_handle_detect_once`).
- Supabase 웹 음성 상태머신: `web_stt_supabase_v2/src/lib/voice/orchestrator.ts`, `llm.ts`, `recommendation.ts`, `session.ts`.
- Supabase DB 계약: `cobot_db/sql/init.sql`, `cobot_db/cobot_db/cobot_db_manager.py`.
- 컨베이어 엣지 의미론: `conveyor_controller/README.md`.

동반 실행 순서 문서는 `docs/03_run_manual.md`이다.

---

## 부록 — Dry Run / 테스트 참고

본문은 실제 Supabase 세션과 실 하드웨어 실행 경로만 다룬다. 아래 항목은 코드 변경 후 하드웨어를 켜기 전 확인하거나, 하드웨어 없이 task loop를 재현할 때 사용한다.

### Mock 실행

- `robot_control_node`는 mock backend를 지원한다: `motion_backend: mock`, `gripper_backend: mock`.
- mock 모드에서는 DSR_ROBOT2나 Modbus RG2를 건드리지 않고 픽 단계 시퀀스 전체를 완료하고 feedback/result를 반환한다.
- `mock_perception_node`는 하드코드된 8-nut 장면을 반환하므로, 카메라와 로봇 없이 task manager loop를 확인할 수 있다.
- perception, 모션, task manager 코드를 바꿨다면 실 하드웨어 실행 전에 mock e2e를 먼저 돌린다. 대표 구성은 `enable_realsense:=false`, `enable_dsr_bringup:=false`, gripper backend mock이다.

### Dry-run / 단일 픽 점검

- `scripts/pick_one.py --dry-run <class>`는 액션을 디스패치하지 않고 보낼 goal 내용을 출력한다.
- `scripts/pick_one.py --z-override <z>`는 첫 픽 z 높이를 맞출 때 사용한다.
- `scripts/pick_one.py`와 `scripts/pick_all.py`는 파일 상단에 별도 `PER_CLASS_Z_OFFSET` dict를 가지고 있다. 현재 `scripts/pick_one.py`의 값은 모두 0이므로, 스크립트 모드 픽은 `cobot_config/config/pick_offsets.yaml`의 `walnut: -1.0`을 자동으로 가져오지 않는다.

### 참고 문서

- `docs/04_validation_checklist.md` — 사전 점검 테스트 체크리스트.
- `docs/03_run_manual.md` — 운영자 실행 순서와 트러블슈팅.

---

## 부록 — Firebase / Firestore 이력 및 롤백 참고

현재 본문 기준 경로는 Supabase다. 아래 항목은 과거 Firebase/Firestore 구현을 이해하거나 긴급 롤백을 검토할 때만 참고한다.

### 남아 있는 Firebase 관련 코드

- `cobot_voice/cobot_voice/firebase_bridge.py` — Firestore `robot_session/current` writer.
- `cobot_voice/cobot_voice/firebase_status_bridge.py` — `/task/status`, `/task/result`, `/conveyor/place_ready`를 Firestore `robot_state` 필드로 미러링하던 ROS 노드.
- `cobot_task_manager/cobot_task_manager/order_provider.py`의 `FirestoreOrderProvider` — Firestore `robot_session/current` 문서에서 `combo`/`request_id`를 읽던 주문 provider.
- `web_stt_firebase*/` — Firebase/Firestore 기반 웹 UI 이력.
- `secrets_4_firebase_config/` — Firebase Admin service-account JSON 위치. Gitignored 상태여야 한다.

### 과거 Firebase 흐름

과거 웹/음성 경로는 Firestore 문서 `robot_session/current`를 공유 상태로 사용했다. 웹 UI는 해당 문서를 실시간 구독했고, Python 쪽 `firebase_bridge.py` 또는 브라우저 Firebase SDK가 `display_state`, `transcript`, `categories`, `intensity`, `combo`, `success`, `theme` 등을 기록했다. 로봇 진행 상태는 `firebase_status_bridge.py`가 별도 `robot_state` 필드로 미러링했다.

`web_voice_bridge_server`는 구형 웹 UI가 호스트 Python 음성 흐름을 트리거하기 위한 HTTP bridge였다. Supabase 웹 경로에서는 사용하지 않는다.

### 롤백 시 확인할 항목

- launch 인자에서 `order_source:=firestore`를 사용한다.
- `enable_firebase_status_bridge:=true`, `enable_supabase_status_bridge:=false`로 bridge를 전환한다.
- `FIREBASE_SERVICE_ACCOUNT` 또는 Google ADC가 Firestore Admin SDK에서 유효해야 한다.
- Firebase 웹 UI를 사용할 경우 Firestore rules와 브라우저 Firebase 설정이 현재 프로젝트에 맞아야 한다.
- Supabase와 Firebase 웹 UI를 동시에 실행하면 같은 로봇 세션 의미를 서로 다른 백엔드에 쓰게 되므로 운영 중 혼용하지 않는다.

상세한 migration 차이와 SQL/RLS 기준은 `docs/09_supabase_migration.md`를 참고한다.
