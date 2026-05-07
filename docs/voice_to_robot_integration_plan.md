# 음성 STT → 로봇 자동 픽업 통합 플랜

> **문서 버전: 1.2** (2026-05-07 Phase 1+2+/task/start 검증 완료)
>
> **진행 상태:**
> - ✅ Phase 1 검증 완료 (실제 로봇으로 cashew=3 + walnut=3 자동 픽업, 6/6 성공)
> - ✅ Phase 2 검증 완료 (FileOrderProvider + task_manager 자동 흐름)
> - ✅ `/task/start` 서비스 신규 추가 (autostart=false 모드 지원)
> - ✅ launch 인자 `order_source`, `file_order_path` 추가 (C3 정책)
> - ✅ `command_parser_node`, `firebase_state_bridge` (dead code) 제거
> - ✅ task_manager에도 `per_class_z_offset_*_mm` 파라미터 추가 (pick_all과 일관성)
> - ✅ perception_transform_node docstring 정정 (service 모드 구현 사실 반영)
> - ⏳ Phase 3 마무리: voice_order_flow → task_manager 자동 트리거 연결
> - ⏳ Phase 4: /task/status, /task/result Firestore 미러
>
> **v1.2 변경**: Phase 1+2 실제 로봇 검증 결과 반영, 정리(cleanup) 작업 8개 완료
> **v1.1 변경**: Codex 감사 결과 반영 (Phase 4 재정의, 알려진 버그 섹션, dispatch_callback 위치)

## 0. 한 줄 요약

사용자가 음성으로 컨디션을 말하면 → 추천 견과류 조합이 산출되고 → **로봇이 자동으로 그 조합을 집어서 반납함에 놓음**. 현재 양쪽 끝(음성 추천 / 로봇 픽업)은 작동하지만 **중간 연결고리만 빠져있다.**

---

## 1. 현재 상태 (As-Is)

### 1-1. 작동하는 양쪽 끝

**왼쪽 — 음성 → 추천 (`cobot_voice`)**

```
사용자 음성
  → wake word ("안녕 로키")          [wakeup_word.py]
  → STT (Whisper API, 5초)            [stt.py]
  → 카테고리 추출 (fatigue/blood_sugar/diet/focus) + 강도(low/normal/high)
                                      [nut_recommendation.py]
  → 견과류 조합 산출 (max 6개)         [nut_recommendation.py:118-156]
  → latest_order.json 저장             [keyword_extractor.py:111-214]
  → Firestore /robot_session/current 갱신 (실시간 웹 표시)
                                      [firebase_bridge.py]
```

**오른쪽 — 로봇 픽업 (`cobot_task_manager`, `cobot_robot_control`, `cobot_perception`)**

```
주문서 (counts dict)
  → /perception/detect_once 호출        [task_manager_node.py:175]
  → 후보 객체 선택 (워크스페이스 필터)   [target_selector.py]
  → /robot/pick_and_place 액션 실행     [task_manager_node.py:222-256]
                                        (DSR 직접 모션, MoveIt 미사용)
  → 견과류를 반납함에 배치
  → 다음 견과류로 이동
  → 진행 상태 발행 [task_manager_node.py:148-149]
      • /task/status (String)  ← ★ 이미 발행 중
      • /task/result (String)  ← ★ 이미 발행 중
```

또는 CLI로 직접:
```bash
~/cobot_ws/src/cobot2/scripts/pick_all.py --counts cashew=3,almond=2
```

### 1-2. 빠진 연결고리

**`cobot_task_manager`의 `order_provider`가 음성 결과를 읽지 못한다.**

- 현재 `order_source` 파라미터: `"mock"` | `"db"`
  - `mock`: yaml에 하드코딩된 `mock_order_*` 값 사용 (`order_provider.py` `MockOrderProvider`)
  - `db`: `/db/get_nut_order` 서비스 호출 — **이 서비스 서버 구현체가 없음** (provider/yaml만 존재, 호출하면 timeout)
- **`latest_order.json` 파일을 읽는 provider가 없음**
- `voice_order_flow.py`는 ROS 노드도 아니라서 자동으로 task_manager를 트리거하지도 않음
- **task_manager 시작 트리거 부재**: `/task/start` 같은 서비스 없음, 오직 `autostart=true`로만 시작됨

**한편 `voice_order_flow.run_recommendation_flow()`에는 `dispatch_callback` 훅이 이미 존재**하며, `voice_web_demo.py:113`에서 `wait_for_robot_motion`을 callback으로 넘기는 패턴이 있음. 이 훅을 task_manager 트리거로 연결하는 것이 가장 자연스러운 통합 지점.

### 1-3. 데이터 흐름 (현재)

```
[음성]                                    [로봇]
cobot_voice                               cobot_task_manager
  │                                          │
  ├── latest_order.json ⚠ 끊김 ⚠            ├── order_provider
  │   (생성은 되지만 아무도 안 읽음)            │   ├── mock (하드코딩)
  │                                          │   └── db (서비스 서버 없음)
  ├── Firestore                              │
  │   └── /robot_session/current             ├── /perception/detect_once
  │                                          ├── /robot/pick_and_place
  │                                          ├── /task/status  ★ 발행 중 (구독자 0)
  │                                          └── /task/result  ★ 발행 중 (구독자 0)
  │
  └── (사람이 수동으로 pick_all.py 실행)
```

---

## 2. 목표 (To-Be)

### 2-1. End-to-End 자동화 흐름

```
사용자 음성
  ↓
cobot_voice
  ├─→ latest_order.json (로봇용 계약 파일)
  └─→ Firestore (웹 UI 동기화)
        ↓
cobot_task_manager (FileOrderProvider 추가)
  ├─→ JSON 읽고 counts 변환
  └─→ pick_and_place 자동 실행
        ↓
로봇이 견과류 픽업 → 반납함
        ↓
완료 상태 Firestore 갱신 (display_state: "completed")
```

### 2-2. 검증 가능한 성공 기준

1. **터미널에서 `voice_order_flow` 한 번 실행** → 음성 한 번 → **로봇이 자동으로 픽업까지 완료**
2. 잘못된 음성 (예: "그냥 괜찮아요" → success=false) 시 로봇 동작 안 함
3. 같은 `request_id` 두 번 처리 안 함 (idempotent)
4. 웹 UI에서 진행 상태(asking → recommending → dispatching → completed) 실시간 반영
5. 로봇 동작 실패 시 Firestore에 error 상태 + 메시지 기록

---

## 3. 아키텍처 결정

### 3-1. 채택: 옵션 A — `FileOrderProvider` 추가

**장점:**
- 가장 적은 코드 변경 (~50줄)
- cobot_voice는 그대로 (이미 latest_order.json 저장 중)
- task_manager의 기존 order_provider 추상화를 활용
- 양쪽 독립적으로 테스트 가능 (음성 없이 JSON 파일만 만들어서 로봇 단독 테스트)

**단점:**
- 파일 폴링 또는 한 번 읽기 — 진정한 이벤트 기반 아님 (다음 단계에서 보완 가능)

### 3-2. 비채택 옵션들 (참고)

| 옵션 | 설명 | 비채택 이유 |
|---|---|---|
| `voice_order_flow.py`가 직접 `pick_all.py` subprocess 실행 | 가장 빠르게 만들 수 있음 | task_manager 무시 → 재시도 정책/감지 시퀀스 우회됨 |
| `/db/get_nut_order` 서비스 구현 | 기존 DBOrderProvider 활용 | 단일 호출 후 영구 데이터 없음 → 재시도/디버깅 어려움 |
| 새 ROS 액션 (`/cobot_voice/order` action) | 이벤트 기반, 깨끗 | 변경 범위 큼 (지금 단계에 과함) |
| Firestore 직접 polling (task_manager가 firestore 구독) | 실시간 | task_manager에 firebase-admin 의존성 추가 |

### 3-3. 향후 확장 경로

1. **이벤트 트리거** — `voice_order_flow`가 task_manager의 `/task/start` 서비스 호출하도록 추가
2. **상태 피드백** — task_manager가 진행 상태(`/task/status`)를 Firestore에 그대로 미러링
3. **이력 저장** — Firebase Data Connect (Postgres) 도입해 모든 주문 영구 기록

---

## 4. 구현 단계

### Phase 1: `pick_all.py` 단독 통합 (0.5h, 안전)

**목적**: task_manager까지 가지 않고도 JSON 파일 하나로 로봇 동작 가능한지 먼저 검증.

**변경 파일**: `scripts/pick_all.py`

**추가할 옵션**: `--order-file PATH`
- 동작: JSON 파일 읽기 → `combo` → `counts` dict 변환 → 기존 main 로직 진입
- 검증: `success=false`이면 거부, 빈 combo이면 거부
- 출력에 `request_id` 표시

**테스트 시나리오:**

```bash
# 가짜 주문 만들기
cat > /tmp/test_order.json <<EOF
{
  "request_id": "test_001",
  "combo": [{"nut": "cashew", "count": 1}],
  "success": true
}
EOF

# 로봇 실행
~/cobot_ws/src/cobot2/scripts/pick_all.py --order-file /tmp/test_order.json
```

→ 로봇이 cashew 1개 집고 정상 종료 → ✅

### Phase 2: cobot_task_manager에 `FileOrderProvider` 추가 (1h)

**변경 파일**:
- `cobot_task_manager/cobot_task_manager/order_provider.py`
- `cobot_task_manager/config/task_manager.yaml` (있으면 수정, 없으면 launch 인자로)
- `cobot_task_manager/cobot_task_manager/task_manager_node.py` (provider 선택 로직)

**추가 클래스**:

```python
class FileOrderProvider:
    """latest_order.json 파일에서 주문서를 읽는 provider."""
    
    def __init__(self, file_path: str, require_success: bool = True):
        self.file_path = file_path
        self.require_success = require_success
        self._last_request_id: Optional[str] = None
    
    def fetch(self) -> OrderBook:
        with open(self.file_path, 'r') as f:
            data = json.load(f)
        
        # 안전장치
        if self.require_success and not data.get("success", False):
            raise OrderProviderError(
                f"order success=false (text: {data.get('recognized_text', '')})"
            )
        
        # 같은 주문 중복 처리 방지
        request_id = data.get("request_id", "")
        if request_id == self._last_request_id:
            raise OrderProviderError(f"order {request_id} already processed")
        self._last_request_id = request_id
        
        # combo → counts 변환
        counts = {"almond": 0, "cashew": 0, "pistachio": 0, "walnut": 0}
        for item in data.get("combo", []):
            nut = item.get("nut")
            count = int(item.get("count", 0))
            if nut in counts and count > 0:
                counts[nut] += count
        
        if not any(v > 0 for v in counts.values()):
            raise OrderProviderError("combo is empty")
        
        return OrderBook(counts=counts, request_id=request_id)
```

**파라미터 추가** (task_manager_node.py):
```python
self.declare_parameter("order_source", "mock")          # mock | db | file
self.declare_parameter("file_order_path", "/home/.../cobot_voice/output/latest_order.json")
self.declare_parameter("file_order_require_success", True)
```

**provider 선택 분기 (task_manager_node.py:87-102):**
```python
if order_source == "file":
    self._order_provider = FileOrderProvider(
        file_path=self.get_parameter("file_order_path").value,
        require_success=self.get_parameter("file_order_require_success").value,
    )
```

**테스트 시나리오:**

```bash
# 가짜 주문 만들기
cat > ~/cobot_ws/src/cobot2/cobot_voice/output/latest_order.json <<EOF
{
  "request_id": "test_002",
  "combo": [{"nut": "cashew", "count": 1}, {"nut": "almond", "count": 1}],
  "success": true
}
EOF

# task_manager를 file 모드로 실행
ros2 launch cobot_bringup full_system.launch.py \
    task_autostart:=true \
    order_source:=file
```

→ task_manager가 JSON 읽고 cashew + almond 자동 픽업 → ✅

### Phase 3: 음성 → task_manager 자동 트리거 (1.5h)

**변경 파일**:
- `cobot_voice/cobot_voice/voice_order_flow.py` — `dispatch_callback` 훅에 task_manager 트리거 함수 연결
- `cobot_task_manager/cobot_task_manager/task_manager_node.py` — `/task/start` 서비스 **신규 추가** (현재 미존재, autostart만 있음)

**task_manager에 시작 서비스 추가** (현재 없음, 새로 추가해야 함):

```python
# task_manager_node.py - 새 코드
from std_srvs.srv import Trigger

# __init__()에 추가:
self._start_service = self.create_service(
    Trigger, "/task/start", self._handle_start
)

def _handle_start(self, _req, resp):
    if self._worker_thread is not None and self._worker_thread.is_alive():
        resp.success = False
        resp.message = "task already running"
    else:
        self._stop_event.clear()
        self.start_worker()  # 이미 정의된 메서드
        resp.success = True
        resp.message = "task started"
    return resp
```

**대안 — 서비스 추가 안 하고 autostart 활용:**

매 음성 주문마다 task_manager를 재시작하는 방식. 더 단순하지만 무겁다.

**voice_order_flow.py에서 호출** (이미 존재하는 `dispatch_callback` 훅 활용):

```python
# 새 모듈: cobot_voice/cobot_voice/task_manager_dispatcher.py
def dispatch_to_task_manager(order: dict) -> bool:
    """latest_order.json 저장 후 task_manager 트리거."""
    import subprocess
    result = subprocess.run(
        ["ros2", "service", "call", "/task/start",
         "std_srvs/srv/Trigger", "{}"],
        capture_output=True, timeout=5,
    )
    return result.returncode == 0

# voice_web_demo.py 또는 entry script에서:
order = run_recommendation_flow(
    debug=False,
    wait_for_wake=True,
    dispatch_callback=dispatch_to_task_manager,  # 이미 있는 훅
)
```

**핵심**: `dispatch_callback`은 이미 `voice_order_flow.py:310`에 파라미터로 정의되어 있고, `voice_web_demo.py:113`이 그 사용 예시다. 새로운 dispatcher 함수를 만들어 callback으로 넘기면 됨.

### Phase 4 (선택): 상태 피드백 — Firestore 미러링 (30분)

> **수정사항(v1.1)**: `/task/status`, `/task/result` 토픽은 **이미 task_manager가 발행 중**(`task_manager_node.py:148-149`). 새로 만들 필요 없음. 단지 **구독자가 없을 뿐**. Firestore로 미러링하는 노드 하나만 추가하면 됨.

**새 파일**: `cobot_voice/cobot_voice/task_status_bridge.py`

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from cobot_voice.firebase_bridge import update_display_state

class TaskStatusBridge(Node):
    """task_manager의 /task/status, /task/result를 Firestore에 미러링."""
    
    STATE_MAP = {
        "init": "dispatching",
        "detect": "dispatching",
        "select_target": "dispatching",
        "pick_and_place": "dispatching",
        "done": "completed",
        "aborted": "error",
        "safety_stop": "error",
    }
    
    def __init__(self):
        super().__init__("task_status_bridge")
        self.create_subscription(String, "/task/status", self._on_status, 10)
        self.create_subscription(String, "/task/result", self._on_result, 10)
    
    def _on_status(self, msg: String):
        state = self.STATE_MAP.get(msg.data, "dispatching")
        update_display_state(state, task_status=msg.data)
    
    def _on_result(self, msg: String):
        if "success" in msg.data.lower():
            update_display_state("completed", task_result=msg.data)
        else:
            update_display_state("error", error=msg.data)
```

→ launch에 이 노드 추가만 하면 끝. 약 30줄.

---

## 5. 변경 위치 요약 표

| Phase | 파일 | 변경 내용 | 라인 수 |
|---|---|---|---|
| 1 | `scripts/pick_all.py` | `--order-file` 옵션 추가, JSON 파싱 | ~50줄 |
| 2 | `cobot_task_manager/cobot_task_manager/order_provider.py` | `FileOrderProvider` 클래스 | ~40줄 |
| 2 | `cobot_task_manager/cobot_task_manager/task_manager_node.py` | provider 분기 + 파라미터 | ~10줄 |
| 3 | `cobot_task_manager/cobot_task_manager/task_manager_node.py` | `/task/start` 서비스 신규 추가 (없음) | ~20줄 |
| 3 | 새 파일: `cobot_voice/cobot_voice/task_manager_dispatcher.py` | dispatch_callback 함수 | ~15줄 |
| 3 | `cobot_voice/cobot_voice/voice_web_demo.py` 또는 entry | callback 연결 | ~5줄 |
| 4 (선택, 짧음) | 새 파일: `cobot_voice/cobot_voice/task_status_bridge.py` | 이미 발행 중인 토픽을 Firestore에 미러링 | ~30줄 |

**총 변경량 ~170줄, 새 의존성 0개.**

**v1.1 수정**: Phase 4의 작업량이 1h → 30분으로 단축 (이미 발행 중인 토픽 활용).

---

## 6. 안전 장치 / 오류 처리

### 6-1. JSON 검증
- `success=false`인 주문은 거부 (`FileOrderProvider`에서 발생)
- `combo`가 비어있으면 거부
- `request_id` 중복 시 거부 (이미 처리한 주문 재실행 방지)

### 6-2. 워크스페이스 안전
- 이미 `target_selector.py`가 워크스페이스 박스 + z 범위 필터링 (변경 없음)
- 영역 밖 객체는 자동으로 제외

### 6-3. 재시도 정책
- 기존 `retry_policy.py` 그대로 사용
- detect_miss 2회 → 해당 클래스 스킵
- grasp_failure 2회 → 해당 클래스 스킵
- motion_fail (code 3, 5, 1) → 즉시 중단

### 6-4. 음성 인식 실패 처리
- 사용자가 발화 안 함 / 카테고리 추출 실패 → success=false → 로봇 안 움직임
- voice_order_flow에서 retry_state로 재질문 후, 그래도 실패 시 idle 복귀

### 6-5. 로봇 동작 실패 처리
- task_manager의 `/task/result` 발행값 확인
- 실패 시 Firestore display_state="error" + error 메시지 기록
- 사용자에게 음성 안내 (선택, Phase 4)

---

## 7. 테스트 매트릭스

| # | 시나리오 | Phase | 기대 결과 |
|---|---|---|---|
| T1 | `--order-file`에 cashew=1 JSON | 1 | 로봇이 cashew 1개 집음 |
| T2 | `--order-file`에 success=false | 1 | 거부, 로봇 안 움직임 |
| T3 | `--order-file`에 빈 combo | 1 | 거부 |
| T4 | task_manager order_source=file | 2 | task_manager가 자동으로 JSON 읽음 |
| T5 | 같은 request_id 두 번 | 2 | 두 번째 거부 |
| T6 | 음성 전체 플로우 (정상) | 3 | 음성 → 추천 → 자동 픽업 → 웹 UI 갱신 |
| T7 | 음성 "그냥 괜찮아요" (실패 케이스) | 3 | 추천 실패, 로봇 안 움직임, 웹 UI에 안내 |
| T8 | 로봇 동작 중 견과류 미스 | 3 | retry_policy에 따라 자동 스킵, 웹 UI에 진행 상태 |
| T9 | 워크스페이스 밖 객체 탐지 | 2 | target_selector가 거부, 정상 진행 |
| T10 | 단일 호출 idempotency | 2 | request_id 추적으로 중복 안 됨 |

---

## 8. 단계별 진행 추천

**최소 기능부터:**

1. **Phase 1만 먼저 — 30분**
   - pick_all.py에 --order-file 추가
   - T1, T2, T3 통과 확인
   - 이 단계만으로도 "JSON → 로봇" 자동화 완성 (사람이 cobot_voice 따로 실행)

2. **Phase 2 추가 — 1시간**
   - FileOrderProvider 추가
   - T4, T5 통과
   - task_manager까지 통합 (재시도 정책 적용)

3. **Phase 3 추가 — 1시간 30분**
   - 음성 자동 트리거
   - T6, T7, T8 통과
   - 진정한 end-to-end

4. **Phase 4 (선택)** — 상태 피드백 강화

**예상 총 작업 시간: 3~4시간** (테스트 포함)

---

## 9. 롤백 계획

각 Phase는 독립적이라 단계별 롤백 가능:

- **Phase 1만 적용 시**: pick_all.py에 옵션 하나 추가일 뿐, 기존 사용 방식 영향 없음
- **Phase 2 적용 시**: `order_source` 파라미터를 다시 "mock"으로 돌리면 원상 복구
- **Phase 3 적용 시**: voice_order_flow에서 `dispatch_to_task_manager=False`로 비활성

각 Phase 변경은 git에서 커밋 단위로 분리 권장.

---

## 9-A. 알려진 버그 / 사전 정리 필요 (v1.1 추가)

플랜 진행 전에 인지하고 있어야 할 기존 코드 이슈들:

### 9-A-1. ⚠ `command_parser_node.py` 깨진 import

```python
# cobot_voice/cobot_voice/command_parser_node.py:5
from cobot_msgs.msg import RobotCommand   # ← cobot_msgs/msg/RobotCommand.msg 파일 없음!
```

→ **이 노드는 시작 시 ImportError로 죽음**. 다행히 음성 → 추천 메인 흐름은 `voice_order_flow.py`(별도 모듈)를 쓰므로 영향 적음. 하지만:
- launch에 포함되면 launch 자체가 실패할 수 있음
- 현재 cobot_voice의 setup.py에 entry_point로 등록돼 있는지 확인 필요

**처리 옵션:**
- (A) `cobot_msgs/msg/RobotCommand.msg` 파일 신규 작성 (사용 안 할거면 지나친 작업)
- (B) `command_parser_node.py`를 정리/제거 (메인 흐름에서 안 쓰면)
- (C) launch에서 제외

→ **권장: (B) 또는 (C)**. 메인 음성 흐름은 voice_order_flow.py 기반이라 이 노드 불필요해 보임.

### 9-A-2. `/db/get_nut_order` 서비스 서버 부재

- `cobot_task_manager/order_provider.py:88`이 이 서비스를 호출
- yaml(`task_manager.yaml:9`)에도 등록
- **하지만 서버 구현체가 저장소 어디에도 없음** → `db` 모드 사용 시 timeout

→ 이번 플랜은 `file` 모드로 갈 거라 영향 없지만, 추후 `db` 모드 쓰려면 서버 구현 또는 폐기 결정 필요.

### 9-A-3. `perception_transform_node.py` docstring 부정확

```python
# 현재 docstring:
"""TCP pose source is selectable:
  - "fixed"  : ...
  - other modes (topic / service) intentionally not implemented yet; ..."""
```

실제 코드와 yaml(`perception.yaml:15` `tcp_source: "service"`)에는 service 모드가 구현되어 작동 중. **docstring만 stale**. 코드 동작에 영향 없으나 다음 사람 헷갈림.

→ docstring만 수정하면 됨 (5줄).

### 9-A-4. `question_flow.json` TTS 메시지 정리 필요

사용자 노출 전에 재시도/에러 문구가 자연스러운지 검토 필요. 기능 영향은 없으나 UX 품질 영향.

### 9-A-5. z 처리 일관성 부족

- `pick_all.py`: `--z-override`, `PER_CLASS_Z_OFFSET` 추가됨
- `cobot_task_manager`: 둘 다 없음 (perception z 그대로 사용)
- **task_manager 경로로 가면 견과류 미끄럼 튜닝값이 적용 안 됨**

→ Phase 2 진행 시 동일한 z 보정 로직을 task_manager에도 이식하거나, 공유 모듈로 추출할지 결정 필요.

---

## 10. 미해결 / 결정 필요 사항

### 10-1. latest_order.json 경로 통일

현재 default: `cobot_voice/output/latest_order.json` (`keyword_extractor.py:14`)
- task_manager가 이 경로를 알아야 함
- 절대 경로 vs 환경변수 vs ROS 파라미터 — **절대 경로 권장 (가장 단순)**

### 10-2. 동시성

같은 시점에 두 개 음성 입력이 들어오면?
- 현재 voice_order_flow는 단일 스레드 (문제 없음)
- task_manager는 worker thread 하나 (busy 시 새 요청 거부)
- → **충돌 가능성 낮음**, 추가 락 불필요

### 10-3. ElevenLabs API 키 / OpenAI API 키 환경변수

```
OPENAI_API_KEY=...     (Whisper STT 필수)
ELEVENLABS_API_KEY=... (TTS, optional, spd-say fallback 있음)
FIREBASE_SERVICE_ACCOUNT=/path/to/json (Firebase 쓸거면 필수)
```

배포 시 이 환경변수들은 launch 환경 또는 `COBOT_VOICE_ENV_PATH=/absolute/path/to/cobot_voice.env`로 지정한 외부 env 파일에 설정한다.

### 10-4. 견과류 위치 z-override

현재 `pick_all.py`가 default `--z-override 없음` (perception z 사용).
- task_manager는 z를 어떻게 결정하나? → `target_selector.py`가 perception z를 그대로 사용
- `--z-override 65` 같은 보정이 필요하면 task_manager에도 같은 파라미터 필요할 수 있음
- **결정 필요**: task_manager의 z 처리 방식이 pick_all.py와 다른지 확인

### 10-5. PER_CLASS_Z_OFFSET

`pick_all.py`에 추가한 `PER_CLASS_Z_OFFSET`도 task_manager에 동일하게 반영해야 일관성 유지.
- → 공유 모듈(`cobot_task_manager`의 grasp 보정 로직)에 두는 게 좋음

---

## 11. 다음 액션

**바로 시작 가능한 작업:**

1. **Phase 1 시작**: `pick_all.py`에 `--order-file` 추가
2. **샘플 JSON 준비**: `/tmp/test_order.json`로 T1 테스트
3. **검증 후 Phase 2로**

**또는 병렬로 진행 가능:**

- **Firebase Data Connect (Postgres) 스키마 작성** — 주문 이력 영구 저장 인프라 (별도 트랙)
- **task_manager 동작 검증** — 현재 `mock` 모드로 잘 도는지 사전 점검

---

## 부록 A: 관련 파일 인덱스

```
cobot_voice/
├── cobot_voice/
│   ├── voice_order_flow.py          ← 음성 추천 플로우 (entry point)
│   ├── nut_recommendation.py        ← 추천 알고리즘
│   ├── keyword_extractor.py         ← latest_order.json 저장
│   ├── firebase_bridge.py           ← Firestore 갱신
│   └── stt.py / wakeup_word.py      ← STT / wake word
├── config/
│   ├── keyword_categories.json      ← 카테고리 → 견과류 매핑
│   ├── nut_combo_rules.json         ← intensity → count 룰
│   └── question_flow.json           ← TTS 메시지
└── output/
    └── latest_order.json            ← 로봇용 계약 파일 (생성됨)

cobot_task_manager/
├── cobot_task_manager/
│   ├── task_manager_node.py         ← 오케스트레이터 메인 노드
│   ├── order_provider.py            ← Mock/DB OrderProvider (FileOrderProvider 추가 위치)
│   ├── target_selector.py           ← 후보 객체 필터/정렬
│   └── retry_policy.py              ← 실패 시 정책
└── ...

cobot_robot_control/
└── cobot_robot_control/
    └── robot_control_node.py        ← /robot/pick_and_place 액션 서버

cobot_perception/
├── cobot_perception/
│   └── perception_transform_node.py ← 카메라 → 베이스 좌표 변환
└── config/perception.yaml

scripts/
├── pick_all.py                      ← CLI 직접 픽업 (기존, --order-file 추가 위치)
└── pick_one.py
```

## 부록 B: 메시지 인터페이스 요약

```
PickAndPlace.action  ✓ 정의됨, 서버 구현됨
  Goal: target_class, grasp_xyz, grasp_yaw, pre_grasp_width_mm,
        return_xyz, return_zyz_deg
  Result: success, failure_code (0=ok, 1=approach, 2=grasp, 3=motion,
                                  4=safety, 5=workspace), message
  Feedback: stage (approach/grasp/...)

DetectOnce.srv  ✓ 정의됨, 서버 구현됨
  Response: objects (DetectedObjectArray), success, message

GetNutOrder.srv  ✓ 정의됨 / ⚠ 서버 미구현
  Response: almond, cashew, pistachio, walnut (각 int32), success, message
  → cobot_task_manager의 DBOrderProvider만 클라이언트로 호출, 서버 없음

DetectedObject.msg  ✓ 정의됨
  class_name, confidence, cx/cy/width/height/theta (OBB),
  camera_xyz, base_xyz, grasp_yaw, short_axis_mm, long_axis_mm,
  transform_valid

RobotCommand.msg  ⚠ 정의 파일 부재
  → command_parser_node.py가 import 시도 → ImportError 발생
  → 9-A-1 참조

GetCurrentPose.srv  ✓ 정의됨, 서버 구현됨
  Response: xyz_mm, zyz_deg, success, message
```

## 부록 C: 토픽/서비스 가용성 매트릭스 (v1.1 신규)

| 인터페이스 | 정의 | 발행/서버 | 구독/클라이언트 | 비고 |
|---|---|---|---|---|
| `/perception/detect_once` | ✓ | ✓ perception_transform_node | task_manager, pick_all.py | 정상 |
| `/robot/pick_and_place` | ✓ | ✓ robot_control_node | task_manager, pick_all.py | 정상 |
| `/robot/get_current_pose` | ✓ | ✓ robot_control_node | perception_transform_node | 정상 |
| `/task/status` | ✓ String | ✓ task_manager_node:148 | **❌ 0** | Phase 4에서 미러 |
| `/task/result` | ✓ String | ✓ task_manager_node:149 | **❌ 0** | Phase 4에서 미러 |
| `/task/start` | ❌ | **미구현** | 없음 | Phase 3에서 추가 |
| `/db/get_nut_order` | ✓ srv | **❌ 서버 없음** | task_manager (timeout) | 9-A-2 |
| `/voice/text` | ✓ String | ✓ voice_processing_node | command_parser_node (깨짐) | 9-A-1 |
| `/command/parsed` | RobotCommand | 노드 시작 실패 | 없음 | 9-A-1 |
| `/robot_session/current` (Firestore) | — | firebase_bridge | useRobotSession.ts | 정상 |

---

**문서 버전**: 1.1
**최초 작성**: 2026-05-07
**v1.1 갱신**: 2026-05-07 (Codex 감사 반영)
**v1.1 변경 요약**:
- Phase 4 재정의: `/task/status`, `/task/result`는 이미 발행 중 → 미러 노드만 필요 (소요 시간 1h → 30분)
- 9-A 알려진 버그 섹션 신설 (5건)
- 부록 C 인터페이스 가용성 매트릭스 신설
- dispatch_callback이 voice_web_demo.py:113에 이미 사용 중인 사실 명시
- Phase 3에서 `/task/start` 서비스가 **신규 추가 대상**임을 명확히 표기
- DSR 직접 모션 명시 (MoveIt 미사용)

**관련 docs**:
- `docs/stt_db_tts_robot_integration.md` (이 플랜의 상위 컨텍스트)
- `docs/nut_recommendation_flow.md` (추천 알고리즘 상세)
- `docs/three_firebase_bridge_changes.md` (Firestore 통합 상세)
