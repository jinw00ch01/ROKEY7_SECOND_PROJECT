# Three.js + Firebase + Python Bridge 변경 사항 정리

## 목적

Python voice bridge에서 wake word, STT, keyword extraction, nut recommendation 진행 상태를 Firebase에 발행하고, Three.js 웹사이트가 `/robot_session/current`를 실시간 구독해 화면 상태와 색상을 변경하도록 통합했다.

역할은 다음처럼 분리했다.

- Firebase: 웹 화면 표시용 실시간 상태
- `cobot_voice/output/latest_order.json`: robot_control 전달용 추천 결과
- Three.js 웹사이트: Firebase session 구독 후 display_state, 문구, combo, theme 반영

## Firebase Session 스키마

Path:

```text
/robot_session/current
```

주요 필드:

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

`display_state` 값:

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

## Python Bridge 변경

### 추가 파일

- `cobot_voice/cobot_voice/firebase_bridge.py`
- `cobot_voice/test_firebase_bridge.py`
- `cobot_voice/scripts/publish_robot_session_scenarios.py`

### 주요 함수

`firebase_bridge.py`:

- `update_display_state(state, **kwargs)`
- `reset_session()`
- `publish_question(question_text, state)`
- `publish_transcript(text)`
- `publish_recommendation_result(order)`
- `publish_dispatching(order=None)`
- `publish_completed(order=None)`
- `publish_error(message)`
- `build_theme(categories, combo)`

### 상태 전환 삽입 위치

`cobot_voice/cobot_voice/voice_order_flow.py`의 `run_recommendation_flow()`에 Firebase 상태 발행을 삽입했다.

흐름:

1. 시작 시 `reset_session()`으로 `idle`
2. wake word 감지 후 `wake_detected`
3. 상태 질문 전 `asking_state`
4. 상태 응답 녹음 중 `listening_state`
5. 상태 STT 완료 후 `publish_transcript`
6. 카테고리 추출 실패 시 `retry_state` 질문 또는 최종 `error`
7. 강도 질문 전 `asking_intensity`
8. 강도 응답 녹음 중 `listening_intensity`
9. 추천 계산 중 `recommending`
10. 추천 성공 시 `publish_recommendation_result()`로 `result_ready`
11. robot_control 콜백 시작 시 `dispatching`
12. robot_control 콜백 완료 시 `completed`
13. 예외 발생 시 `publish_error()`로 `error`

Firebase 업데이트 실패는 전체 voice flow를 중단하지 않고 warning 로그만 남긴다.

## 웹사이트 변경

### 추가 파일

- `web_stt_firebase/src/hooks/useRobotSession.ts`

### 수정 파일

- `web_stt_firebase/src/lib/types.ts`
- `web_stt_firebase/src/App.tsx`
- `web_stt_firebase/src/components/Terrain.tsx`

### Firebase 구독

`useRobotSession.ts`에서 Firestore 문서 `/robot_session/current`를 구독한다.

주요 함수:

- `subscribeRobotSession()`
- `handleRobotSessionUpdate(session)`
- `useRobotSession()`

Firebase 데이터가 없거나 잘못된 값이 오면 `idle` 기본값으로 정규화한다.

### 화면 상태 표시

`App.tsx`에 display_state별 overlay 문구와 진행 indicator를 추가했다.

주요 함수:

- `getDisplayText(session)`
- `updateDisplayPanel(session)`
- `updateProgressIndicator(displayState)`
- `setDisplayState(state, session)`
- `updateComboDisplay(combo, comboText)`
- `showTranscript(transcript)`
- `showError(error)`

기본 문구보다 Firebase의 `question`, `transcript`, `combo_text`, `confirm_message`, `error`를 우선 사용한다.

### Three.js 색상 변경

`App.tsx`:

- `updateTheme(theme)`
- `resolveSessionTheme(session)`
- `ThemedScene`

`Terrain.tsx`:

- `createColorThemeFromSessionTheme(theme)`

적용 대상:

- scene 배경 색상
- overlay panel 색상
- ambient/directional light 색상과 intensity
- Terrain surface/ribbon/emissive material 색상

색상은 `useFrame`에서 lerp 기반으로 부드럽게 전환된다.

## Theme 매핑

| category | nut | primary | secondary | accent |
| --- | --- | --- | --- | --- |
| `fatigue` | `cashew` | `#F2C879` | `#FFF3D6` | `#D99A36` |
| `blood_sugar` | `almond` | `#B9855A` | `#F3E1D0` | `#7A4E2D` |
| `diet` | `pistachio` | `#8BC34A` | `#E8F5D2` | `#4F8A10` |
| `focus` | `walnut` | `#6D4C41` | `#D7CCC8` | `#3E2723` |

복합 combo에서는 첫 번째 category 또는 첫 번째 nut을 primary로 사용하고, 두 번째 nut이 있으면 accent 색상에 반영한다.

## 테스트 추가

### 자동 테스트

`cobot_voice/test_firebase_bridge.py`:

- `reset_session()` payload 검증
- `publish_question()` payload 검증
- `publish_recommendation_result()` payload 검증
- `publish_error()`와 unknown state fallback 검증
- `build_theme()` fallback 검증

실행:

```bash
cd cobot_voice
python3 test_firebase_bridge.py
```

### 수동 Firebase 시나리오 발행

`cobot_voice/scripts/publish_robot_session_scenarios.py`:

`idle`부터 `error`까지 웹 통합 테스트용 상태를 순차 발행한다.

실행:

```bash
cd cobot_voice
python3 scripts/publish_robot_session_scenarios.py --delay 2
```

필요 조건:

- `COBOT_VOICE_ENV_PATH=/absolute/path/to/cobot_voice.env`
- env 파일 안의 `FIREBASE_SERVICE_ACCOUNT=/absolute/path/to/serviceAccount.json`
- Firestore 쓰기 권한

## 검증 완료

실행한 검증:

```bash
cd cobot_voice
python3 test_firebase_bridge.py
python3 test_nut_recommendation.py
python3 test_question_flow.py
```

```bash
cd web_stt_firebase
npm run lint
npm run build
```

결과:

- Python Firebase bridge 테스트 통과
- 기존 견과류 추천 테스트 통과
- question_flow 테스트 통과
- 웹 lint 통과
- 웹 production build 성공
- Vite chunk size warning은 남아 있으나 빌드 실패는 아님

## 테스트 순서

1. 웹사이트 실행

```bash
cd web_stt_firebase
npm run dev
```

2. 브라우저에서 Vite 주소 접속

3. 다른 터미널에서 Firebase 상태 발행

```bash
cd cobot_voice
python3 scripts/publish_robot_session_scenarios.py --delay 2
```

4. 확인 항목

- `idle`: 호출어 대기 문구
- `wake_detected`: wake 응답 화면
- `asking_state`: 질문 문구
- `listening_state`: 듣는 중 표시
- `result_ready`: combo_text, combo, confirm_message 표시
- `result_ready`: 골드 계열 Three.js 색상 전환
- `dispatching`: 로봇 준비 중 화면
- `completed`: 완료 화면
- `error`: 에러 화면

## 남은 연결 작업

- 실제 Firebase service account 파일 위치 확인
- Python bridge 실행 환경에서 `FIREBASE_SERVICE_ACCOUNT` 설정 확인
- robot_control 실행 지점에 `dispatch_callback(order)` 연결
- robot_control 완료 시 `publish_completed(order)`가 호출되는지 실제 하드웨어 흐름에서 검증
