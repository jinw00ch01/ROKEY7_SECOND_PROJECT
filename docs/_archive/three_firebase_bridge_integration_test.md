# Three.js + Firebase + Python Bridge 통합 테스트 체크리스트

## 범위

Python voice bridge는 Firestore `/robot_session/current`에 화면 표시용 상태를 발행한다. 웹사이트는 같은 문서를 실시간 구독해서 overlay 문구, 진행 단계, Three.js 색상을 갱신한다. `cobot_voice/output/latest_order.json`은 robot_control 전달용으로 유지한다.

## Firebase Path

- Collection: `robot_session`
- Document: `current`
- Full path: `/robot_session/current`

## display_state 목록

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

## 수동 통합 테스트 체크리스트

1. 웹사이트 실행
   - 명령: `cd web_stt_firebase && npm run dev`
   - 확인: `idle` 상태, "호출어를 말해주세요." 문구, 기본 색상 표시

2. Firebase에 `wake_detected` 쓰기
   - 확인: wake 화면 전환
   - 확인 문구: "네, 맞춤 견과류 콤보를 준비해드릴게요." 또는 기본 wake 문구

3. Firebase에 `asking_state` 쓰기
   - 확인: 질문 문구 표시
   - 확인 문구: "오늘 컨디션은 어떤가요?"

4. Firebase에 `listening_state` 쓰기
   - 확인: 듣는 중 화면
   - 확인: overlay에 "음성 입력 대기 중..." 표시
   - 확인: Three.js animation mode가 listening 계열로 변경

5. Firebase에 추천 결과 쓰기
   - 입력 payload:

```json
{
  "display_state": "result_ready",
  "categories": ["fatigue", "focus"],
  "intensity": "high",
  "combo": [
    {"nut": "cashew", "count": 3},
    {"nut": "walnut", "count": 3}
  ],
  "combo_text": "캐슈넛 세 개와 호두 세 개",
  "confirm_message": "말씀하신 상태에 맞춰 캐슈넛 세 개와 호두 세 개를 준비해드릴게요.",
  "theme": {
    "primary_category": "fatigue",
    "primary_nut": "cashew",
    "primary_color": "#F2C879",
    "secondary_color": "#FFF3D6",
    "accent_color": "#D99A36"
  }
}
```

   - 확인: `result_ready` 화면 전환
   - 확인: `combo_text` 또는 `confirm_message` 표시
   - 확인: `Combo: 캐슈넛 세 개와 호두 세 개` 표시
   - 확인: Three.js 배경, terrain material, 조명 색상이 골드 계열로 부드럽게 변경

6. Firebase에 `dispatching` 쓰기
   - 확인: "로봇이 견과류를 준비하고 있어요." 표시
   - 확인: 진행 indicator의 "로봇 준비" 활성화

7. Firebase에 `completed` 쓰기
   - 확인: "준비가 완료되었습니다." 표시
   - 확인: 진행 indicator의 "완료" 활성화

8. Firebase에 `error` 쓰기
   - 확인: 에러 화면 표시
   - 확인: error 메시지 표시

## 자동 테스트

Firebase 연결 없이 Python bridge payload와 theme 생성을 검증한다.

```bash
cd cobot_voice
python3 test_firebase_bridge.py
```

기존 추천/질문 유틸도 함께 검증한다.

```bash
cd cobot_voice
python3 test_nut_recommendation.py
python3 test_question_flow.py
```

웹 코드는 타입 검사와 번들 빌드로 회귀를 확인한다.

```bash
cd web_stt_firebase
npm run lint
npm run build
```

## 실제 Firebase 수동 발행 스크립트

서비스 계정이 설정된 환경에서 다음 명령으로 `idle`부터 `error`까지 테스트 상태를 순차 발행한다.

```bash
cd cobot_voice
python3 scripts/publish_robot_session_scenarios.py --delay 2
```

필요 환경:

- `COBOT_VOICE_ENV_PATH=/absolute/path/to/cobot_voice.env`
- env 파일 안의 `FIREBASE_SERVICE_ACCOUNT=/absolute/path/to/serviceAccount.json`
- Firestore 쓰기 권한

## 주요 코드 위치

- Firebase session 발행: `cobot_voice/cobot_voice/firebase_bridge.py`
- Python voice flow 상태 전환 호출: `cobot_voice/cobot_voice/voice_order_flow.py`
- 웹 Firebase 구독: `web_stt_firebase/src/hooks/useRobotSession.ts`
- display_state별 overlay 문구: `web_stt_firebase/src/App.tsx`
- Three.js 색상 적용 함수: `web_stt_firebase/src/App.tsx`의 `updateTheme`
- Terrain material 색상 변환: `web_stt_firebase/src/components/Terrain.tsx`의 `createColorThemeFromSessionTheme`

## robot_control 연동 확인점

- robot_control은 `cobot_voice/output/latest_order.json`만 읽는다.
- `latest_order.json`의 `success`가 `false`이면 robot_control을 실행하지 않는다.
- Firebase는 웹 표시용이므로 robot_control의 실행 판단 소스로 쓰지 않는다.
