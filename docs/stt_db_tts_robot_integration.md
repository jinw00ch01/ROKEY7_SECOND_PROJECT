# STT, DB, TTS, Robot Integration Summary

## 목적

이 문서는 현재 구현된 음성 기반 견과류 추천 흐름을 한 곳에 정리한다.

최종 목표는 사용자의 음성을 STT로 텍스트화하고, 추천 결과를 DB와 로컬 주문 파일에 저장한 뒤, 그 값을 바탕으로 로봇이 실제 견과류 픽앤플레이스 동작을 수행하는 것이다.

현재 기준으로 역할은 다음처럼 나뉜다.

- STT: 사용자의 음성을 텍스트로 변환한다.
- 추천 로직: 텍스트에서 사용자 상태와 강도를 추출하고 견과류 조합을 만든다.
- TTS: 질문, 재질문, 추천 결과를 음성으로 안내한다.
- DB: Firebase Firestore에 웹 표시용 실시간 상태를 저장한다.
- 로봇 실행 계약: `cobot_voice/output/latest_order.json`의 성공한 주문 값을 로봇 제어 입력으로 사용한다.

## 전체 흐름

```text
Wake word 감지
  -> TTS로 시작 안내
  -> TTS로 컨디션 질문
  -> STT로 상태 텍스트 수집
  -> 상태 카테고리 추출
  -> TTS로 강도 질문
  -> STT로 강도 텍스트 수집
  -> 견과류 추천 조합 생성
  -> latest_order.json 저장
  -> Firestore /robot_session/current 업데이트
  -> TTS로 추천 결과 안내
  -> robot_control에서 주문 값을 읽고 로봇 동작 수행
```

주요 실행 파일은 `cobot_voice/cobot_voice/voice_order_flow.py`이다. 디버그 모드에서는 실제 마이크와 TTS 없이 터미널 입력과 `[TTS]` 출력으로 흐름을 확인할 수 있다.

```bash
cd /home/aes/cobot2_ws/cobot_voice
python3 voice_order_flow.py --debug
```

## STT

STT 구현은 `cobot_voice/cobot_voice/stt.py`에 있다.

현재 동작은 다음과 같다.

- `sounddevice`로 5초 동안 마이크 입력을 녹음한다.
- 샘플레이트는 16 kHz, mono, int16이다.
- 임시 WAV 파일을 만든다.
- OpenAI Whisper API의 `whisper-1` 모델로 전사한다.
- 전사 결과인 `transcript.text`를 반환한다.

`voice_order_flow.py`에서는 STT를 두 번 사용한다.

- 첫 번째 STT: 사용자의 상태를 받는다. 예: "피곤하고 집중이 안 돼요"
- 두 번째 STT: 상태의 강도를 받는다. 예: "많이", "보통", "조금"

디버그 모드에서는 `STT.speech2text()` 대신 `input()`을 사용한다.

## 추천 로직

추천 로직은 `cobot_voice/cobot_voice/nut_recommendation.py`와 `cobot_voice/config/*.json`에 있다.

상태 카테고리 설정은 `cobot_voice/config/keyword_categories.json`에 있다.

| category | 의미 | 추천 nut |
| --- | --- | --- |
| `fatigue` | 피로/회복 | `cashew` |
| `blood_sugar` | 혈당 관리 | `almond` |
| `diet` | 다이어트/체중 | `pistachio` |
| `focus` | 집중/두뇌 | `walnut` |

강도 설정은 `cobot_voice/config/nut_combo_rules.json`에 있다.

| intensity | 개수 |
| --- | --- |
| `low` | 1 |
| `normal` | 2 |
| `high` | 3 |

복합 상태가 들어오면 여러 견과류가 조합될 수 있다. 단, `max_total_count`는 6개로 제한되어 있다. 조합이 6개를 넘으면 낮은 우선순위 카테고리부터 개수가 줄어든다.

예시:

```json
{
  "recognized_text": "피곤하고 집중이 안 돼요 많이",
  "categories": ["fatigue", "focus"],
  "intensity": "high",
  "combo": [
    {"nut": "cashew", "count": 3},
    {"nut": "walnut", "count": 3}
  ],
  "combo_text": "캐슈넛 세 개와 호두 세 개"
}
```

## TTS

TTS 흐름은 `cobot_voice/cobot_voice/voice_order_flow.py`의 `speak(text)` 함수가 담당한다.

현재 지원 방식은 다음과 같다.

- ElevenLabs API 사용
- Linux `spd-say` 사용
- TTS 비활성화 후 콘솔 출력만 사용

관련 환경 변수는 다음과 같다.

| 환경 변수 | 역할 |
| --- | --- |
| `COBOT_TTS_ENABLED` | `0`, `false`, `no`, `off`이면 실제 TTS 재생을 끈다. |
| `COBOT_TTS_PROVIDER` | `auto`, `elevenlabs`, `spd-say` 계열 값을 사용할 수 있다. |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS API 키 |
| `ELEVENLABS_VOICE_ID` | 사용할 ElevenLabs voice id |
| `ELEVENLABS_MODEL_ID` | 기본값은 `eleven_flash_v2_5` |
| `ELEVENLABS_LANGUAGE_CODE` | 기본값은 `ko` |

질문과 확인 문구는 `cobot_voice/config/question_flow.json`에 있다.

현재 주요 문구 키는 다음과 같다.

- `wake_response`: wake word 감지 후 시작 안내
- `ask_state`: 사용자 컨디션 질문
- `retry_state`: 상태 인식 실패 시 재질문
- `ask_intensity`: 강도 질문
- `confirm_template`: 추천 결과 안내

## DB

현재 DB 역할은 Firebase Firestore가 담당한다.

Firestore 경로:

```text
/robot_session/current
```

이 문서는 웹 UI가 실시간 구독하는 표시용 상태이다. Python voice bridge가 상태를 발행하고, `web_stt_firebase`가 이를 받아 Three.js 화면의 문구, 색상, 진행 상태, 추천 결과를 표시한다.

대표 필드:

```json
{
  "display_state": "result_ready",
  "question": "",
  "transcript": "너무 피곤하고 집중이 안 돼요 많이",
  "categories": ["fatigue", "focus"],
  "intensity": "high",
  "combo": [
    {"nut": "cashew", "count": 3},
    {"nut": "walnut", "count": 3}
  ],
  "combo_text": "캐슈넛 세 개와 호두 세 개",
  "confirm_message": "말씀하신 상태에 맞춰 캐슈넛 세 개와 호두 세 개를 준비해드릴게요.",
  "success": true,
  "theme": {
    "primary_category": "fatigue",
    "primary_nut": "cashew",
    "primary_color": "#F2C879",
    "secondary_color": "#FFF3D6",
    "accent_color": "#D99A36"
  },
  "error": "",
  "updated_at": "2026-05-06T03:00:00+00:00"
}
```

`display_state` 값은 다음과 같다.

- `idle`
- `wake_detected`
- `asking_state`
- `listening_state`
- `asking_intensity`
- `listening_intensity`
- `recommending`
- `result_ready`
- `dispatching`
- `completed`
- `error`

중요한 점은 Firestore가 현재 웹 표시용 상태라는 것이다. 로봇의 실제 실행 판단은 Firestore보다 `latest_order.json`을 우선 입력 계약으로 사용하는 것이 안전하다.

## 로봇 실행용 주문 파일

로봇 제어 쪽에서 읽어야 할 현재 주문 파일은 다음이다.

```text
cobot_voice/output/latest_order.json
```

이 파일은 `cobot_voice/cobot_voice/keyword_extractor.py`의 `save_recommendation_order()`를 통해 저장된다.

스키마:

```json
{
  "request_id": "20260506_113200",
  "recognized_text": "피곤하고 집중이 안 돼요 많이",
  "categories": ["fatigue", "focus"],
  "intensity": "high",
  "combo": [
    {"nut": "cashew", "count": 3},
    {"nut": "walnut", "count": 3}
  ],
  "combo_text": "캐슈넛 세 개와 호두 세 개",
  "success": true
}
```

필드 계약:

| 필드 | 의미 |
| --- | --- |
| `request_id` | 주문 생성 시각 기반 ID |
| `recognized_text` | 추천에 사용된 최종 STT 텍스트 |
| `categories` | 추출된 상태 카테고리 |
| `intensity` | `low`, `normal`, `high` 중 하나 |
| `combo` | 로봇이 집어야 할 견과류 목록 |
| `combo[].nut` | `almond`, `cashew`, `pistachio`, `walnut` 중 하나 |
| `combo[].count` | 해당 견과류 개수 |
| `combo_text` | TTS로 읽기 좋은 한국어 조합 문장 |
| `success` | 로봇 실행 가능 여부 |

`success=false`이면 로봇은 절대 동작을 시작하면 안 된다.

실패 예시:

```json
{
  "request_id": "20260506_113200",
  "recognized_text": "그냥 괜찮아요",
  "categories": [],
  "intensity": "normal",
  "combo": [],
  "combo_text": "",
  "success": false
}
```

## 로봇 동작 구현 방향

현재 `cobot_robot_control/cobot_robot_control/robot_control_node.py`, `motion_sequence.py`, `doosan_motion_client.py`는 비어 있다. 따라서 다음 단계는 `latest_order.json` 또는 ROS2 메시지로 들어온 주문을 로봇 작업 단위로 변환하는 것이다.

권장 1차 구현은 파일 기반 폴링이다.

```text
robot_control_node
  -> latest_order.json 읽기
  -> request_id 중복 실행 방지
  -> success 확인
  -> combo 배열 검증
  -> nut, count를 작업 큐로 변환
  -> 견과류 종류별 인식/픽 위치 결정
  -> count만큼 pick and place 반복
  -> 완료 시 Firestore display_state를 completed로 업데이트
```

로봇 실행 전 반드시 확인할 조건:

- `success`가 `true`인지 확인한다.
- `combo`가 비어 있지 않은지 확인한다.
- `nut` 값이 허용된 4개 클래스인지 확인한다.
- `count`가 양의 정수인지 확인한다.
- 같은 `request_id`를 중복 실행하지 않는다.
- 로봇 workspace와 slot pose가 유효한지 확인한다.
- 비전 인식 결과가 없으면 해당 nut 작업을 실패 처리하고 로봇을 멈추거나 다음 작업으로 넘어가는 정책을 정한다.

기본 실행 게이트 예시:

```python
VALID_NUTS = {"almond", "cashew", "pistachio", "walnut"}

if not order.get("success"):
    return

for item in order.get("combo", []):
    nut = item.get("nut")
    count = int(item.get("count", 0))

    if nut not in VALID_NUTS or count <= 0:
        continue

    for _ in range(count):
        # 1. nut 클래스에 맞는 객체 위치 탐색
        # 2. pick pose 계산
        # 3. gripper close
        # 4. place slot으로 이동
        # 5. gripper open
        pass
```

## DB 값을 바탕으로 로봇 동작을 구현할 때의 기준

Firestore에도 `combo`, `success`, `display_state`가 들어가지만, 현재 설계상 Firestore는 웹 표시용이다. 로봇이 직접 DB 값을 읽어 동작하게 만들 수도 있지만, 1차 구현에서는 다음 기준을 권장한다.

| 입력원 | 권장 역할 |
| --- | --- |
| `latest_order.json` | 로봇 실행의 기준 데이터 |
| Firestore `/robot_session/current` | 웹 표시와 로봇 진행 상태 표시 |
| ROS2 topic/action | 추후 안정적인 로봇 실행 인터페이스 |

추후 구조를 더 안정화하려면 파일 폴링 대신 ROS2 인터페이스로 바꾸는 것이 좋다.

```text
cobot_voice
  -> 주문 생성
  -> /robot/order 또는 PickAndPlace action goal 발행

cobot_robot_control
  -> 주문 수신
  -> 로봇 동작 수행
  -> 진행률, 완료, 실패 상태 발행

cobot_voice 또는 firebase bridge
  -> 로봇 상태를 Firestore에 반영
```

## 현재 남은 구현 작업

- `robot_control_node.py`에서 `latest_order.json` 읽기 또는 ROS2 주문 구독 구현
- `request_id` 기반 중복 실행 방지
- `combo[].nut`와 비전 인식 클래스 매핑
- 견과류별 pick pose 선택 로직
- `count`만큼 반복 수행하는 motion sequence 구현
- gripper open/close 구현
- place slot 할당 정책 구현
- 로봇 완료/실패 상태를 Firestore 또는 ROS2 상태 토픽으로 발행
- 실제 로봇 동작 전 dry-run 모드 추가

## 관련 파일

- `cobot_voice/cobot_voice/stt.py`
- `cobot_voice/cobot_voice/voice_order_flow.py`
- `cobot_voice/cobot_voice/firebase_bridge.py`
- `cobot_voice/cobot_voice/keyword_extractor.py`
- `cobot_voice/cobot_voice/nut_recommendation.py`
- `cobot_voice/config/keyword_categories.json`
- `cobot_voice/config/nut_combo_rules.json`
- `cobot_voice/config/question_flow.json`
- `cobot_voice/output/latest_order.json`
- `web_stt_firebase/src/hooks/useRobotSession.ts`
- `cobot_robot_control/cobot_robot_control/robot_control_node.py`
- `cobot_config/config/slot_poses.yaml`
- `cobot_config/config/workspace.yaml`
