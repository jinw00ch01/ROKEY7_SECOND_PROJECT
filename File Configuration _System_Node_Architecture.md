1. ' /home/choijinwoo/cobot_ws/src/cobot2'에 존재하는 디렉토리 중에 /home/choijinwoo/cobot_ws/src/cobot2/nuts_data_recording 디렉토리를 제외한 다른 디렉토리의 이름 앞에 [lecture]를 넣고, 그 디렉토리 내 존재하는 파일들도 코드적으로 문제 없게 만들것.

2. 아래 요구사항에 맞는 구조를 만들어볼것.

# 파일 구성 + 시스템/노드 아키텍쳐

아래가 현재 확정 조건을 반영한 최종 정리입니다.

## 1. 시스템 아키텍처

```
User Speech
  ↓
[Host] voice_processing_node
  ↓
[Host] command_parser_node
  ↓
[Host] policy_selector_node
  ↓
[Host] task_manager_node
  ├──────────────→ [Host] robot_control_node
  │                    ↓
  │              Doosan ROS2 Package
  │              dsr_bringup2 / dsr_msgs2 / dsr_common2
  │                    ↓
  │              Doosan M0609 + RG2
  │
  └──────────────→ [Host] perception_transform_node
                       ↑
                 [Docker] object_detection_node
                       ↑
                 [Host] RealSense D435i
```

핵심 구조는 **음성 → 키워드 추출 → 정책 선택 → 6칸 배분 계획 → 객체 인식 → 좌표 변환 → Doosan 패키지로 로봇 실행**입니다.

---

## 2. 실행 위치 기준

```
Host
├── RealSense D435i launch
├── Doosan bringup
├── voice_processing_node
├── command_parser_node
├── policy_selector_node
├── task_manager_node
├── perception_transform_node
├── robot_control_node
├── gripper_dio_controller
└── safety_manager_node

Docker
└── object_detection_node
```

Doosan 패키지는 `cobot2` 안에 복사하지 않고, 기존 `cobot_ws/src`에 있는 `dsr_bringup2`, `dsr_msgs2`, `dsr_common2`를 사용합니다.

---

## 3. 노드 구조

### `voice_processing_node`

```
역할:
- Wake word: "안녕 로키"
- STT 수행
- 사용자 발화 텍스트 publish

Pub:
- /voice/text
```

---

### `command_parser_node`

```
역할:
- 사용자 발화에서 키워드 추출
- action 판단
- 예: sort, stop, home

Sub:
- /voice/text

Pub:
- /command/parsed
```

---

### `policy_selector_node`

```
역할:
- 키워드 기반 정책 선택
- 사전 정의된 6칸 배분 조합 결정

Sub:
- /command/parsed

Pub:
- /policy/selected
```

예:

```
"건강하게 나눠줘"
→ keyword: 건강
→ policy: health_mix
→ slot_1~slot_6 배분 조합 생성
```

---

### `object_detection_node` — Docker

```
역할:
- RealSense RGB/Depth topic 구독
- 6종 객체 검출
- bbox, center, depth, camera frame point publish

Sub:
- /camera/color/image_raw
- /camera/aligned_depth_to_color/image_raw
- /camera/color/camera_info

Pub:
- /detection/objects
```

---

### `perception_transform_node`

```
역할:
- detection 결과를 robot base 좌표계로 변환
- hand-eye calibration 적용
- grasp pose 후보 생성

Sub:
- /detection/objects

Pub:
- /perception/objects_base
```

---

### `task_manager_node`

```
역할:
- 전체 작업 흐름 관리
- policy에 따라 target object와 destination slot 결정
- perception 결과 중 다음 pick 대상 선택
- robot_control_node에 pick/place 요청
- 실패, 재시도, 완료 처리

Sub:
- /command/parsed
- /policy/selected
- /perception/objects_base

Action Client:
- /robot/pick_and_place

Pub:
- /task/status
- /task/result
```

---

### `robot_control_node`

```
역할:
- 상위 /robot/pick_and_place Action Server 제공
- 내부적으로 Doosan ROS2 package service 호출
- pick/place/home/stop sequence 실행

Action Server:
- /robot/pick_and_place

Service:
- /robot/home
- /robot/stop

사용:
- dsr_msgs2
- Doosan motion service
- Doosan IO service
```

---

### `gripper_dio_controller`

```
역할:
- RG2 gripper open/close
- Doosan DIO service wrapper

사용:
- /dsr01/io/set_digital_output 계열
```

---

### `safety_manager_node`

```
역할:
- stop 명령 우선 처리
- 작업 영역 제한 확인
- 로봇 동작 가능 여부 판단
- task_manager 또는 robot_control에 stop 전달

Sub:
- /command/parsed
- /robot/status

Pub 또는 Service:
- /safety/status
- /robot/stop
```

---

## 4. 전체 데이터 흐름

```
1. 사용자 발화
   "안녕 로키, 건강하게 나눠줘"

2. voice_processing_node
   → /voice/text

3. command_parser_node
   → 키워드 추출
   → /command/parsed

4. policy_selector_node
   → 6칸 배분 정책 선택
   → /policy/selected

5. object_detection_node
   → 현재 판 위의 물체 검출
   → /detection/objects

6. perception_transform_node
   → camera 좌표를 robot base 좌표로 변환
   → /perception/objects_base

7. task_manager_node
   → policy와 perception 결과를 매칭
   → 다음 pick 대상 선택
   → destination slot 결정

8. robot_control_node
   → Doosan package service 호출
   → pick/place 실행

9. 반복
   → 모든 필요한 물체를 6칸에 배분
```

---

## 5. 패키지/파일 구조

```
~/cobot_ws/src/
├── doosan-robot2/ 또는 기존 Doosan 관련 패키지
│   ├── dsr_bringup2
│   ├── dsr_msgs2
│   ├── dsr_common2
│   └── ...
│
└── cobot2/
    ├── cobot_msgs/
    │   ├── msg/
    │   │   ├── RobotCommand.msg
    │   │   ├── Policy.msg
    │   │   ├── DetectedObject.msg
    │   │   ├── DetectedObjectArray.msg
    │   │   ├── ObjectPose.msg
    │   │   └── ObjectPoseArray.msg
    │   └── action/
    │       └── PickAndPlace.action
    │
    ├── cobot_voice/
    │   └── cobot_voice/
    │       ├── voice_processing_node.py
    │       ├── command_parser_node.py
    │       ├── keyword_extractor.py
    │       └── object_aliases.py
    │
    ├── cobot_policy/
    │   └── cobot_policy/
    │       ├── policy_selector_node.py
    │       ├── policy_rules.py
    │       └── policy_config.yaml
    │
    ├── cobot_task_manager/
    │   └── cobot_task_manager/
    │       ├── task_manager_node.py
    │       ├── task_state.py
    │       ├── target_selector.py
    │       └── retry_policy.py
    │
    ├── cobot_perception/
    │   └── cobot_perception/
    │       ├── perception_transform_node.py
    │       ├── handeye_transform.py
    │       ├── depth_filter.py
    │       └── grasp_pose_generator.py
    │
    ├── cobot_robot_control/
    │   └── cobot_robot_control/
    │       ├── robot_control_node.py
    │       ├── doosan_motion_client.py
    │       ├── doosan_io_client.py
    │       ├── gripper_dio_controller.py
    │       ├── motion_sequence.py
    │       └── pose_converter.py
    │
    ├── cobot_safety/
    │   └── cobot_safety/
    │       ├── safety_manager_node.py
    │       └── workspace_guard.py
    │
    ├── cobot_config/
    │   └── config/
    │       ├── object_aliases.yaml
    │       ├── policy_config.yaml
    │       ├── slot_poses.yaml
    │       ├── workspace.yaml
    │       └── handeye.yaml
    │
    └── cobot_bringup/
        ├── launch/
        │   ├── host_system.launch.py
        │   ├── perception.launch.py
        │   ├── robot.launch.py
        │   └── full_system.launch.py
        └── config/
            └── params.yaml
```

Docker workspace:

```
~/ros2_ws/src/cobot2/
├── object_detection/
│   └── object_detection/
│       ├── object_detection_node.py
│       ├── yolo_detector.py
│       ├── depth_utils.py
│       └── detection_postprocess.py
│
└── cobot_msgs/
```

---

## 6. 최종 요약

```
voice_processing_node
→ 말 듣기

command_parser_node
→ 키워드 추출

policy_selector_node
→ 6칸 배분 정책 결정

object_detection_node
→ 물체 인식

perception_transform_node
→ 로봇 좌표 변환

task_manager_node
→ 전체 작업 판단 및 순서 관리

robot_control_node
→ Doosan 패키지 호출

gripper_dio_controller
→ RG2 DIO 제어

safety_manager_node
→ stop / workspace / 안전 상태 관리
```