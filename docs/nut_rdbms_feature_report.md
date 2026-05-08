# 견과류 RDBMS 기반 건강 백과(Nut Encyclopedia) 기능 구현 보고서

본 문서는 `feature/nut-rdbms` 브랜치에서 진행된 로컬 RDBMS(SQLite) 기반의 '견과류 건강 백과' 기능 구현 내용을 정리한 것입니다.

---

## 1. 개요
기존의 NoSQL(Firebase) 추천 로직과는 독립적으로 작동하며, 사용자에게 견과류에 대한 상세 건강 정보(권장량, 주의사항, 음식 궁합 등)를 제공하는 기능을 추가하였습니다. 모든 데이터는 로컬 SQLite 데이터베이스를 통해 관리됩니다.

---

## 2. 데이터베이스 설계 (RDBMS)

### SQLite 데이터베이스 구조
- **파일명**: `database.db` (프로젝트 루트 위치)
- **테이블명**: `Nut_Details`

| 컬럼명 | 데이터 타입 | 설명 |
| :--- | :--- | :--- |
| `nut_name` | TEXT (PK) | 견과류 이름 (아몬드, 호두, 캐슈넛, 피스타치오) |
| `daily_serving` | TEXT | 하루 권장 섭취량 |
| `max_limit` | TEXT | 섭취 시 주의사항 및 한계량 |
| `good_pairing` | TEXT | 같이 먹으면 좋은 음식 (궁합) |
| `bad_pairing` | TEXT | 피해야 할 음식 |
| `recipe_tip` | TEXT | 추천 요리 활용법 |

### 초기 데이터 (Sample Data)
아몬드, 호두, 캐슈넛, 피스타치오 등 4종의 상세 데이터를 삽입 완료하였습니다.

---

## 3. 백엔드 구현 (Python)

### 3.1. 데이터베이스 초기화 (`init_db.py`)
- `sqlite3` 라이브러리를 사용하여 테이블을 생성하고 초기 샘플 데이터를 삽입하는 스크립트입니다.
- 실행 시 프로젝트 루트에 `database.db` 파일을 자동으로 생성합니다.

### 3.2. API 서버 (`db_server.py`)
- Python 내장 `http.server`를 활용한 경량 API 서버입니다.
- **Endpoint**: `GET /api/nut?name=[견과류이름]`
- **기능**: 요청된 이름을 기반으로 SQLite에서 정보를 조회하여 JSON 형식으로 반환합니다.
- **CORS 지원**: 프론트엔드(Vite)에서 접근 가능하도록 CORS 헤더가 적용되어 있습니다.

---

## 4. 프론트엔드 구현 (React/TSX)

### 4.1. `NutEncyclopedia` 컴포넌트
- **위치**: `web_stt_firebase/src/components/NutEncyclopedia.tsx`
- **주요 기능**:
    - 4종 견과류 선택 버튼 (2x2 그리드 배치)
    - 클릭 시 백엔드 API 호출 및 실시간 데이터 페칭
    - 상세 정보 표시 (권장량, 주의사항, 궁합 등)
    - Fade-in 애니메이션 효과 적용

### 4.2. 디자인 최적화
- **LOKI UI 통합**: 기존 대시보드와 동일한 `panelBackground`, `borderColor`를 사용하여 일체감을 주었습니다.
- **공간 효율성**: 페이지 하단으로 넘치는 현상을 방지하기 위해 텍스트 크기 및 간격을 조정한 컴팩트 레이아웃을 적용했습니다.
- **너비 일치**: 상단 세션 상태 박스와 동일하게 `width: 440px`, `box-sizing: border-box`를 적용하여 수직 정렬을 맞췄습니다.
- **다이내믹 테마**: 현재 로봇 세션의 테마 색상을 prop으로 전달받아, 강조색(Accent Color)이 실시간으로 동기화됩니다.

---

## 5. 실행 및 테스트 방법

### Step 1: DB 서버 실행
터미널에서 프로젝트 루트로 이동 후 다음 명령어를 실행합니다.
```bash
python3 db_server.py
```
*(기본 8000번 포트에서 대기합니다.)*

### Step 2: 웹 UI 실행
새 터미널에서 웹 패키지 폴더로 이동 후 실행합니다.
```bash
cd web_stt_firebase
npm run dev
```

---

## 6. 결론
이번 작업을 통해 로컬 환경에서 독립적으로 작동하는 RDBMS 기반 부가 기능을 성공적으로 통합하였습니다. 이는 별도의 외부 서버 없이도 `database.db` 파일만으로 이식 가능한 구조를 가집니다.
