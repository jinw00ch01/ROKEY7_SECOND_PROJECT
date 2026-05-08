# 실행 준비 및 운영 매뉴얼

통합 cobot 너트 피킹 시스템을 위한 단계별 운영 매뉴얼이다.

## 목차

1. 목적
2. 사전 점검 체크리스트
3. 환경 변수
4. 빌드 절차
5. Dry-Run / Mock 모드 실행
6. Voice-to-Task 테스트
7. 실제 하드웨어 전체 시스템 실행
8. 단일 너트 1차 테스트
9. 컨베이어 테스트
10. 상태 모니터링
11. 종료 절차
12. 트러블슈팅
부록 — Quick command reference

## 문서 세트

- `docs/01_system_architecture.md` — 시스템을 처음 접한다면 먼저 읽을 것.
- `docs/02_ros_node_architecture.md` — 노드별 인터페이스 레퍼런스, 파라미터
  목록, 그리고 전체 ROS 디버깅 명령 표면.
- `docs/03_run_manual.md` — **이 파일**.
- `docs/04_validation_checklist.md` — 아래 단계와 매칭되는 테스트/수용
  체크리스트.
- `docs/cleanup_deletion_proposal.md` — 아카이브된/플래그된 파일에 대한 삭제
  계획 (읽기 전용 메타 문서).

legacy `docs/_archive/run_manual.md` 는 이 파일로 **대체**되어
`docs/_archive/`로 이전되었다. 오래된 경로(`~/cobot_ws/...`)와 만료된
캘리브레이션 값(예: 구식 `--z-override 315`)을 포함하므로, 진실의
출처로 사용하지 말 것.

> **`_archive_cleanup/` 에서 어떤 것도 source 하거나 실행하지 말 것.** 해당
> 디렉터리는 `<YYYYMMDD>` (현재 배치: `20260508`) 에 활성 트리에서 이동된
> 파일을 보관한다. 실행 가능한 entry point 가 없으며, `colcon` 에 의해
> 빌드되지 않도록 의도되어 있다. 계획은 `docs/cleanup_deletion_proposal.md`,
> 파일별 사유/근거/위험 기록은
> `_archive_cleanup/20260508/cleanup_manifest.md` 참조.

이 문서에서 사용하는 규칙:

- 워크스페이스 루트는 `~/cobot_ws`, cobot2 패키지 소스는 `~/cobot_ws/src/cobot2`. 클론 위치가 다르다면 적절히 변경.
- 각 셸 명령은 **한 줄로 입력**해야 한다 — 긴 `ros2 launch …` 호출은
  터미널이 줄바꿈하면 깨진다 (bash 가 줄바꿈 지점에서 분할하고 나머지 인자를
  조용히 버린다).
- `T1`, `T2`, … 는 별도의 터미널 탭/창을 의미한다.

---

## 1. 목적

이 매뉴얼은 운영자에게 다음을 안내한다:

1. 새 셸에서 `cobot_ws` 워크스페이스 기동.
2. mock / dry-run 모드에서 시스템을 안전하게 검증 (로봇 동작 없음, 실제
   그리퍼 없음, 원하면 실제 카메라도 없음).
3. 음성 → 추천 → 로봇 픽업 end-to-end 실행 트리거.
4. mock 경로가 안정화되면 실제 하드웨어 (Doosan M0609 + OnRobot RG2 +
   RealSense + Arduino conveyor) 로 전환.
5. 모니터링, 종료, 그리고 일반적 실패 복구.

이 문서는 조립, 캘리브레이션, YOLO 모델 학습, 또는 web/Firebase 프로젝트
설정은 **다루지 않는다** — 데모를 운영할 때마다 매번 수행하는 런타임
단계만 다룬다.

---

## 2. 사전 점검 체크리스트

매 세션 전에 이 점검을 수행. 실패하는 항목은 진행 전에 멈추고 해결.

### 2.1 소프트웨어 환경

- [ ] Ubuntu 22.04 + ROS 2 Humble 설치.
- [ ] 사용하는 **모든** 터미널에서 ROS 환경을 source:
  ```bash
  source /opt/ros/humble/setup.bash
  source ~/cobot_ws/install/setup.bash
  ```
- [ ] `ROS_DOMAIN_ID` export (§3 참조).
- [ ] 워크스페이스가 에러 없이 빌드됨 (§4 참조).
- [ ] 필요한 Python 의존성 사용 가능: `numpy`, `scipy`, `opencv-python`,
  `cv_bridge` (시스템), `ultralytics`, `pyserial`, `pyaudio`,
  `sounddevice`, `openwakeword`, `openai`, `langchain-openai`,
  `python-dotenv`, 선택적으로 `firebase-admin`.
- [ ] 시스템 바이너리: `ffplay` (ElevenLabs 재생) 그리고/또는 `spd-say`
  (`speech-dispatcher`).

### 2.2 자격증명

- [ ] `cobot_voice/resource/.env` 존재 (`.env.example` 에서 복사) 하고
  최소 `OPENAI_API_KEY` 설정. **단**, STT 또는 LLM analyzer 를 사용할
  계획인 경우에만 필요.
- [ ] `FIREBASE_SERVICE_ACCOUNT` 가 유효한 서비스 어카운트 JSON 을 가리킴.
  **단**, web UI / Firestore 미러를 원하는 경우에만 필요. 없으면 writer
  들이 조용히 no-op 하고 로봇 파이프라인은 여전히 동작한다.
- [ ] ElevenLabs 키 설정. **단**, `COBOT_TTS_PROVIDER=elevenlabs` 인 경우만.

### 2.3 컨테이너 / Docker

이 저장소에는 **Dockerfile 이나 docker-compose 파일이 없다**. 객체 검출,
perception, robot control, 음성 파이프라인이 모두 호스트에서 네이티브 ROS 2
노드로 동작한다. 컨테이너에서 무언가 실행하는 배포라면 트리 외부이며 로컬
설정에서 **확인 필요**.

### 2.4 하드웨어 (real 모드 전용 — mock 에서는 건너뜀)

- [ ] Intel RealSense 가 USB-3 포트에 연결됨:
  ```bash
  lsusb | grep -i realsense
  ```
- [ ] Doosan 컨트롤러 도달 가능:
  ```bash
  ping -c 3 192.168.1.100
  ```
- [ ] OnRobot RG2 도달 가능:
  ```bash
  ping -c 3 192.168.1.1
  ```
- [ ] 컨베이어 Arduino 인식됨:
  ```bash
  ls /dev/ttyACM*       # expect /dev/ttyACM0
  ```
- [ ] 펜던트: **AUTO** 모드 + **Servo On** + 상태 표시등 흰색. 빨간색
  표시등은 동작을 조용히 실패시킨다 (API 가 success 를 반환하지만 암은
  움직이지 않음 — 알려진 footgun).
- [ ] 노트북을 운영하는 사람의 **손에 닿는 거리에 E-stop**.
- [ ] **워크스페이스 정리**: 너트가 설정된 워크스페이스 박스
  (`task_manager.yaml` / `robot_control.yaml`) 안에 있어야 함; approach /
  transit / return 경로에 손가락, 케이블, 공구 없음; 컨베이어 벨트 경로
  방해물 없음.

---

## 3. 환경 변수

이 저장소의 코드가 실제로 참조하는 변수만 나열한다. 주어진 기본값은 코드가
폴백하는 값이다.

### 3.1 ROS

| 변수 | 사용 위치 | 필수 | 비고 |
|---|---|---|---|
| `ROS_DOMAIN_ID` | 모든 ROS 2 트래픽 | 예 | 모든 터미널이 공유할 값을 선택. `cobot_bringup/config/params.yaml` 은 `66` 을 참고치로 적어두지만, **그 파일은 어떤 launch 파일도 로드하지 않는다** — 실제 값은 셸에서 `export` 한 값이다. 중앙화하려면 **확인 필요**. |
| `RMW_IMPLEMENTATION` | 모든 ROS 2 트래픽 | 아니오 | `cobot_bringup/config/params.yaml` 은 팀의 참조 RMW 로 `rmw_cyclonedds_cpp` 를 적어둔다. 같은 단서: 자동 적용되지 않음. |

예시:
```bash
export ROS_DOMAIN_ID=99
# export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp   # optional
```

### 3.2 Voice / TTS / LLM

이들은 `cobot_voice.env.load_package_env` 가 해석하며,
`cobot_voice/resource/.env` (또는 `COBOT_VOICE_ENV_PATH` 가 가리키는 파일)
를 로드한다.

| 변수 | 필수 | 코드 기본값 | 용도 |
|---|---|---|---|
| `COBOT_VOICE_ENV_PATH` | 아니오 | `cobot_voice/resource/.env` | dotenv 파일 위치 오버라이드 |
| `OPENAI_API_KEY` | 예 (STT/LLM 용) | (없음 — 시작 시 raise) | Whisper transcription + gpt-4o analyzer |
| `COBOT_VOICE_PROMPT_MODE` | 아니오 | `freeform` | `freeform` (LLM analyzer) 또는 `menu` (한국어 번호 메뉴 + 정규식) |
| `COBOT_TTS_ENABLED` | 아니오 | `1` | `0`/`false`/`no`/`off` 로 설정 시 TTS 음성 음소거 |
| `COBOT_TTS_PROVIDER` | 아니오 | `auto` | `auto` (키가 있으면 ElevenLabs, 없으면 `spd-say`), `elevenlabs`, 또는 `spd-say` |
| `ELEVENLABS_API_KEY` (또는 `ELEVEN_LABS_API_KEY`) | ElevenLabs 사용 시 | — | provider 가 ElevenLabs 로 결정되면 필수 |
| `ELEVENLABS_VOICE_ID` | 아니오 | `pNInz6obpgDQGcFmaJgB` (Adam) | |
| `ELEVENLABS_MODEL_ID` | 아니오 | `eleven_flash_v2_5` | |
| `ELEVENLABS_LANGUAGE_CODE` | 아니오 | `ko` | |
| `ELEVENLABS_OUTPUT_FORMAT` | 아니오 | `mp3_44100_128` | |
| `ELEVENLABS_STABILITY` | 아니오 | `0.5` | Float |
| `ELEVENLABS_SIMILARITY_BOOST` | 아니오 | `0.75` | Float |
| `ELEVENLABS_STYLE` | 아니오 | `0.0` | Float |
| `ELEVENLABS_USE_SPEAKER_BOOST` | 아니오 | `true` | Bool |

### 3.3 Firebase

| 변수 | 필수 | 용도 |
|---|---|---|
| `FIREBASE_SERVICE_ACCOUNT` | 아니오 | Admin SDK 서비스 어카운트 JSON 경로. 미설정 시 코드는 기본 ADC 로 `firebase_admin.initialize_app()` 을 시도한다. 둘 다 실패하면 `firebase_bridge` 가 조용히 no-op 으로 전환. |

### 3.4 Task manager

| 변수 | 필수 | 용도 |
|---|---|---|
| `COBOT_PICK_OFFSETS_PATH` | 아니오 | `cobot_config/config/pick_offsets.yaml` 의 해석 체인 오버라이드. 로더 순서: 명시적 `pick_offsets_path` 파라미터 → 이 환경 변수 → ament-share lookup → 소스 트리 폴백. 파일이 없으면 내장 `DEFAULT_OFFSETS_MM` (`walnut: -1.0`, 그 외 `0.0`) 사용. |

### 3.5 권장 export 블록 (mock 세션)

```bash
export ROS_DOMAIN_ID=99
source /opt/ros/humble/setup.bash
source ~/cobot_ws/install/setup.bash
# Optional: silence TTS during mock runs
export COBOT_TTS_ENABLED=0
```

### 3.6 권장 export 블록 (LLM 음성을 사용하는 full real 실행)

```bash
export ROS_DOMAIN_ID=99
source /opt/ros/humble/setup.bash
source ~/cobot_ws/install/setup.bash
# .env file is auto-loaded by cobot_voice; you only need this if you
# want a non-default location:
# export COBOT_VOICE_ENV_PATH=/absolute/path/to/cobot_voice.env
```

---

## 4. 빌드 절차

워크스페이스 루트에서:

```bash
cd ~/cobot_ws
colcon build --symlink-install
source install/setup.bash
```

타깃 리빌드 (빠른 반복):

```bash
# After editing a single Python package
colcon build --packages-select cobot_task_manager --symlink-install

# After editing the message package, rebuild everything that depends on it
colcon build --packages-select cobot_msgs
colcon build --packages-up-to cobot_bringup
```

비고:

- `--symlink-install` 권장 — Python 편집 시 런타임이 변경을 반영하기 위해
  리빌드가 필요 없다. `cobot_*/config/` 하위의 YAML config 는 `share/` 로
  재설치되도록 빌드가 **필요하다**.
- `cobot_msgs` 는 `ament_cmake` (인터페이스) 다. 다른 in-repo Python 패키지는
  `ament_python` 이다.
- OD 모델은
  `experiments/cobot_OD_obb_nano/train_phase2_20260504_173049/weights/best.pt`
  에서 `cobot_object_detection/setup.py` 를 통해 패키징된다. 그 파일이
  없어도 빌드는 성공하지만, 리졸버는 런타임에 소스 트리로 폴백한다.
- 마커 파일: `web_stt_firebase/`, `nuts_data_recording/`, `scripts/`,
  `docs/` 가 `COLCON_IGNORE` 를 가진다. 절대 빌드되지 않는다.

`colcon build` 후에는 새 패키지를 가시화하기 위해 각 터미널에서 **반드시**
`source install/setup.bash` 를 다시 수행.

---

## 5. Dry-Run / Mock 모드 실행

로봇, 그리퍼, 또는 카메라가 사용 불가능할 때, 또는 perception / motion /
task 코드를 변경했을 때 항상 이 모드를 사용. 어떤 하드웨어 동작도 없이
**전체** task 루프를 행사한다.

### 5.1 "mock" 의 의미

- `motion_backend: mock` (`cobot_robot_control/config/robot_control.yaml`,
  **기본** YAML) — DSR_ROBOT2 가 임포트되지 않음; 액션 서버가 즉시 전체
  스테이지 시퀀스를 완료.
- `gripper_backend: mock` — Modbus 트래픽 없음; `is_grip_detected()` 가
  true 를 반환하므로 `verify_grip` 이 항상 성공.
- `mock_perception_node` — 하드코딩된 8-너트 장면으로
  `/perception/detect_once` 를 제공. 카메라 불필요.
- `task_autostart:=false` — `/task/start` 를 트리거할 때까지 워커가 idle.

### 5.2 터미널 레이아웃

#### T1 — mock 으로 전체 시스템

```bash
source ~/cobot_ws/install/setup.bash
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false enable_firebase_status_bridge:=false
```

이 launch 는 **실제** `perception_transform_node` 와
`object_detection_node` 를 실행하지만, `enable_realsense:=false` 이므로
카메라 프레임이 없다. 카메라 없이 루프를 end-to-end 로 테스트하려면 mock
perception 노드로 교체 — §5.3 참조.

기대되는 boot 라인:

- `Initializing MOCK motion backend ...` *(경고를 로깅한다면)*
- `Initializing MOCK gripper backend ...`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `Service /perception/detect_once ready`
- `Subscribed to /camera/camera/color/image_raw, publishing on /detection/objects`
- `[state] idle` (task manager 가 `/task/start` 대기)

#### T2 (대안) — mock perception 으로 대체

루프가 실제로 타깃을 반환하길 원한다면, 실제 perception 노드 대신 mock
perception 노드를 실행. 이 경우 실제 perception transform 노드 없이 시스템을
launch 해야 한다 — 가장 쉬운 경로는 서브시스템을 개별 launch:

```bash
# T1 — robot stack only (mock backends), no perception
source ~/cobot_ws/install/setup.bash
ros2 launch cobot_robot_control robot_control.launch.py
```

```bash
# T2 — mock perception
source ~/cobot_ws/install/setup.bash
ros2 run cobot_perception mock_perception_node
```

```bash
# T3 — task manager (autostart false so we control trigger)
source ~/cobot_ws/install/setup.bash
ros2 launch cobot_task_manager task_manager.launch.py
```

> **확인 필요**: `task_manager.launch.py` 는 `task_autostart` 를 전달하지
> 않으며, YAML 기본값은 `autostart: true` 이다. 이 레이아웃에서
> idle-then-trigger 패턴이 필요하다면 노드를 직접 실행:
> ```bash
> ros2 run cobot_task_manager task_manager_node --ros-args -p autostart:=false
> ```

#### T4 — 가짜 task sender

```bash
source ~/cobot_ws/install/setup.bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

기대 응답:
```
response:
std_srvs.srv.Trigger_Response(success=True, message='task started')
```

그 후 T1 (또는 T3) 터미널에서 루프가 다음을 출력해야 한다:

```
[state] init
[state] detect
[state] select_target almond
[state] pick_and_place almond
[state] detect
...
[state] done
```

…그리고 `/task/result` 가 `success counts={...} skipped=[...]` 으로 끝난다.

### 5.3 mock 모드의 컨베이어

컨베이어 노드는 시작 시 `/dev/ttyACM0` 열기를 시도한다. Arduino 가 없다면
**완전히 생략**. `place_ready` 토픽은 여전히 `robot_control_node` 가 게시하며,
구독자가 없어도 무해하다.

Arduino 없이 컨베이어 로직을 행사하고 싶다면 토픽을 검사할 수 있고, 노드가
포트를 열 수 있었다면 auto-stop 타이머도 설정되었을 것이다 — 다만 단지
open 실패를 로깅하고 `serial_port=None` 으로 동작한다. 포트가 `None` 일 때
명령 전송이 의미 있는 동작을 만드는지는 **확인 필요**.

---

## 6. Voice-to-Task 테스트

이 섹션은 음성 파이프라인 → JSON 파일 → `/task/start` 핸드오프를 검증한다.
이 작업 동안 로봇 스택은 mock 모드를 유지해도 된다.

### 6.1 사전 조건

- T1 을 **file 모드**로 launch (그래야 task manager 가 실제로
  `latest_order.json` 을 소비):
  ```bash
  source ~/cobot_ws/install/setup.bash
  ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false enable_firebase_status_bridge:=false order_source:=file file_order_path:=/home/aes/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
  ```
  T1 로그에서 확인:
  ```
  FileOrderProvider reading /home/aes/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
  ```
  이 라인이 없다면 task manager 가 `mock` 으로 폴백한 것 —
  `order_source:=file` 인자와 launch 라인이 줄바꿈되지 않았는지 재확인.

- LLM analyzer 와 Whisper STT 를 위해 (`cobot_voice/resource/.env` 에)
  `OPENAI_API_KEY` 설정.

### 6.2 텍스트 모드 (마이크 없음)

end-to-end 통합을 검증하는 가장 빠른 방법:

```bash
source ~/cobot_ws/install/setup.bash
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이 도움 필요해요"
```

기대되는 stdout:

```
recognized_text : '피곤하고 집중이 안 돼서 많이 도움 필요해요'
combo           : [{'nut': 'cashew', 'count': 3}, {'nut': 'walnut', 'count': 3}]
success         : True
dispatched      : True
```

JSON 계약 확인:

```bash
cat ~/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
```

`success: true` 와 비어있지 않은 `combo` 배열을 포함해야 한다. `request_id`
는 `YYYYMMDD_HHMMSS` 타임스탬프이다.

`/task/start` 트리거 발사 확인 — T1 task manager 로그가 `idle` 에서 `init`
→ `detect` → `select_target <class>` → … → `done` 으로 진행해야 한다.

### 6.3 디버그 모드 음성 (키보드, 마이크 없음)

STT 대신 터미널 입력으로 프롬프트 흐름을 단계 진행:

```bash
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --debug
```

상태 및 강도 문자열을 입력하라는 프롬프트가 표시된다.

### 6.4 마이크 모드 (전체 음성)

```bash
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py
```

1. wake word 발화 ("Hello Rokey" — 번들된 `hello_rokey_8332_32.tflite`
   모델).
2. 컨디션을 묻는 TTS 프롬프트 대기; 약 5 s 발화.
3. 강도 프롬프트 대기; 약 5 s 발화.
4. TTS 가 combo 를 확인하고 task manager 가 자동 시작.

### 6.5 Web bridge 변형

React web UI 에서 음성 흐름을 구동:

```bash
# T1 — task manager + perception in file mode (as in §6.1)

# T2 — local HTTP bridge for the web UI
source ~/cobot_ws/install/setup.bash
ros2 run cobot_voice web_voice_bridge_server
# Server listens on http://127.0.0.1:8765 (override with --host/--port)

# T3 — Vite dev server for the UI
cd ~/cobot_ws/src/cobot2/web_stt_firebase
npm install     # first time only
npm run dev
```

web UI 의 시작 버튼은 `/voice-audio/start` 로 POST; bridge 가 동일한
`voice_order_flow` 를 실행하고 `latest_order.json` 과 Firestore 에 쓴다.
로봇 트리거 경로는 §6.2 와 동일.

### 6.6 로봇 트리거 건너뛰기 (검증만)

```bash
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --text "..." --no-dispatch
```

`latest_order.json` 은 저장하지만 `/task/start` 는 호출하지 **않는다**.

---

## 7. 실제 하드웨어 전체 시스템 실행

> ⚠ **Real-hardware 모드는 6-DOF 암을 움직인다.** 먼저 mock 모드에서 §2.4
> 와 §6.4 를 검증할 것. E-stop 을 손에 닿는 거리에. `gripper_force_x10`
> 을 필요 이상으로 높이지 말 것 (현재 기본값 `150` → 15 N).
>
> Real 모드는 명시적으로 옵트인. Mock 이 기본값.

### 7.1 네트워크 점검

```bash
ping -c 3 192.168.1.100   # Doosan controller
ping -c 3 192.168.1.1     # OnRobot RG2 gripper
lsusb | grep -i realsense
ls /dev/ttyACM*           # Arduino conveyor
```

진행 전에 네 가지 모두 응답해야 한다.

### 7.2 권장 터미널 레이아웃

#### T1 — Doosan bring-up

```bash
source ~/cobot_ws/install/setup.bash
ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=192.168.1.100 port:=12345
```

다음 대기:

- `Connected to DRCF`
- `ROBOT_STATE : STATE_STANDBY`
- `Configured and activated dsr_controller2`
- `Configured and activated joint_state_broadcaster`

이 터미널은 그대로 둘 것; 닫으면 로봇 연결이 끊긴다.

`Controller already loaded` 가 보이면 좀비 `ros2_control_node` 가 살아있는
것 — T1 에서 Ctrl-C, 이후 아무 터미널에서:
```bash
pkill -9 -f ros2_control_node
```
…그리고 T1 재 launch.

#### T2 — RealSense

```bash
source ~/cobot_ws/install/setup.bash
ros2 launch realsense2_camera rs_launch.py enable_color:=true enable_depth:=true align_depth.enable:=true
```

`RealSense Node Is Up!` 대기 후 T6 (또는 임의 여분 터미널) 에서 sanity
check:

```bash
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw
# expect ~30 Hz; Ctrl-C
```

#### T3 — real 모드의 전체 cobot 스택

> ⚠ 이 라인이 실제 동작 + 실제 그리퍼를 활성화한다. E-stop 을 손에 들 것.
> **한 줄로** 입력/붙여넣기.

```bash
source ~/cobot_ws/install/setup.bash
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false dsr_mode:=real config_robot_control:=$(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config/robot_control.real.yaml order_source:=file file_order_path:=/home/aes/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
```

인자에 대한 비고:

- `enable_realsense:=false` — T2 에서 이미 실행 중.
- `enable_dsr_bringup:=false` — T1 에서 이미 실행 중.
- `dsr_mode:=real` — 서브 launch 로 전파; `enable_dsr_bringup:=false` 이므로
  여기서 엄밀히 필요하진 않지만 문서화를 위해 유지.
- `config_robot_control:=...real.yaml` — **이 라인**이 `motion_backend` 를
  mock 에서 real 로, `gripper_backend` 를 mock 에서 modbus 로 전환한다.
  이것이 없으면 T1 과 무관하게 mock robot 으로 실행된다.

다음 대기:

- `Initializing DSR_ROBOT2 (id=dsr01, model=m0609)`
- `Initializing Modbus RG2 at 192.168.1.1:502 (force=15.0N)`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `Service /perception/detect_once ready`
- `FileOrderProvider reading /home/aes/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json`

#### T4 — 컨베이어 (실제 Arduino)

```bash
source ~/cobot_ws/install/setup.bash
ros2 launch conveyor_controller conveyor_controller.launch.py
```

다음 대기:

- `Connected to Arduino serial port /dev/ttyACM0 at 115200 baud`
- `Listening on /conveyor_cmd for commands: F<1-100>, R<1-100>, STOP`
- `Place-ready trigger: one False->True edge on /conveyor/place_ready ...`

`Failed to open serial port /dev/ttyACM0` 가 보이면 §12 참조.

#### T5 — 운영자 터미널 (sanity → 트리거)

```bash
source ~/cobot_ws/install/setup.bash

# Live TCP read works?
ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"

# One detection cycle (no motion)
ros2 service call /perception/detect_once cobot_msgs/srv/DetectOnce "{}"

# Dry-run a single pick (prints, does not move the robot)
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --dry-run
```

위 점검이 정상이면:

- **단일 너트** 테스트는 §8 참조.
- 음성 구동 전체 픽업:
  ```bash
  ~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이"
  ```
  또는 마이크 모드 (§6.4).

---

## 8. 단일 너트 1차 테스트

특히 perception / motion / 캘리브레이션 코드를 편집했거나 카메라를 옮긴
뒤에는, 멀티 너트 세션 전에 **항상** 단일 너트 픽을 실행.

```bash
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --dry-run
```

출력된 `base_xyz` 가 합리적인지 확인 (워크스페이스 경계는
`x ∈ [200, 700]`, `y ∈ [-300, 300]`, `z` 는 너트 높이 범위 `40–80` mm
근처). 그렇지 않다면 실제 픽 시도 전에 **멈추고** 재캘리브레이션.

그 후:

```bash
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew
# or, when tuning Z:
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --z-override 315
# or, when tuning the gripper pre-position:
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --pre-grasp-width 35
```

T3 로그에서 액션 피드백 관찰:

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

result-code 알림 (`cobot_msgs/action/PickAndPlace` 출처):

| Code | 의미 |
|---|---|
| 0 | ok |
| 1 | approach_fail |
| 2 | grasp_not_detected |
| 3 | motion_fail |
| 4 | safety_stop |
| 5 | workspace_violation |

테이블을 누르지 않으면서 잡히는 값을 찾을 때까지 `--z-override` 를 5 mm
간격으로 반복. 이후 `cobot_config/config/pick_offsets.yaml` (클래스별
`_z_offset_mm`) 에 커밋하여 다음 실행 시 task-manager 경로가 동일한 값을
사용하게 한다.

---

## 9. 컨베이어 테스트

로봇을 실행하지 않고도 컨베이어 배선 + 엣지 로직을 검증할 수 있다.

### 9.1 place_ready 엣지 한 번 수동 발사

한 터미널에서 컨베이어 노드 로그 (§7 의 T4) 를 관찰. 다른 터미널에서:

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: false}"
```

기대 동작:

- True 메시지가 정확히 한 번의 벨트 전진을 트리거:
  ```
  [conveyor_start] command=R80 duration=5.00s (place_ready edge)
  ```
- `auto_run_duration_sec` 초 (기본 `5.0`) 후 타이머가 만료되고 노드가
  `STOP` 전송:
  ```
  [conveyor_stop]  command was R80, duration=5.00s elapsed
  ```
- False 메시지는 `_last_place_ready` 를 리셋하므로 다음 True 가 새 엣지가
  된다.

타이머가 활성인 동안 두 번째 `True` 가 게시되면
`Ignoring place_ready trigger while conveyor auto-run is active` 로 로깅
되고 무시된다 — 이는 의도된 동작 (한 엣지 = 한 동작).

### 9.2 수동 명령 오버라이드

같은 터미널:

```bash
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'F30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'STOP'}"
```

이들은 엣지 로직을 완전히 우회한다.

### 9.3 픽당 거리 튜닝

이동은 **duration 기반이며 step 기반이 아니다**
(`conveyor_controller/README.md` 참조). 거리 ≈ 벨트 속도 × duration.

리빌드 없이 전진을 늦추거나 줄이려면:

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py auto_command:=R30 auto_run_duration_sec:=2.0
```

또는 실행 중인 노드에서 라이브로:

```bash
ros2 param set /conveyor_serial_node auto_run_duration_sec 3.0
ros2 param set /conveyor_serial_node auto_command R50
```

**Step-mode 펌웨어** (트리거당 정확한 거리) 는
`conveyor_controller/README.md` 에 향후 작업으로 문서화되어 있다. 그것이
도착하기 전까지는 첫 설치 시 줄자로 픽당 거리를 검증.

---

## 10. 상태 모니터링

### 10.1 ROS 토픽

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

유용한 one-shot:

```bash
ros2 topic hz /detection/objects
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw

ros2 node list
ros2 service list -t
```

### 10.2 Web UI / Firestore

`enable_firebase_status_bridge:=true` (기본값) 이고 Firebase 자격증명이
로드되어 있다면:

- web UI 가 `robot_session/current` 를 구독하고 `display_state` (음성
  흐름) 와 `robot_state` (로봇 파이프라인) 를 모두 렌더링.
- 실행 중에 보게 되는 `robot_state` 값:
  `detecting → picking → placing → conveyor_moving → task_done`
  (실패 시 `error` 와 `robot_error` 필드).

### 10.3 단일 픽을 시각적으로 마크

rqt YOLO 오버레이 사용:

```bash
~/cobot_ws/src/cobot2/scripts/yolo_rqt_view.py
# Then in another terminal:
ros2 run rqt_image_view rqt_image_view /yolo/annotated
```

이는 동일한 컬러 스트림을 구독하여 YOLO 를 독립 실행하고 주석 프레임을
게시한다 — 프로덕션 `object_detection_node` 파이프라인에는 영향을 주지
**않는다**.

---

## 11. 종료 절차

bring-up 의 역순. 목표는 암을 안전한 상태로 두고 좀비 프로세스를 남기지
않는 것이다.

1. **새 task 입력 중지.**
   - 음성 흐름 중지 (`voice_to_robot.py` 터미널 Ctrl-C, 또는 web UI 탭
     닫기).
   - task 루프가 실행 중이면 가능하다면 `[state] done` 까지 대기. 그렇지
     않으면:
     ```bash
     ros2 service call /robot/stop std_srvs/srv/Trigger "{}"
     ```

2. **로봇을 home 으로 복귀** (real 모드 전용; mock 은 효과 없음):
   ```bash
   ros2 service call /robot/home std_srvs/srv/Trigger "{}"
   ```
   `success: True` 대기. 또는 task 루프를 일시 정지하고 펜던트 사용.

3. **cobot 스택 중지 (T3).** launch 터미널에서 Ctrl-C. launch 가 완전히
   해체될 때까지 대기 (모든 `process has finished cleanly` 라인).

4. **컨베이어 중지 (T4).** Ctrl-C. 시리얼 포트가 닫히고 Arduino 는 idle
   상태를 계속 유지.

5. **카메라 중지 (T2).** Ctrl-C.

6. **Doosan bring-up 중지 (T1).** Ctrl-C. 컨트롤러와의 연결이 끊긴다. 다음
   실행 시 "Controller already loaded" 가 보이면:
   ```bash
   pkill -9 -f ros2_control_node
   ```

7. **web bridge / npm dev server 중지.** 해당 터미널에서 Ctrl-C.

8. **최후의 수단** 프로세스가 멈춘 경우:
   ```bash
   pkill -9 -f 'ros2 launch'
   pkill -9 -f ros2_control_node
   pkill -9 -f realsense2_camera_node
   ```

---

## 12. 트러블슈팅

### 12.1 STT 결과 없음 (Whisper)

- 마이크 디바이스 확인. `MicConfig.device_index` 가
  `cobot_voice/cobot_voice/mic_controller.py` 에 `6` 으로 하드코딩되어 있다.
  호스트별 **확인 필요**:
  ```bash
  python3 -c "import sounddevice as sd; print(sd.query_devices())"
  ```
- `OPENAI_API_KEY` 로드 확인:
  ```bash
  python3 -c "from cobot_voice.env import get_required_env; print(bool(get_required_env('OPENAI_API_KEY')))"
  ```
- STT 를 우회하고 실패를 격리하려면 텍스트 모드 사용:
  ```bash
  ~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --text "피곤해요"
  ```

### 12.2 키워드 추출 실패 (`categories` 없음)

- `voice_order_flow` 는 상태를 해석할 수 없을 때 JSON 에 `success: false`
  와 `categories: []` 를 저장한다.
- 증상: `dispatched: True` 이지만 task manager 가 `FileOrderProvider` 가
  주문을 거절했다고 로깅, 또는 `voice_to_robot.py` 가 0이 아닌 코드로
  종료.
- freeform 모드에서는 더 명확한 키워드로 재시도:
  `피곤`, `집중`, `혈당`, `다이어트`.
- 또는 세션 동안 menu 모드로 전환:
  ```bash
  export COBOT_VOICE_PROMPT_MODE=menu
  ```

### 12.3 `latest_order.json` 이 생성되지 않음

- 경로 존재 확인:
  ```bash
  ls -la ~/cobot_ws/src/cobot2/cobot_voice/output/
  ```
- dotenv 도달 가능 확인:
  ```bash
  cat ~/cobot_ws/src/cobot2/cobot_voice/resource/.env       # should have OPENAI_API_KEY
  ```
- 로깅과 함께 실행:
  ```bash
  ~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --debug
  ```
  끝부분의 `[INFO] save_recommendation_order` 라인을 관찰.

### 12.4 `/task/start` 사용 불가

```bash
ros2 service list | grep task
# Expect /task/start
```

부재 시:

- `task_manager_node` 가 실행 중인지 확인: `ros2 node list | grep task_manager`.
- 시작 시 크래시했다면 T3 에서 다음을 찾아본다:
  - `unknown order_source=...`
  - `order_source='file' requires file_order_path parameter`
- 올바른 `order_source`/`file_order_path` 로 재 launch.

### 12.5 검출 결과 없음 (perception)

- `ros2 topic hz /detection/objects` — 너트가 보이면 > 0 Hz 여야 한다.
- 0 Hz 이면 카메라 점검:
  ```bash
  ros2 topic hz /camera/camera/color/image_raw
  ```
- 카메라는 살아있는데 검출이 0 이면, 임시로 게이트를 낮춤:
  ```bash
  ros2 param set /object_detection_node conf_threshold 0.40
  ```
- YOLO 모델이 로드되었는지 검증 — T1/T3 가
  `Loading YOLO-OBB model: ...` 를 로깅해야 한다.

### 12.6 매 검출마다 `transform_valid: false`

`perception_transform_node` 가 다음 경우 `transform_valid=false` 를 반환:

- OBB 내부 깊이 누락 (`median_inside_obb` 가 non-finite 반환). OBB 를
  키우거나 `cobot_perception/config/perception.yaml` 의
  `min_depth_camera_mm` 을 낮춤.
- TCP 읽기 실패 (`tcp_source: service` 일 때만). T3 로그의 증상:
  - `tcp source error: /robot/get_current_pose not ready`
  - `get_current_pose call timed out`
- Hand-eye 파일 미로드 — 시작 시 raise:
  `gripper2camera_npy is required.` `perception.yaml` 에 경로 설정.

robot_control 이 아직 정상이 아닌 초기 bring-up 동안에는 고정 TCP 로 폴백:

```bash
ros2 param set /perception_transform_node tcp_source fixed
```

…YAML 에 `fixed_tcp_xyz_mm` / `fixed_tcp_zyz_deg` 설정과 함께.

### 12.7 로봇 액션 사용 불가

```bash
ros2 action list | grep pick_and_place
# Expect /robot/pick_and_place
```

부재 시:

- `robot_control_node` 가 실행 중인가? `ros2 node list | grep robot_control_node`.
- real 모드라면 올바른 config 가 선택되었는가? T3 로그에서
  `Initializing DSR_ROBOT2 ...` (real) 대 `Using MOCK motion backend`
  (mock) 확인.
- 액션 서버는 in-process `robot_action_helper` 노드에서 호스팅된다 —
  `ros2 node list` 에 표시되는 것은 정상이며 중복이 아니다.

### 12.8 그리퍼가 응답하지 않음

- 그리퍼 ping:
  ```bash
  ping -c 3 192.168.1.1
  ```
- `gripper_backend: modbus` 확인 (real 모드 YAML) — **기본** YAML 은
  `mock` 사용.
- Modbus 연결성 검사. 네트워크에 따라 **확인 필요** — in-tree Modbus
  진단 명령은 없다.
- 정착하지 않는 close 는
  `failure_code=3 motion_fail "gripper close did not settle in time"` 로
  표면화. RG2 전원 LED + 공압 (해당 변형이라면) 점검.

### 12.9 컨베이어 시리얼 권한 오류

T4 에서 증상: `Failed to open serial port /dev/ttyACM0: ... Permission denied`.

```bash
sudo usermod -aG dialout $USER
# log out, log back in for the group change to take effect
```

또는 이번 세션만:

```bash
sudo chmod a+rw /dev/ttyACM0
```

확인:

```bash
ls -l /dev/ttyACM0
groups | grep dialout
```

포트가 사용 중이면:

```bash
sudo fuser -v /dev/ttyACM0
```

방해 프로세스 종료 (종종 Arduino IDE 시리얼 모니터).

### 12.10 `ROS_DOMAIN_ID` 불일치

증상: `ros2 node list` 가 비어있거나, 기대 노드의 일부만 보임; 한 터미널의
토픽이 다른 터미널에서 보이지 않음.

- 모든 터미널은 워크스페이스 source **이전에** 동일한 `ROS_DOMAIN_ID` 를
  export 해야 한다.
- 각 터미널의 실제 값 확인:
  ```bash
  echo $ROS_DOMAIN_ID
  ```
- 원격 호스트와 공유하려면 양쪽이 일치해야 한다. RMW 구현도 일치해야 한다
  (Humble 기본값은 `rmw_fastrtps_cpp`; 팀 참조는
  `cobot_bringup/config/params.yaml` 기준 `rmw_cyclonedds_cpp` 이지만 그
  파일은 자동으로 **로드되지 않는다** — 강제하려면 셸에서
  `RMW_IMPLEMENTATION` 설정).

### 12.11 Docker 가 ROS 토픽을 보지 못함

이 저장소는 Docker 를 사용하지 않는다 (§2.3 참조). 로컬에서 컨테이너를
도입했다면 `ROS_DOMAIN_ID` 와 `RMW_IMPLEMENTATION` 이 호스트와 일치해야
하며 **그리고** 네트워킹이 멀티캐스트를 허용해야 한다 (또는 FastDDS
discovery server 사용). 설정에 따라 **확인 필요**; 이 저장소는 어떤
설정도 하지 않는다.

### 12.12 Firebase 사용 불가

- writer (`firebase_bridge.py`) 는 `firebase_admin` 이 초기화에 실패하면
  조용히 no-op. 로봇 파이프라인은 영향받지 않는다.
- 진단:
  ```bash
  python3 -c "from cobot_voice.firebase_bridge import _ensure_session_ref; _ensure_session_ref(); print('ok')"
  ```
  정상 실행 중에는 삼켜지더라도 여기서는 예외가 표면화된다.
- 일반적 원인:
  - `FIREBASE_SERVICE_ACCOUNT` 미설정 또는 누락된 파일을 가리킴.
  - 서비스 어카운트 JSON 이 프로젝트에서 Firestore 접근 권한이 없음.
  - 호스트에서 외부 인터넷 없음.
- 필요시 bridge 를 완전 비활성화:
  ```bash
  ros2 launch cobot_bringup full_system.launch.py enable_firebase_status_bridge:=false ...
  ```

### 12.13 기타 운영 footgun (다른 곳에 이미 문서화됨)

- **펜던트 빨간 불** → 동작 명령이 움직이지 않고 조용히 성공한다. AUTO +
  Servo On 으로 전환.
- **`ros2 launch` 의 줄바꿈** → bash 가 분할하고 끝의 인자를 버린다. 한
  줄로 입력/붙여넣기.
- **좀비 `ros2_control_node`** → `pkill -9 -f ros2_control_node`.
- **실행 중 카메라 분리** → T2 에 `The device has been disconnected!`.
  다른 USB-3 포트에 다시 꽂고 T2 재시작.
- `task_manager.yaml` 와 `robot_control.yaml` 사이 **워크스페이스 불일치**
  는 task 필터를 통과한 goal 이 액션 서버에서 `failure_code=5` 로
  거절되는 원인이 된다. 단일 진실의 출처를 공유할 때까지 두 bound 블록을
  동기화 유지.

---

## 부록 — Quick command reference

```bash
# Build + source
cd ~/cobot_ws && colcon build --symlink-install && source install/setup.bash

# Mock e2e (one terminal)
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false enable_firebase_status_bridge:=false

# Real e2e (T1: dsr_bringup2; T2: realsense; T3: this)
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false dsr_mode:=real config_robot_control:=$(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config/robot_control.real.yaml order_source:=file file_order_path:=/home/aes/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json

# Conveyor
ros2 launch conveyor_controller conveyor_controller.launch.py

# Trigger task with a fake order (mock-mode quick check)
ros2 service call /task/start std_srvs/srv/Trigger "{}"

# Voice → robot end-to-end
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이"

# Single nut
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --dry-run
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew

# Status
ros2 topic echo /task/status
ros2 topic echo /task/result
ros2 topic echo /conveyor/place_ready

# Stop
ros2 service call /robot/stop std_srvs/srv/Trigger "{}"
```

심층 검사 명령 (파라미터, 액션 goal 등) 은
`docs/02_ros_node_architecture.md` §8 참조.
