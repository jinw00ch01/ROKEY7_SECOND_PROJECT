# 검증 체크리스트

통합 cobot 너트 피킹 시스템의 사전 점검 체크리스트다.
실제 하드웨어 세션 전마다, 그리고 perception, motion, calibration,
task-manager 코드를 수정할 때마다 위에서 아래로 따라간다.

## 목차

1. 문서 범위
2. Static 점검
3. ROS 그래프 점검
4. 음성 파이프라인 점검
5. Task Manager 점검
6. Perception 점검
7. Robot / Gripper Dry-Run 점검
8. 컨베이어 점검
9. 실제 하드웨어 사전 점검
10. 합격 기준

## 문서 세트

- `docs/01_system_architecture.md` — 시스템이 무엇을 왜 하는지.
- `docs/02_ros_node_architecture.md` — 노드 단위 인터페이스 레퍼런스,
  상태 머신, 디버깅 명령어.
- `docs/03_run_manual.md` — mock 및 real 운용 실행 순서.
- `docs/04_validation_checklist.md` — **이 파일**.
- `docs/cleanup_deletion_proposal.md` 및
  `_archive_cleanup/<YYYYMMDD>/cleanup_manifest.md` — 정리 기록.
  Static 점검 §2 섹션은 grep 범위에서 `_archive_cleanup/`을 명시적으로
  제외한다. 비활성으로 취급한다.

> **전반에 걸쳐 사용되는 명명 규약.** Doosan 측 **노드 이름**은
> 네임스페이스가 적용되어 있다(`/dsr01/robot_control_node`,
> `/dsr01/robot_action_helper`, `/dsr01/robot_pose_helper`). 그러나
> **서비스와 액션**은 절대 경로다(`/robot/pick_and_place`,
> `/robot/home`, `/robot/stop`, `/robot/get_current_pose`).
> `robot_control.yaml`에서 선행 `/`로 선언되며, `task_manager.yaml`에서
> 동일한 절대 이름으로 호출된다. 전체 인터페이스 표는
> `docs/02_ros_node_architecture.md` §3 참조.

---

## 1. 문서 범위

이 체크리스트는 시스템이 엔드-투-엔드로 **안전하고 운용 준비가 되었는지**
검증한다.

- 모든 패키지가 빌드되고, 모든 launch 파일이 로드되며, 모든 인터페이스가 존재한다.
- ROS 그래프에 예상된 노드, 토픽, 서비스, 액션이 포함된다.
- 음성 파이프라인이 유효한 주문을 생성하고, task manager가 이를 소비하며,
  perception이 변환된 후보를 반환하고, 액션 서버가 goal을 받는다 — 모두
  실제 모션 이전에 **mock 모드**에서.
- 실제 하드웨어 사전 점검(네트워크, USB, E-stop, 워크스페이스)이 통과한다.
- 다중 너트 실행 전에 단일 너트 실제 픽이 성공한다.

이 체크리스트는 모델 학습, 핸드-아이 캘리브레이션,
또는 web/Firebase 프로젝트 셋업은 다루지 **않는다**.

사용 방법:

- 각 항목을 ✅ 통과 / ❌ 실패로 표시한다. ❌ 항목은 건너뛰지 않는다.
- 자신의 세션 노트북에 근거를 기록한다(타임스탬프, 터미널 발췌).
- §10에 종료 기준이 있다. 거기 모든 항목이 통과해야만 시스템은 "준비됨"이다.

---

## 2. Static 점검

### 2.1 패키지가 깨끗하게 빌드된다

```bash
cd ~/cobot2_ws
colcon build --symlink-install
source install/setup.bash
```

기대값: 모든 패키지가 `Finished <<<`로 끝난다. `Failed <<<`이나
의존성 누락 오류가 없다.

존재하는 곳에서 단위 테스트를 실행한다.

```bash
colcon test --packages-select cobot_object_detection cobot_robot_control cobot_task_manager
colcon test-result --verbose
```

기대 테스트 파일(이미 저장소에 존재):

- `cobot_object_detection/test/test_model_paths.py`
- `cobot_robot_control/test/test_motion_sequence_workspace.py`
- `cobot_task_manager/test/test_order_provider_db.py`
- `cobot_task_manager/test/test_pick_offsets.py`
- `cobot_voice/`의 순수 Python 테스트(`pytest`로 직접 실행):
  ```bash
  cd ~/cobot2_ws/cobot_voice
  python3 -m pytest -q
  ```
  이는 `test_env.py`, `test_firebase_bridge.py`,
  `test_firebase_status_bridge.py`, `test_nut_recommendation.py`,
  `test_question_flow.py`, `test_web_voice_bridge_server.py`를 검증한다.

### 2.2 launch 파일이 존재하고 문법적으로 유효하다

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

빠른 문법 점검(실제로 노드를 시작하지 않는다 — `--show-args`는
description을 파싱한다).

```bash
ros2 launch cobot_bringup full_system.launch.py --show-args
ros2 launch cobot_bringup host_system.launch.py --show-args
ros2 launch cobot_bringup perception.launch.py --show-args
ros2 launch cobot_bringup robot.launch.py --show-args
ros2 launch conveyor_controller conveyor_controller.launch.py --show-args
```

기대값: 기본값과 함께 선언된 인자 목록, Python 예외 없음.

### 2.3 config 파일이 로드된다

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

최소한 다음이 있어야 한다.

- `cobot_object_detection/.../object_detection.yaml`
- `cobot_perception/.../perception.yaml`
- `cobot_robot_control/.../robot_control.yaml` 및 `robot_control.real.yaml`
- `cobot_task_manager/.../task_manager.yaml`
- `conveyor_controller/.../conveyor_controller.yaml`
- `cobot_voice/.../keyword_categories.json`,
  `nut_combo_rules.json`, `question_flow.json`

파싱 가능 여부 스팟 체크.

```bash
python3 -c "import yaml; yaml.safe_load(open('$(ros2 pkg prefix cobot_task_manager)/share/cobot_task_manager/config/task_manager.yaml'))"
python3 -c "import json; json.load(open('$(ros2 pkg prefix cobot_voice)/share/cobot_voice/config/keyword_categories.json'))"
```

기대값: 조용히 성공.

### 2.4 메시지 / 서비스 / 액션 인터페이스 존재

```bash
ros2 interface show cobot_msgs/msg/DetectedObject
ros2 interface show cobot_msgs/msg/DetectedObjectArray
ros2 interface show cobot_msgs/srv/DetectOnce
ros2 interface show cobot_msgs/srv/GetCurrentPose
ros2 interface show cobot_msgs/srv/GetNutOrder
ros2 interface show cobot_msgs/action/PickAndPlace
```

기대값: 각 명령이 `Could not find` 오류 없이 인터페이스 본문을 출력한다.

### 2.5 stale `command_parser_node` 참조 없음

`command_parser_node`와 `firebase_state_bridge`는 voice→robot 통합
정리 과정에서 제거되었다. 런타임 트리 어디에도 나타나서는 안 된다.

```bash
grep -RnE "command_parser_node|firebase_state_bridge" \
    cobot_msgs cobot_bringup cobot_object_detection cobot_perception \
    cobot_robot_control cobot_safety cobot_task_manager cobot_voice \
    conveyor_controller scripts 2>/dev/null
```

기대값: **출력 없음**. (`docs/` 내 기록용 변경 로그의 히트는 허용되며
정리할 필요가 없다.)

---

## 3. ROS 그래프 점검

mock 모드에서 전체 시스템을 launch한 후 실행한다(run manual §5).

### 3.1 노드

```bash
ros2 node list
```

기대 항목(mock 모드, `enable_realsense:=false`,
`enable_dsr_bringup:=false`, `enable_firebase_status_bridge:=true`):

- `/object_detection_node`
- `/perception_transform_node`
- `/dsr01/robot_control_node`
- `/dsr01/robot_action_helper`
- `/dsr01/robot_pose_helper`
- `/task_manager_node`
- `/firebase_status_bridge` (활성화된 경우에만)

real 모드에서는 추가로 `/camera/camera`(RealSense)와 `dsr_bringup2`의
`/dsr01/dsr_*` 컨트롤러도 기대한다.

`enable_firebase_status_bridge:=false`로 실행했다면, 해당 노드는
**없어야** 한다.

### 3.2 토픽

```bash
ros2 topic list -t
```

필수:

| 토픽 | 타입 |
|---|---|
| `/detection/objects` | `cobot_msgs/msg/DetectedObjectArray` |
| `/conveyor/place_ready` | `std_msgs/msg/Bool` |
| `/task/status` | `std_msgs/msg/String` |
| `/task/result` | `std_msgs/msg/String` |

real 모드에서는 추가로:

- `/camera/camera/color/image_raw`
- `/camera/camera/aligned_depth_to_color/image_raw`
- `/camera/camera/color/camera_info`

컨베이어를 실행하는 경우:

- `/conveyor_cmd` (`std_msgs/msg/String`)

### 3.3 서비스

```bash
ros2 service list -t | grep -E "task|robot|perception|conveyor"
```

필수:

- `/task/start                std_srvs/srv/Trigger`
- `/perception/detect_once    cobot_msgs/srv/DetectOnce`
- `/robot/home                std_srvs/srv/Trigger`
- `/robot/stop                std_srvs/srv/Trigger`
- `/robot/get_current_pose    cobot_msgs/srv/GetCurrentPose`

robot 서비스는 `robot_control.yaml`에서 선행 `/`로 선언되기 때문에
**절대** 이름을 사용한다. 호스트 helper 노드(home/stop은
`/dsr01/robot_action_helper`, pose 서비스는 `/dsr01/robot_pose_helper`)는
`dsr01` 네임스페이스 내에 있지만, 서비스 이름 자체는 prefix가 붙지 않는다.
Doosan 네이티브 상위 서비스는 `/dsr01/system/get_current_pose`에 있다
(`dsr_bringup2` 제공).

### 3.4 액션

```bash
ros2 action list -t
```

필수:

- `/robot/pick_and_place    cobot_msgs/action/PickAndPlace`

타입 검증:

```bash
ros2 action info /robot/pick_and_place -t
```

기대값: 서버 `/dsr01/robot_action_helper` (노드 — 그건 *맞게*
네임스페이스가 적용되어 있다); 클라이언트는 task가 시작되면
`/task_manager_node`를 포함한다.

---

## 4. 음성 파이프라인 점검

전체 시스템을 **mock + file 모드**로 launch하여 실행한다(추천이
실제로 task manager까지 흘러가도록).

```bash
ros2 launch cobot_bringup full_system.launch.py task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false order_source:=file file_order_path:=/home/aes/cobot2_ws/cobot_voice/output/latest_order.json
```

T1 task-manager 로그에 다음이 포함되는지 확인한다.

```
FileOrderProvider reading /home/aes/cobot2_ws/cobot_voice/output/latest_order.json
```

### 4.1 TTS 프롬프트

```bash
~/cobot2_ws/scripts/voice_to_robot.py --debug
```

첫 번째 prompt 단계에서 기대값:

- 콘솔 라인 `[TTS] 샤갈! 맞춤 견과류 콤보를 준비해드릴게요.`
- `COBOT_TTS_ENABLED=1`(기본값)이고 **그리고**
  `ffplay`(ElevenLabs) 또는 `spd-say`(fallback)가 설치되어 있으면
  음성 재생.

`COBOT_TTS_PROVIDER=elevenlabs`가 설정되어 있다면
`api.elevenlabs.io`로의 HTTP 요청을 기대한다. 실패는 로그에 기록되지만
플로우를 깨뜨리지는 않는다.

### 4.2 STT가 텍스트를 반환한다

검증 방법은 두 가지다.

- **STT 우회**(가장 빠른 sanity 체크):
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py --text "피곤하고 집중이 안 돼서 많이"
  ```
  기대 stdout:
  ```
  recognized_text : '피곤하고 집중이 안 돼서 많이'
  combo           : [{'nut': 'cashew', 'count': 3}, {'nut': 'walnut', 'count': 3}]
  success         : True
  dispatched      : True
  ```

- **실제 Whisper**(마이크 경로):
  ```bash
  ~/cobot2_ws/scripts/voice_to_robot.py
  ```
  기대값: 5 s 녹음 윈도우마다 콘솔에 `STT 결과: <Korean text>`가
  출력된다. 실패는 보통 Whisper API 예외로 드러난다.

### 4.3 키워드 추출이 condition + severity를 반환한다

4.2 단계 후 JSON을 점검한다.

```bash
cat ~/cobot2_ws/cobot_voice/output/latest_order.json
```

필수 필드와 제약:

| 필드 | 검증 |
|---|---|
| `request_id` | 비어있지 않은 문자열, 형식 `YYYYMMDD_HHMMSS` |
| `recognized_text` | STT/text 성공 시 비어있지 않음 |
| `categories` | 비어있지 않은 배열; 각 값 ∈ `{fatigue, blood_sugar, diet, focus}` |
| `intensity` | `low` / `normal` / `high` |
| `combo` | 비어있지 않은 `{nut, count}` 배열, `nut ∈ {almond, cashew, pistachio, walnut}` 및 `count ≥ 1` |
| `combo_text` | 비어있지 않은 한국어 문자열 |
| `success` | `true` |

`success`가 `false`이거나 `combo`가 비어있으면, 주문은
**`FileOrderProvider`에 의해 거부**되고 task manager는 아무것도 픽하지
않는다(이는 의도된 동작이다).

### 4.4 Order provider가 너트 개수를 반환한다

mock 모드(음성 없음)에서는 `task_manager.yaml`의 하드코딩된
개수(`mock_order_*`)로 검증된다. 트리거하고 관찰한다.

```bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
ros2 topic echo /task/status
```

file 모드에서는 `/task/start` 후 `/task/status` 로그 라인으로
검증된다.

```
[state] init
[state] detect
[state] select_target cashew
[state] pick_and_place cashew
...
```

여기 나타나는 클래스 이름은 JSON의 `combo`와 일치해야 한다.

> `db` 모드(`/db/get_nut_order`)는 이 저장소에 **Not Implemented**다.
> `order_source:=db`로 설정하면 timeout된다 — 이 점검은 건너뛴다.

### 4.5 `latest_order.json`이 존재하고 유효하다

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

기대값: `ok`.

---

## 5. Task Manager 점검

### 5.1 `/task/start` 사용 가능

```bash
ros2 service list | grep ^/task/start$
ros2 service type /task/start            # std_srvs/srv/Trigger
```

기대값: 존재, 타입 일치.

### 5.2 가짜 task 수락

mock 모드(또는 음성 실행 성공 후 file 모드)에서:

```bash
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

기대값:

- 첫 호출: `success=True message='task started'`.
- **루프가 아직 실행 중일 때** 후속 호출:
  `success=False message='task already running'`.

### 5.3 잘못된 task 거부

**file 모드**에서, 잘못된 주문을 시뮬레이션하고 worker가 이를 거부하는지
확인한다. `FileOrderProvider`는 `success=false`이거나 combo가 비었을 때
거부하며, 동일한 주문의 재실행을 막기 위해 `request_id`를 추적한다.

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

기대값: 주문이 fetch 시점에 거부되며 `/task/result`에 `failure
order_fetch_failed`(또는 동등한) 메시지가 나온다. 로봇은 움직이지 않는다.

> **검증 필요**: 방출되는 정확한 failure 문자열은
> `FileOrderProvider`의 예외 경로에 따라 다르다. 이 거부 점검의 성공
> 신호로는 어떠한 `[state] pick_and_place ...` 라인도 나타나지 않는
> 것을 본다.

### 5.4 상태 전이가 보인다

```bash
ros2 topic echo /task/status
# Trigger from another terminal
ros2 service call /task/start std_srvs/srv/Trigger "{}"
```

기대 시퀀스(성공 경로):

```
init
detect
select_target <class>
pick_and_place <class>
detect
...
done
```

실패 경로(완전성을 위해 반드시 관찰되어야 한다).

```
aborted home_failed
aborted order_fetch_failed
aborted action_failure
aborted failure_code=<N>
safety_stop
```

### 5.5 Task 결과 게시

```bash
ros2 topic echo /task/result --once
```

기대값: `success counts={...} skipped=[...]` 또는 `failure <reason>`로
끝나는 단일 라인. 결과는 task 실행당 정확히 **한 번** 게시된다.

---

## 6. Perception 점검

### 6.1 Detection 노드 실행 중

```bash
ros2 node list | grep object_detection_node
ros2 node info /object_detection_node
```

기대값: 존재; `/camera/camera/color/image_raw`를 구독하고
`/detection/objects`를 게시. 부팅 로그 라인
`Loading YOLO-OBB model: <path>`이 모델 해결을 확인한다.

완전한 mock(카메라 없음)으로 실행하는 경우
`mock_perception_node`로 대체한다.

```bash
ros2 run cobot_perception mock_perception_node
ros2 node list | grep mock_perception_node
```

### 6.2 `detect_once` 서비스 동작

```bash
ros2 service call /perception/detect_once cobot_msgs/srv/DetectOnce "{}"
```

기대값(채워진 장면이 있는 실제 perception):

- `success: true`
- `message: "transformed K/N detections"` 단, `K, N ≥ 0`.
- `objects.objects` 리스트(워크스페이스에 아무것도 없으면 비어있을 수 있음).

기대 실패 모드(모두 `success: false` 반환):

- `"no detection received yet"` — `object_detection_node`가 실행되지
  않았거나 아직 컬러 프레임이 없음.
- `"no depth frame received yet"` — depth 정렬 누락.
- `"no camera_info received yet"` — intrinsics 미수신.
- `"tcp source error: ..."` — `tcp_source: service`이고
  `/robot/get_current_pose`가 응답하지 않음.

`mock_perception_node`를 사용했다면, 모든 항목이 `transform_valid=true`인
하드코딩된 8-object 장면을 기대한다.

### 6.3 타겟이 유효한 `class_name`을 가진다

`detect_once`가 반환하는 각 항목에 대해:

- `class_name ∈ {almond, cashew, pistachio, walnut}` —
  `cobot_object_detection/config/object_detection.yaml`의 `class_names`와
  동일한 어휘.

응답에서 빠른 필터 점검 — 모든 `objects.objects[*].class_name`은 그
집합 안에 있어야 한다. 제안된 스키마의 "nut_type" 이름은 실제
`cobot_msgs/DetectedObject.msg`의 `class_name`에 해당한다.

### 6.4 타겟이 유효한 base 좌표 / `transform_valid`를 가진다

task manager가 받아들일 모든 항목에 대해(즉,
`target_selector.choose_target`에 전달되는 모든 것):

- `transform_valid: true` — 변환이 성공적으로 적용됨.
- `base_xyz.x`, `base_xyz.y`, `base_xyz.z` — 로봇 base 프레임에서
  밀리미터 단위의 0이 아닌 유한 float.
- `grasp_yaw` — 유한한 라디안 값.
- `short_axis_mm`, `long_axis_mm` — 실제 너트 치수에 부합하는 양의
  float(대략 범위: 5–25 mm).

스팟 체크 sanity: 채워진 워크스페이스 장면은 `transform_valid=true`이고
`base_xyz` 값이 `task_manager.yaml` 워크스페이스 박스(`x ∈ [200, 700]`,
`y ∈ [-300, 300]`, `z ∈ [40, 80]`) 안에 있는 여러 항목을 가져야 한다.

모든 항목이 `transform_valid: false`로 돌아온다면, Run Manual §12.6을 본다.

---

## 7. Robot / Gripper Dry-Run 점검

이들은 **mock 모드**에서 실행한다(`motion_backend: mock`,
`gripper_backend: mock` — 기본 `robot_control.yaml`).

### 7.1 Pick 액션이 타겟을 받는다

```bash
ros2 action info /robot/pick_and_place
```

기대값: 서버 노드 `/dsr01/robot_action_helper`; task가 시작되면
클라이언트에 `/task_manager_node`가 포함된다.

helper 스크립트로 dry-run 타겟을 보낸다.

```bash
~/cobot2_ws/scripts/pick_one.py cashew --dry-run
```

기대값: 해결된 goal(`base_xyz`, `grasp_yaw`,
`short_axis_mm`, 계산된 pre-grasp width)을 출력하고 액션 goal을 보내지
**않고** 종료한다.

### 7.2 모션 단계가 올바르게 로그된다

`--dry-run` 없이 액션 서버는 모든 단계를 진행한다. launch 터미널을 본다.

```bash
~/cobot2_ws/scripts/pick_one.py cashew
```

기대 단계 피드백(mock 백엔드는 각 단계를 즉시 완료):

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

액션 결과: `success: True, failure_code: 0`.

### 7.3 그리퍼 close/open 시퀀스가 올바르게 로그된다

mock 모드에서 그리퍼 백엔드는 `gripper_controller.py`의 디버그 로그를
출력한다. 다음을 찾는다.

- `pre_grasp_width` 단계가 `move_to(...)`를 트리거하고 대기한다.
- `grasp` 단계가 `close()`와 `wait_until_idle`을 트리거한다.
- `verify_grip`이 `is_grip_detected()`를 호출한다(mock은 True 반환).
- `place` 단계가 `open()`과 `wait_until_idle`을 트리거한다.

`verify_grip`이 실패하면(mock에서 False 반환) — 코드가 변경되지
않는 한 일어나서는 안 된다. mock은 기본적으로 True를 반환한다. 여기서의
실패는 코드 회귀로 취급한다.

### 7.4 dry-run에서 실제 모션이 발생하지 않는다

**기본** YAML이 사용 중인지 확인한다. launch 터미널은 다음을 로그해야
한다.

```
Using MOCK motion backend ...
Using MOCK gripper backend ...
```

…**다음이 아님**:

```
Initializing DSR_ROBOT2 ...
Initializing Modbus RG2 ...
```

후자가 보이면 **real** YAML이 잘못 로드된 것이다 — 멈추고
다시 launch한다. 다음 픽에서 로봇이 움직일 것이다.

추가로 `enable_dsr_bringup:=false`인 경우, `dsr_*` 토픽이 보이지
않아야 한다.

```bash
ros2 topic list | grep ^/dsr01/ || echo "no /dsr01/ topics — expected for mock-only"
```

(`robot_control_node`가 그 네임스페이스에 있기 때문에 일부 `/dsr01/...`
서비스가 존재하지만, **모터 명령**은 stub이다.)

---

## 8. 컨베이어 점검

컨베이어만 launch한다(`/dev/ttyACM0`의 실제 Arduino).

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py
```

기대 부팅 로그:

```
Connected to Arduino serial port /dev/ttyACM0 at 115200 baud
Listening on /conveyor_cmd for commands: F<1-100>, R<1-100>, STOP
Place-ready trigger: one False->True edge on /conveyor/place_ready = one movement
                     (command=R80, duration=5.00s, then STOP). Distance is approximate;
                     exact distance requires firmware step mode.
```

### 8.1 `place_ready` edge가 정확히 한 번만 트리거된다

한 터미널에서 컨베이어 로그를 본다. 다른 터미널에서:

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
```

즉시 기대값:

```
[conveyor_start] command=R80 duration=5.00s (place_ready edge)
```

`auto_run_duration_sec`(기본 `5.0` s) 후:

```
[conveyor_stop]  command was R80, duration=5.00s elapsed
```

edge 트래커를 리셋하기 위해 `false`를 보내고, 다시 `true`를 보내
**다음** edge가 또 한 번의 단일 advance를 발생시키는지 검증한다.

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: false}"
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
```

기대값: 또 다른 `[conveyor_start] ... [conveyor_stop]` 쌍.

### 8.2 컨베이어가 예상 시간 후 정지한다

`[conveyor_start]`와 `[conveyor_stop]` 로그 라인 사이의 간격을
측정한다 — `auto_run_duration_sec`와 약 100 ms 이내로 일치해야 한다.
`STOP`은 내부 일회성 `create_timer` 콜백으로 전송된다.

duration을 라이브로 변경하면:

```bash
ros2 param set /conveyor_serial_node auto_run_duration_sec 2.0
```

…다음 edge는 2초 실행을 발생시켜야 한다.

### 8.3 새로운 edge 없이 트리거가 반복되지 않는다

중간 `false` **없이** `true`를 다시 보낸다.

```bash
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /conveyor/place_ready std_msgs/msg/Bool "{data: true}"   # second message
```

기대값: 첫 번째 메시지만 시작 로그를 만든다. 두 번째는 no-op이다
(`_last_place_ready`가 이미 `True`이기 때문). `[conveyor_start]` 라인
개수로 확인한다.

**이전의 timed 실행이 아직 활성화되어 있는 동안** 도착하는 `true`는
로그되고 무시되어야 한다.

```
Ignoring place_ready trigger while conveyor auto-run is active
```

(이를 위해서는 5 s 윈도우 내에서 `false → true → true`를 빠르게
보내야 한다.)

---

## 9. 실제 하드웨어 사전 점검

이들 중 어느 것도 건너뛰지 않는다. 여기서의 각 ❌는 **정지**, 실제 모션
없음을 의미한다.

하드웨어 및 네트워크 항목은 `docs/03_run_manual.md` §2.4 / §7.1에도
열거되어 있다 — 둘 다 다시 점검하되, 정식 go/no-go 게이트는 이 섹션이다.

- [ ] **로봇 ping**: `ping -c 3 192.168.1.100`이 0 % 손실을 반환한다.
- [ ] **그리퍼 ping**: `ping -c 3 192.168.1.1`이 0 % 손실을 반환한다.
- [ ] **RealSense USB**: `lsusb | grep -i realsense`가 디바이스를 보여준다.
- [ ] **RealSense 스트림 활성**:
  카메라 launch가 `RealSense Node Is Up!`에 도달한 후
  `ros2 topic hz /camera/camera/aligned_depth_to_color/image_raw`가
  ~30 Hz를 보여준다.
- [ ] **컨베이어 시리얼**: `ls /dev/ttyACM*`이 포트를 나열한다; 현재
  사용자가 `dialout` 그룹에 있다(`groups | grep dialout`); 컨베이어
  launch가 `Connected to Arduino serial port ...`에 도달한다.
- [ ] **캘리브레이션 파일**:
  `cobot_perception/config/perception.yaml`의 `gripper2camera_npy`
  파라미터가 존재하는 `T_gripper2camera.npy`(4×4 배열)를 가리킨다.
  Perception 시작 로그에 `Loaded gripper2camera from <path>`이
  포함된다.
- [ ] **펜던트**: AUTO 모드 + Servo On + 상태 인디케이터 **흰색**.
  (빨간 인디케이터 → motion API가 조용히 no-op한다.)
- [ ] **E-stop이 운전자 손이 닿는 거리**에 있다.
- [ ] **워크스페이스 정리**: approach / transit / return 경로에
  손가락, 케이블, 공구 없음; 컨베이어 벨트 정리.
- [ ] **Pick offset 최신**:
  `cat ~/cobot2_ws/cobot_config/config/pick_offsets.yaml`이 가장 최근의
  성공한 튜닝과 일치한다.
- [ ] **Real config 선택됨**:
  `config_robot_control:=...robot_control.real.yaml`이 launch 명령줄에
  있다; launch 터미널이 `Initializing DSR_ROBOT2 ...`와
  `Initializing Modbus RG2 at 192.168.1.1:502`를 보여준다.
- [ ] **단일 너트 dry-run 먼저**:
  비-dry-run 명령이 실행되기 **전에**
  `~/cobot2_ws/scripts/pick_one.py <class> --dry-run`이 합리적인 base
  좌표를 반환한다(`docs/03_run_manual.md` §8 참조).
- [ ] **오늘 mock dry-run 통과** — §7의 모든 항목이 동일 세션에서
  체크됨.

---

## 10. 합격 기준

다음 모두가 동일 세션에서 통과할 때만 시스템은 "운용 준비됨"이다.

- [ ] **Static 점검 (§2)** — `colcon build`가 깨끗하고,
  `colcon test`가 통과하며, 모든 인터페이스가 해결되고, `docs/` 외부에
  `command_parser_node` / `firebase_state_bridge` 참조가 남아있지
  않다.
- [ ] **ROS 그래프 (§3)** — §3에 나열된 모든 필수 노드, 토픽, 서비스,
  액션이 존재한다.
- [ ] **음성 파이프라인 (§4)** — text 모드 및 (해당하는 경우)
  마이크 모드가 `success: true`인 유효한 `latest_order.json`을
  생성한다. 추천 카테고리와 intensity가 적어도 한 샘플에서 발화 의도와
  일치한다.
- [ ] **Task manager (§5)** — `/task/start`가 응답한다; 유효한 주문이
  루프를 `[state] done`까지 구동하고 `/task/result`가 `success`로
  끝난다; 잘못된 주문은 로봇 모션 없이 거부된다.
- [ ] **Perception (§6)** — `detect_once`가 `success=true`를 반환하고,
  `base_xyz`가 `task_manager.yaml` 워크스페이스 박스 안에 있고
  `transform_valid=true`인 항목이 적어도 하나 있다.
- [ ] **로봇 dry-run (§7)** — 모든 픽 단계가 순서대로 로그되고, 액션이
  `success=True, failure_code=0`을 반환하며, launch 터미널이 MOCK
  백엔드 사용을 확인한다.
- [ ] **컨베이어 (§8)** — `false→true` edge당 정확히 한 쌍의
  `[conveyor_start]/[conveyor_stop]`이 있다; 유지된 `true`는
  재트리거하지 않는다.
- [ ] **실제 하드웨어 사전 점검 (§9)** — 모든 체크박스 체크됨.
- [ ] **단일 너트 실제 테스트** — `~/cobot2_ws/scripts/pick_one.py <class>`가
  취소 없이 선택한 클래스에 대해 성공하며, 복귀 자세 place_ready edge가
  컨베이어를 정확히 한 번 발화시킨다.
- [ ] **다중 너트 task** — `~/cobot2_ws/scripts/voice_to_robot.py
  --text "..."`(또는 마이크 동등물)이 전체 루프를 `[state] done`까지
  구동하고 `/task/result success counts={...}`가 된다. 소비된 모든
  너트가 정확히 한 번의 컨베이어 advance를 발생시킨다.
- [ ] **상태 가시성** — `/task/status`, `/task/result`,
  `/conveyor/place_ready`가 예상 메시지를 echo한다; Firebase가
  활성화된 경우, 웹 UI가 끝에 `display_state: completed`와
  `robot_state: task_done`을 보여준다.
- [ ] **안전하지 않은 모션 관찰 없음** — 다중 너트 실행 동안 충돌 없음,
  E-stop 발동 없음, `failure_code` 1, 3, 4, 또는 5로 종료되는 단계 없음.

어떤 기준이라도 실패하면, 정지하고 재실행 전에
`docs/03_run_manual.md` §12의 관련 트러블슈팅 섹션을 통해 라우팅한다.
