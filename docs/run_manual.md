# Cobot 실행 매뉴얼 (4-Terminal)

각 명령은 **한 줄**로 입력. 새 터미널마다 `source` 1회 필수.

라인-랩(긴 명령이 여러 줄로 표시되는 현상)이 일어나면 bash가 둘로 쪼개서 실행하므로 args가 드롭됩니다. 터미널 폭을 충분히 넓히거나 명령을 짧게 유지하세요.

---

## 사전 점검 (T4 또는 임시 터미널)

```
ping -c 3 192.168.1.100
```
```
ping -c 3 192.168.1.1
```
```
lsusb | grep -i realsense
```

셋 다 응답 OK여야 진행.

---

## T1 — Doosan 로봇 (dsr_bringup2)

```
source ~/cobot_ws/install/setup.bash
```
```
ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=192.168.1.100 port:=12345
```

**대기 신호:**
- `Connected to DRCF`
- `ROBOT_STATE : STATE_STANDBY`
- `Configured and activated dsr_controller2`
- `Configured and activated joint_state_broadcaster`

이 터미널은 그대로 둠 (종료 시 로봇 끊김).

**자주 보는 함정:**
- `Controller already loaded` 에러 → 좀비 `ros2_control_node`가 살아있음. T1 Ctrl+C → `pkill -9 -f ros2_control_node` → T1 재실행.

---

## T2 — RealSense

```
source ~/cobot_ws/install/setup.bash
```
```
ros2 launch realsense2_camera rs_launch.py enable_color:=true enable_depth:=true align_depth.enable:=true
```

**대기 신호:** `RealSense Node Is Up!`

**align_depth가 launch arg로 안 잡힌 경우** (라인 랩 등) — T4에서:
```
ros2 param set /camera/camera align_depth.enable true
```

**검증 (T4에서):**
```
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw
```
→ ~30 Hz 나오면 OK, Ctrl+C.

**자주 보는 함정:**
- `The device has been disconnected!` → USB 케이블 빠짐 → 물리 재연결 + 다른 USB-3 포트 시도.

---

## T3 — cobot 파이프라인

```
source ~/cobot_ws/install/setup.bash
```

용도에 따라 두 가지 중 하나를 선택:

> ⚠️ **중요**: 아래 명령은 반드시 **한 줄**로 입력. 터미널에서 줄바꿈하면 bash가 끊어서 별개 명령으로 해석함 (`task_autostart:=false: command not found` 에러). 줄바꿈 필요하면 줄 끝에 `\` 붙일 것.

### T3-A) 기본 / 디버깅용 (mock 모드)

```
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false
```

T4에서 `pick_one.py`, `pick_all.py` 직접 사용. task_manager는 백업으로만 떠있음.

### T3-B) 음성 통합용 (file 모드, voice_to_robot.py와 연동)

한 줄 버전:

```
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false order_source:=file file_order_path:=/home/choijinwoo/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
```

또는 `\` 사용한 multi-line 버전 (각 줄 끝에 `\`, 그 뒤 공백 없음):

```
ros2 launch cobot_bringup full_system.launch.py \
    task_autostart:=false \
    enable_realsense:=false \
    enable_dsr_bringup:=false \
    order_source:=file \
    file_order_path:=/home/choijinwoo/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
```

task_manager가 `latest_order.json`을 자동 소비. T4에서 `voice_to_robot.py` 실행 시 자동 픽업 시작.

**검증**: 시작 직후 task_manager 로그에 다음 줄이 떠야 file 모드:
```
FileOrderProvider reading /home/choijinwoo/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json
```
이 줄이 없으면 mock 모드로 폴백된 것 — 명령어 다시 확인.

**대기 신호 (공통, 5줄):**
- `Initializing DSR_ROBOT2 (id=dsr01, model=m0609)`
- `Initializing Modbus RG2 at 192.168.1.1:502`
- `robot_control_node ready (action=/robot/pick_and_place)`
- `Service /perception/detect_once ready`
- `Subscribed to /camera/camera/color/image_raw, publishing on /detection/objects`

T3-B에서 추가로:
- `FileOrderProvider reading /home/.../latest_order.json`

**arg 의미:**
- `task_autostart:=false` — task_manager 부팅 직후 자동 시작 안 함. T4에서 `/task/start` 또는 `voice_to_robot.py`로 트리거.
- `enable_realsense:=false` — T2에서 이미 띄움
- `enable_dsr_bringup:=false` — T1에서 이미 띄움
- `order_source:=file` (T3-B) — task_manager가 latest_order.json을 주문서로 사용
- `file_order_path:=...` (T3-B) — JSON 절대경로

---

## T4 — 검증 / 픽 명령

```
source ~/cobot_ws/install/setup.bash
```

### 1) 빠른 sanity check

```
ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw
```
30 Hz 확인 후 Ctrl+C.

```
ros2 service call /robot/get_current_pose cobot_msgs/srv/GetCurrentPose "{}"
```
`success: True` + xyz_mm 값.

### 2) detect 미리보기 (dry-run, 액션 안 보냄)

```
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --dry-run
```
→ 검출된 base_xyz / grasp_yaw / short_axis 출력. 좌표가 합리적인지 확인.

### 3) 단일 픽 (캘리브레이션 / 디버깅)

⚠️ **펜던트 확인: AUTO 모드 + Servo On + 로봇 등 흰색 점멸**
- 빨간 등이면 motion command가 silent fail (성공 리턴되지만 로봇 안 움직임).

```
~/cobot_ws/src/cobot2/scripts/pick_one.py cashew --z-override 315
```

옵션:
- `--z-override <mm>` : detect z 무시하고 강제 z 사용 (sweet spot 찾을 때)
- `--pre-grasp-width <mm>` : 그리퍼 사전 폭 (default = short_axis + 15)
- `--dry-run` : 액션 보내지 않고 좌표만 출력

다른 클래스도 동일:
```
~/cobot_ws/src/cobot2/scripts/pick_one.py almond --z-override 315
~/cobot_ws/src/cobot2/scripts/pick_one.py pistachio --z-override 315
~/cobot_ws/src/cobot2/scripts/pick_one.py walnut --z-override 315
```

### 4) 연속 픽 (8개 / 클래스별 카운트 자동화)

`pick_all.py`는 detect → pick → 반복으로 여러 개 자동 처리. 라운드로빈으로 클래스 균형 유지.

**각 클래스 2개씩 (총 8개, 데모 시나리오):**
```
~/cobot_ws/src/cobot2/scripts/pick_all.py --per-class 2 --z-override 315
```

**클래스별 다른 개수:**
```
~/cobot_ws/src/cobot2/scripts/pick_all.py --counts cashew=3,almond=2,pistachio=1,walnut=2 --z-override 315
```

**검출된 거 다 (카운트 캡 없음):**
```
~/cobot_ws/src/cobot2/scripts/pick_all.py --z-override 315
```

옵션:
- `--per-class N` : 모든 클래스에 N개씩 (with `--order`)
- `--counts cashew=2,almond=1,...` : 클래스별 명시 (listed class만 픽, 나머지는 0)
- `--max-picks 12` : 안전 캡 (기본 12)
- `--max-failures 3` : 연속 실패 N회 시 자동 중단 (기본 3)
- `--inter-pick-delay 0.5` : 픽 사이 대기 (기본 0.5s)
- `--order cashew,almond,pistachio,walnut` : 라운드로빈 동률 시 우선순위

### 5) 음성 → 자동 로봇 픽업 (voice_to_robot.py)

**전제 조건:** T3-B (file 모드)로 띄워져 있어야 함.

`cobot_voice` 추천 → `latest_order.json` 저장 → `/task/start` 호출 → task_manager 자동 픽업까지 한 번에.

#### 텍스트 모드 (가장 빠른 검증, 마이크 X)

```
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이 도움 필요해요"
```

기대 출력:
```
recognized_text : '피곤하고 집중이 안 돼서 많이 도움 필요해요'
combo           : [{'nut': 'cashew', 'count': 3}, {'nut': 'walnut', 'count': 3}]
success         : True
dispatched      : True
```

→ T3 터미널에 `[state] select_target ...` 시작되면 정상.

#### 마이크 모드 (Hello Rokey 깨우기 → 음성 STT)

```
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py
```

흐름:
1. "**Hello Rokey**" 발음 (모델 학습된 영어 발음)
2. wake 감지 후 "오늘 컨디션 어떤가요?" 음성 → 5초 녹음 (예: "피곤해요")
3. "강도는?" → 5초 녹음 (예: "많이")
4. 추천 결과 음성 안내 + 자동 픽업 시작

#### 디버그 모드 (마이크 없이 키보드 입력)

```
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --debug
```

각 단계마다 터미널 prompt에 입력.

#### 옵션

- `--text "..."` : STT/wake 우회
- `--debug` : 키보드 입력으로 STT 흉내
- `--no-dispatch` : `latest_order.json`만 저장하고 robot 트리거는 건너뜀 (검증용)

#### 흔한 함정

- T3가 T3-A (mock 모드)로 떠 있으면 voice_to_robot 트리거해도 mock 주문(2개씩)이 실행됨. T3-B로 띄웠는지 확인.
- `dispatched: False` 나오면 `/task/start` 서비스 미존재 → T3 재시작.
- `success: False` 나오면 카테고리 추출 실패 → 더 명확한 키워드("피곤", "집중", "혈당", "다이어트")로 다시 시도.

### Sweet spot 찾는 법 (Z 캘리브레이션)
1. 첫 시도: `pick_one.py cashew --z-override 325` (보수적, 작업대 닿을 위험 적음)
2. 그리퍼가 너트 위에서만 닫히면 → z를 5 mm씩 낮춰서 재시도 (320 → 315 → ...)
3. 작업대 표면을 누르거나 충돌 의심되면 즉시 E-stop → z 더 높여서 재시도
4. 한 클래스에서 잘 잡히는 z 찾으면 그 값으로 `pick_all.py --z-override` 사용

### XY 정렬 (그리퍼 한쪽 쏠림)
파일: `cobot_robot_control/config/robot_control.yaml`의 `grasp_local_offset_xy_mm: [dx, dy]`
- 그리퍼 로컬 좌표계에서 (yaw에 따라 회전됨)
- 한쪽 finger만 너트 닿으면 빈 finger 방향으로 +/- 조정
- 변경 후 빌드 + T3 재시작 필요

---

## 정상 부팅 순서

| 순서 | 터미널 | 진행 조건 |
|---|---|---|
| 1 | T1 dsr_bringup2 | STANDBY + 컨트롤러 active |
| 2 | T2 RealSense | Node Is Up + align_depth 30 Hz |
| 3 | T3 cobot_bringup (T3-A 또는 T3-B) | 4개 노드 ready 메시지 |
| 4 | T4 sanity check | hz 30, pose OK |
| 5 | T4 픽 시작 | T3-A: pick_one/pick_all<br>T3-B: voice_to_robot.py |

### 시나리오별 T3 모드 선택

| 사용 목적 | T3 모드 | T4 명령 |
|---|---|---|
| 디버깅 / 캘리브레이션 / 단일 픽 | T3-A (mock) | `pick_one.py <class>` |
| 8-pick 데모 / 수동 카운트 지정 | T3-A (mock) | `pick_all.py --counts ...` |
| 음성/텍스트 자동화 (end-to-end) | **T3-B (file)** | **`voice_to_robot.py --text "..."`** |

---

## 종료 순서

역순: T3 Ctrl+C → T2 Ctrl+C → T1 Ctrl+C. T4는 그냥 닫음.

전체 강제 종료가 필요하면:
```
pkill -9 -f 'ros2 launch'
pkill -9 -f ros2_control_node
pkill -9 -f realsense2_camera_node
```

---

## 알려진 이슈 / 주의사항

### 1. ✅ 두 번째 픽 액션 hang (해결됨)
액션 server / pose service를 별도 helper 노드 + 자체 executor로 분리. helper 노드 생성 시 `use_global_arguments=False`로 launch의 `__node:=robot_control_node` 리맵 차단. 연속 픽 정상 동작.

### 2. ✅ verify_grip 너무 빠름 (해결됨)
`gripper_controller.wait_until_idle`이 두 단계: busy=True 먼저 본 후 busy=False 대기. 이전엔 close() 직후 stale "idle" 읽고 즉시 verify_grip로 넘어가 grip_detected stale value 사용. 이제 실제 모션 끝까지 대기.

### 3. Z 캘리브레이션 (`depth_offset_mm`)
파일: `cobot_perception/config/perception.yaml`
- 너무 약하면 (예: -5) 그리퍼가 너트 위에서 닫혀 못 잡음
- 너무 강하면 (예: -40) 작업대를 뚫어 충돌 위험
- 환경마다 다름 — `pick_one.py --z-override`로 sweet spot 찾고 그 값에 맞게 yaml 조정
- 현재 설정값: `depth_offset_mm: -35.0`, perception이 z~63mm 정도 보고함 → **`--z-override` 생략하고 perception 값 그대로 사용 권장** (이전 값 `--z-override 315`는 TCP 설정이 다른 환경에서만 통함)

#### 클래스별 미세조정 (`PER_CLASS_Z_OFFSET`)
- `scripts/pick_all.py`, `scripts/pick_one.py` 상단 dict: 견과 별 mm 보정. 음수 = 더 깊이 그립.
- task_manager 경로용은 `cobot_task_manager/config/task_manager.yaml`의 `per_class_z_offset_*_mm`. 두 곳 동기화 필요.
- 현재 default: `walnut: -1.0`, 나머지 0.0.

#### Return pose (반납함 z)
- `pick_all.py` / `pick_one.py`: `DEFAULT_RETURN_XYZ = (367.0, -150.0, 70.0)`
- `cobot_task_manager/config/task_manager.yaml`: `return_xyz_mm: [367.0, -150.0, 70.0]`
- 두 값 동기화 필수. yaml 변경 후 T3 재시작 필요 (메모리 캐시).

### 4. XY 정렬 (TCP 바이어스)
Doosan TCP가 그리퍼 finger 중심과 일치하지 않으면 한쪽 쏠림 발생.
파일: `cobot_robot_control/config/robot_control.yaml`의 `grasp_local_offset_xy_mm: [dx, dy]`
- gripper 로컬 좌표 (yaw로 자동 회전)
- 현재 설정값: `[1.5, 0.0]` (사용자 미세조정 결과)

### 5. 라인-랩
긴 명령이 두 번째 줄로 넘어가면 bash가 별도 명령으로 처리해 args 드롭. 항상 한 줄.

### 6. 좀비 ros2_control_node
launch만 죽이면 자식 ros2_control_node가 살아남아 다음 launch에서 controller 충돌.
```
pkill -9 -f ros2_control_node
```

### 7. 그리퍼 힘
`cobot_robot_control/config/robot_control.yaml`의 `gripper_force_x10`. 현재 150 (15 N). 견과 너무 짓눌리면 더 낮춤, 안 잡히면 200 (20 N) 정도로 올림.

---

## 헬퍼 스크립트

위치: `/home/choijinwoo/cobot_ws/src/cobot2/scripts/`

| 스크립트 | 용도 | 필요 launch 모드 |
|---|---|---|
| `pick_one.py` | 단일 클래스 1개 픽 — 캘리브레이션, 디버깅 | T3-A (mock) |
| `pick_all.py` | 연속 픽 — 클래스별 카운트 / 라운드로빈 자동화 | T3-A (mock) |
| `voice_to_robot.py` | **음성/텍스트 → 추천 → 자동 픽업** (end-to-end) | T3-B (file) |

ROS workspace를 source한 후 직접 실행 가능 (`#!/usr/bin/env python3` shebang + chmod +x).

```
~/cobot_ws/src/cobot2/scripts/pick_one.py --help
~/cobot_ws/src/cobot2/scripts/pick_all.py --help
~/cobot_ws/src/cobot2/scripts/voice_to_robot.py --help
```

으로 옵션 확인 가능.

### voice_to_robot.py 내부 흐름

```
사용자 텍스트/음성
  → cobot_voice 추천 엔진 (categories + intensity → combo)
  → cobot_voice/output/latest_order.json 저장
  → ros2 service call /task/start (cobot_task_manager 트리거)
  → task_manager: detect_once → target_select → pick_and_place 반복
  → 작업 완료 시 [state] done 발행
```

### 의존하는 ROS 인터페이스

| 인터페이스 | 제공자 | 용도 |
|---|---|---|
| `/perception/detect_once` (서비스) | `perception_transform_node` | 1회 객체 탐지 |
| `/robot/pick_and_place` (액션) | `robot_control_node` | 단일 픽 동작 |
| `/task/start` (서비스, std_srvs/Trigger) | `task_manager_node` | 워커 시작 트리거 |
| `/task/status`, `/task/result` (토픽, String) | `task_manager_node` | 진행 상태 (구독자 추가 가능) |
