# cobot2

음성 기반 견과류 픽 앤 플레이스 데모. Doosan M0609 6-DOF cobot에 OnRobot RG2 그리퍼, Intel RealSense 카메라, 그리고 Arduino로 제어되는 stepper 컨베이어를 결합한 ROS 2 시스템.

## 동작 개요

1. 사용자가 웹 UI(또는 CLI)에서 음성 세션을 시작한다.
2. Wake word 감지 후 시스템이 사용자에게 **컨디션**과 **강도**를 TTS로 묻는다.
3. STT(Whisper)가 사용자의 답변을 전사하고, 키워드/카테고리 분석기가 답변을 매핑한다.
4. 콤보 룰 엔진이 견과류 주문 리스트를 생성해 `cobot_voice/output/latest_order.json` 및 백엔드(Firestore 또는 Supabase)에 기록한다.
5. `task_manager_node`가 주문을 읽어, 견과류별로 perception → pick → place 사이클을 실행한다.
6. `robot_control_node`가 픽 시퀀스(approach → grasp → verify_grip → lift → transit → place → retreat → home)를 수행한다.
7. 컨베이어가 `place_ready` 신호의 엣지에서 한 단위 전진한다.
8. 주문 완료 시 상태가 백엔드에 미러링되어 웹 UI가 "completed"를 표시한다.

## 패키지 구성

| 패키지 | 역할 |
|---|---|
| `cobot_bringup` | 통합 launch 파일 (`full_system`, `bringup_supabase`, `perception`, `robot`, `host_system`) |
| `cobot_config` | 워크스페이스/캘리브레이션 공용 설정 |
| `cobot_db` | DB 어댑터 (Firestore / Supabase) |
| `cobot_msgs` | 커스텀 ROS 메시지/액션 정의 |
| `cobot_object_detection` | YOLO 기반 견과류 검출 |
| `cobot_perception` | 카메라 ↔ 로봇 좌표 변환 및 perception 트리거 |
| `cobot_robot_control` | Doosan 로봇 + RG2 그리퍼 제어 (액션 서버) |
| `cobot_task_manager` | 주문 단위 task 오케스트레이션, verification/correction 루프 |
| `cobot_voice` | 음성 파이프라인 (wake word, STT, TTS, 키워드 추출, 룰 엔진) |
| `conveyor_controller` | Arduino stepper 벨트 제어 노드 |
| `nuts_data_recording` | 견과류 캘리브레이션/데이터 수집용 레코더 |
| `web_stt_firebase[_v2]` / `web_stt_supabase_v2` | 웹 UI (React + Vite + Three.js) |

## 빠른 실행

> 워크스페이스 경로는 `~/cobot_ws` 기준 (`src/cobot2`에 본 repo가 위치). 상세 사전 점검과 환경 변수는 `docs/03_run_manual.md` 참조.

```bash
cd ~/cobot_ws
colcon build --symlink-install
source install/setup.bash

# Supabase 경로 (현재 기본). bringup_supabase는 full_system의 Supabase 프리셋 wrapper.
ros2 launch cobot_bringup bringup_supabase.launch.py

# Firestore 경로 (레거시 — Supabase 마이그레이션 이후 사용 안 함, 필요 시에만)
ros2 launch cobot_bringup full_system.launch.py \
    enable_firebase_status_bridge:=true enable_supabase_status_bridge:=false

# 웹 UI는 rosbridge_websocket을 거쳐 ROS와 통신한다.
# 별도 터미널에서:
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
cd src/cobot2/web_stt_supabase_v2 && npm run dev
```

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/01_system_architecture.md`](docs/01_system_architecture.md) | 시스템 구성, 데이터 계약, 하드웨어 아키텍처, 안전 설계 |
| [`docs/02_ros_node_architecture.md`](docs/02_ros_node_architecture.md) | 노드별 ROS 인터페이스 레퍼런스 |
| [`docs/03_run_manual.md`](docs/03_run_manual.md) | 단계별 운영자 실행 매뉴얼 (Firestore 경로) |
| [`docs/04_validation_checklist.md`](docs/04_validation_checklist.md) | 사전 점검/수용 테스트 체크리스트 |
| [`docs/05_clustered_nuts_handling.md`](docs/05_clustered_nuts_handling.md) | 클러스터된 견과류 처리 정책 |
| [`docs/06_perception_trigger_redesign.md`](docs/06_perception_trigger_redesign.md) | Perception 트리거 재설계 |
| [`docs/07_verification_and_correction_loop.md`](docs/07_verification_and_correction_loop.md) | Verification / correction 루프 |
| [`docs/08_cluster_handling_implementation.md`](docs/08_cluster_handling_implementation.md) | 클러스터 처리 구현 노트 |
| [`docs/09_supabase_migration.md`](docs/09_supabase_migration.md) | Supabase 백엔드 경로 (Firestore 대체) |
| [`docs/cleanup_deletion_proposal.md`](docs/cleanup_deletion_proposal.md) | 아카이브 및 삭제 계획 |

## 하드웨어

- Doosan Robotics M0609 (6-DOF)
- OnRobot RG2 그리퍼
- Intel RealSense D-시리즈 카메라
- Arduino 기반 stepper 컨베이어

## 아카이브 안내

`_archive_cleanup/<YYYYMMDD>/` 디렉토리와 `docs/_archive/`는 **활성 코드/문서가 아니다**. 이력 보존 목적으로만 남아 있으며, `colcon build`, `source`, `import`, 실행 대상 모두 제외 대상이다. 자세한 사유는 `docs/cleanup_deletion_proposal.md` 및 각 배치의 `cleanup_manifest.md` 참조.
