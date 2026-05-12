# Supabase 백엔드

이 문서는 `cobot2`의 Supabase 백엔드 통합을 다룬다. 주문/상태 실시간
동기화, 재고 원장, 예외 로그를 Postgres 하나에서 처리한다.

레거시 Firebase/Firestore 경로도 launch 인자 토글로 공존하지만, 본문에는
Supabase 내용만 담고 Firebase 관련 내용은 **부록**에 모았다.

## 문서 세트와의 관계

- `docs/01_system_architecture.md` — 전체 시스템 설계 (Firestore 기준 서술).
- `docs/02_ros_node_architecture.md` — ROS 인터페이스 (Firestore 기준).
- `docs/03_run_manual.md` — 운영자 실행 절차 (Firestore 경로).
- `docs/09_supabase_migration.md` — **이 파일**. Supabase 경로의 모든 내용.

01~03을 Supabase 경로로 읽으려면 firestore/firebase 언급을 이 문서의
Supabase 등가물(테이블/RPC/realtime 채널)로 치환하면 된다.

## 목차

1. 도입 동기와 범위
2. 추가/변경된 패키지
3. Supabase 스키마 (테이블별 데이터와 용도)
4. RLS / RPC / Realtime 정책
5. 데이터 흐름
6. ROS 측 변경 (cobot_db, task_manager, cobot_voice)
7. Web 측 변경 (web_stt_supabase_v2)
8. Launch / Bringup
9. 운영 절차
10. 디버깅 / 흔한 함정

부록 A: Firebase 경로(레거시) 개요 및 즉시 롤백 방법
부록 B: Firestore ↔ Supabase 매핑표
부록 C: 관련 커밋

---

## 1. 도입 동기와 범위

`cobot2`는 두 가지 영속화 요구를 가진다.

- **실시간 세션 동기화**: 음성 STT 흐름이 작성하는 주문/상태/테마를 웹 UI가
  실시간으로 구독.
- **이력/재고 관리**: 픽 성공/실패 로그, 재고 차감, 예외 분류.

이 두 요구를 한 백엔드(Supabase = Postgres + Realtime + RLS + RPC)에서
처리한다. Realtime publication이 실시간 구독을 담당하고, SQL 테이블과
RPC가 이력/재고를 담당한다.

**범위:**

- (포함) 주문 publish/subscribe, 로봇 상태 미러링, 재고/예외 로깅, 단일 세션
  realtime 동기화.
- (제외) 사용자 인증 (anon publishable 키 하나만 사용), 다중 세션, 음성
  파일 storage. 향후 별도 도입 시 docs를 갱신.

---

## 2. 추가/변경된 패키지

| 패키지 | 종류 | 역할 |
|---|---|---|
| `cobot_db/` | 신규 ament_python | Supabase 영속화 레이어. `CobotDbManager`, SQL 스키마, 통합 예제. |
| `cobot_task_manager/` | 수정 | `SupabaseOrderProvider` 추가, cluster_push/verification_round/primary_pick hooks. |
| `cobot_voice/` | 수정 | `supabase_status_bridge.py` 추가. |
| `cobot_bringup/` | 수정 | `bringup_supabase.launch.py` 추가, `enable_supabase_status_bridge` 인자. |
| `web_stt_supabase_v2/` | 신규 Vite/React | 브라우저 클라이언트. `@supabase/supabase-js` 사용. |

---

## 3. Supabase 스키마 (테이블별 데이터와 용도)

원본 DDL: `cobot_db/sql/init.sql`. SQL Editor에 통째로 붙여 Run (idempotent —
재실행 안전).

### 3.1 테이블 한눈에 보기

| 테이블 | 키 | 행 수 특성 | 한 줄 용도 |
|---|---|---|---|
| `public.robot_session` | `id text PK = 'current'` | 항상 1행 | 웹 ↔ ROS 실시간 세션 상태 단일 소스 |
| `public.inventory` | `nut_type text PK` | 항상 4행 (견과류 종류) | 견과류별 현재 재고 (스냅샷) |
| `public.inventory_logs` | `id uuid PK` | append-only | 모든 재고 변동의 시계열 원장 |
| `public.exception_logs` | `id uuid PK` | append-only | task 실패/이상 상태 기록 |

### 3.2 `robot_session` — 단일 행 세션 상태

**용도**: 한 사용자의 한 주문 사이클 동안 발생하는 모든 상태(질문, 답변
transcript, 추천 콤보, 테마, 로봇 진행 상태)를 1행에 담는다. 브라우저
UI는 이 행을 Realtime으로 구독하고, ROS status bridge와 브라우저 STT 흐름이
양쪽 모두 이 행을 upsert한다.

**행 수 강제**: `CHECK (id = 'current')` 제약 — 항상 단일 행. 모든 write는
`upsert(onConflict='id')`로 처리.

**컬럼 — 누가 무엇을 쓰는가:**

| 컬럼 | 타입 | writer | 의미 |
|---|---|---|---|
| `id` | text PK | (고정) | 항상 `'current'` |
| `display_state` | text | 웹 (STT flow) | UI 단계 식별자 (`idle` / `listening` / `confirming` / …) |
| `question` | text | 웹 | 챗봇이 사용자에게 던진 마지막 질문 |
| `transcript` | text | 웹 | 사용자의 마지막 음성 → 텍스트 결과 |
| `categories` | jsonb | 웹 | 선택된 카테고리 리스트 |
| `combo` | jsonb | 웹 | 추천 견과류 콤보 (배열) |
| `theme` | jsonb | 웹 | UI 색/테마 정보 |
| `intensity` | text | 웹 | 강도(`mild`/`medium`/`strong`) |
| `combo_text` | text | 웹 | 콤보의 사람이 읽는 텍스트 |
| `confirm_message` | text | 웹 | 확인 단계 메시지 |
| `error` | text | 웹 | 사용자 흐름 에러 메시지 |
| `success` | boolean | 웹 | 주문 확정 여부 (ROS는 `true`만 읽음) |
| `request_id` | text | 웹 | 주문 dedup용 UUID — ROS provider가 이 값으로 새 주문 판별 |
| `robot_state` | text | ROS (status bridge) | `idle` / `picking` / `placing` / `done` 등 |
| `robot_target_class` | text | ROS (status bridge) | 현재 픽 중인 견과류 종류 (UI 색상 갱신용) |
| `updated_at` | timestamptz | (트리거) | `BEFORE UPDATE` 트리거 `touch_updated_at`이 매번 `now()` 박음 |

**reader**: 브라우저 UI(Realtime 구독), `SupabaseOrderProvider`(주문 폴링),
디버깅 시 대시보드 Table Editor.

### 3.3 `inventory` — 견과류별 현재 재고

**용도**: 4종 견과류의 현재 남은 개수를 한 행씩 보관. 시계열이 아니라
**현재값 스냅샷**이다 (변동 이력은 `inventory_logs`).

**스키마:**

```sql
nut_type      text PK    -- CHECK in ('almond','cashew','pistachio','walnut')
current_stock int4 NOT NULL DEFAULT 1000 CHECK (current_stock >= 0)
```

**초기 데이터**: `init.sql` 시드가 4종 견과류 각 1000개로 채움.

**write 규칙**: 직접 UPDATE 금지 — **반드시 RPC `update_inventory_atomic`을
통해서만** 변경한다. 이유는 클라이언트 측 `UPDATE inventory SET
current_stock = current_stock - 1` 패턴이 동시성에서 race를 유발하므로,
서버 측 단일 트랜잭션으로 강제하기 위함이다. RLS도 anon에 SELECT만 허용.

**writer**: `update_inventory_atomic` RPC 함수만.
**reader**: 운영자 대시보드, ROS 노드 디버깅(`CobotDbManager.get_inventory()`).

### 3.4 `inventory_logs` — 재고 변동 원장 (append-only)

**용도**: `inventory`의 모든 변동(픽 차감, 리필, 보정)을 시계열로 남기는
ledger. **append-only** — 한 번 들어간 행은 수정/삭제하지 않는다.

**컬럼:**

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `id` | uuid PK | `uuid_generate_v4()` |
| `created_at` | timestamptz | `now()` default |
| `nut_type` | text | 어느 견과류인가 |
| `change_amount` | int4 | 부호 있는 변동량 (`-1` 차감, `+N` 리필) |
| `reason` | text | 자유 텍스트 라벨 (예: `primary_pick_success`, `verify_pick_success_round_2`, `refill`) |
| `resulting_stock` | int4 | 이 변동 직후의 `current_stock` (감사용 스냅샷) |

**라벨 컨벤션** (task_manager가 박는 값):
- `primary_pick_success` — 1차 픽 성공 시 -1
- `verify_pick_success_round_N` — 검증 라운드 N에서 성공 시 -1
- `refill` — 수동 리필

**writer**: `update_inventory_atomic` RPC만 (`inventory`와 같은 트랜잭션).
**reader**: 시계열 분석, 운영 보고서.

### 3.5 `exception_logs` — task 실패/이상 기록

**용도**: 로봇이 task를 수행하다 발생한 실패/이상 상태를 기록. 어떤 task의
어떤 단계에서, 어떤 클래스/포즈에서 무엇이 잘못됐는지 추적.

**컬럼:**

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `id` | uuid PK | `uuid_generate_v4()` |
| `created_at` | timestamptz | `now()` default |
| `task_name` | text | **CHECK**: `'cluster_push'` 또는 `'verification_round'`만 허용 |
| `state` | text | 자유 텍스트 단계 태그 (예: `ENTRY_HIT`, `COUNT_MISMATCH`, `MOTION_FAIL`) |
| `error_code` | int4 | 0 default (또는 action server failure_code) |
| `error_msg` | text | nullable, 사람이 읽는 에러 설명 |
| `target_class` | text | nullable, 관련 견과류 클래스 |
| `target_xyz` | jsonb | `{"x":..,"y":..,"z":..}` |
| `robot_pose` | jsonb | `{"j1":..,...}` 6축 관절 포즈 |

**state 값 컨벤션** (task_manager가 박는 값):
- `cluster_push / ENTRY_HIT` — 진입 시 충돌 감지
- `cluster_push / MOTION_FAIL` — 모션 액션 실패
- `verification_round / MOTION_FAIL` — 검증 라운드 픽 실패
- `verification_round / COUNT_MISMATCH` — 검증 라운드 종료 후 클래스별 부족분

**새 task 종류를 추가하려면**: `ALTER TABLE`로 CHECK 제약을 갈고
`CobotDbManager._VALID_TASKS`도 함께 갱신해야 한다 (의도적인 마찰 —
오타로 인한 garbage state 방지).

**writer**: 로봇(`CobotDbManager.log_robot_exception`, RLS에서 anon INSERT만 허용).
**reader**: 운영자 사후 분석.

---

## 4. RLS / RPC / Realtime 정책

### 4.1 키 모델

- 로봇/브라우저 양쪽 모두 **publishable(anon) 키** 하나만 사용.
- `service_role` 키는 로봇/브라우저에 절대 두지 않는다.
- DDL/스키마 변경은 Supabase 대시보드 SQL Editor에서만.

### 4.2 RLS 정책 (init.sql:121-160)

| 테이블 | anon SELECT | anon INSERT/UPDATE/DELETE | 비고 |
|---|---|---|---|
| `robot_session` | ✓ | ✓ ALL | 브라우저+ROS가 권위 있는 writer |
| `inventory` | ✓ | ✗ (RPC만) | 직접 쓰기 금지 |
| `inventory_logs` | ✓ | ✗ (RPC만) | append-only ledger는 RPC 안에서만 |
| `exception_logs` | ✓ | ✓ INSERT만 | 로봇이 자기 실패를 직접 기록 |

### 4.3 RPC `update_inventory_atomic`

`SECURITY DEFINER`, `plpgsql`. 시그니처:

```sql
update_inventory_atomic(p_nut_type text, p_change_amount int4, p_reason text)
  returns table (nut_type text, current_stock int4)
```

- `change_amount`는 부호 있음 — `-1`은 차감, `+N`은 리필.
- `inventory.current_stock` UPDATE와 `inventory_logs` INSERT를 한 트랜잭션에서 수행.
- underflow는 함수가 raise (에러 코드 23514).

### 4.4 Realtime publication

`supabase_realtime` publication에 `robot_session`을 add. `init.sql`의 do-block이
이 작업을 idempotent하게 수행. 권한 부족으로 silent skip된 경우 대시보드
**Database → Replication**에서 수동 토글.

---

## 5. 데이터 흐름

```
[Browser web_stt_supabase_v2]
     │ supabase.from('robot_session').upsert({id:'current', ...})
     ▼
[Postgres robot_session] ── Realtime postgres_changes ──► [Browser UI]
     ▲
     │ supabase.upsert (CobotDbManager.set_robot_state)
[ROS supabase_status_bridge]

[ROS task_manager]
  ├─ 픽 성공 ───► RPC update_inventory_atomic(-1, '<phase>_pick_success')
  │                     │
  │                     └─► inventory UPDATE + inventory_logs INSERT (한 트랜잭션)
  └─ 실패/부족 ──► exception_logs INSERT
```

- 브라우저 STT 흐름이 주문을 `robot_session`에 upsert.
- `SupabaseOrderProvider`가 `robot_session`을 폴링/구독해 새 `request_id`를 감지.
- task_manager가 액션 진행하며 픽 성공/실패를 `inventory_logs` / `exception_logs`에 기록.
- `supabase_status_bridge`가 `/task/status`, `/task/result`, `/conveyor/place_ready`를
  구독해 `robot_session.robot_state`, `robot_target_class`를 갱신.
- 브라우저 UI는 Realtime 채널로 `robot_session` 변경을 수신해 색깔/상태 표시 갱신.

---

## 6. ROS 측

### 6.1 `cobot_db/` (신규 패키지)

```
cobot_db/
├── package.xml / setup.py / setup.cfg / resource/cobot_db
├── sql/init.sql              DDL + RPC + RLS + 시드 + robot_session
├── cobot_db/
│   ├── __init__.py
│   ├── cobot_db_manager.py   CobotDbManager 클래스
│   └── integration_example.py
├── .env.example
└── README.md
```

`CobotDbManager` API:

| 메서드 | 용도 |
|---|---|
| `log_robot_exception(task_name, state, error_code, error_msg, target_class, target_xyz, robot_pose)` | `exception_logs` insert |
| `update_inventory(nut_type, amount, reason)` | RPC 호출 (원자 차감/리필) |
| `get_inventory()` / `get_stock(nut_type)` | `inventory` 조회 |
| `set_robot_state(state, **fields)` | `robot_session` upsert (status bridge용) |
| `read_robot_session()` | `robot_session` 조회 (`SupabaseOrderProvider`용) |

클라이언트는 lazy: 첫 호출 시점에 `create_client` 수행. 따라서 import-time
실패 안 함. `.env`는 `env_path` 인자 또는 CWD `.env`에서 로드.

### 6.2 `cobot_task_manager` 변경

- **`order_provider.py`**: `SupabaseOrderProvider` 추가 — `robot_session.current`을
  읽어 새 `request_id`로 dedup, `success=false` 거부.
- **`task_manager_node.py`**:
  - `order_source` 값 `supabase` 추가.
  - cluster_push 액션 실패 시 `_db_log_exception(task_name='cluster_push',
    state='MOTION_FAIL', ...)`.
  - primary/verify 픽 성공 시 `_db_update_inventory(-1, '{phase}_pick_success')`.
  - verify 픽 실패 시 `_db_log_exception(task_name='verification_round',
    state='MOTION_FAIL', ...)`.
  - verify 라운드 부족분 클래스별 `_db_log_exception(... state='COUNT_MISMATCH')`.
  - 모든 DB 호출은 swallow — 로봇 루프는 Supabase outage에 영향받지 않음.

`task_manager.yaml`에 추가된 파라미터:

```yaml
db_logging_enabled: true
db_env_path: ""            # 빈 문자열 = CWD .env
supabase_require_success: true
```

자세한 hook 위치는 `cobot_db/README.md`의 매핑 표 참조.

### 6.3 `cobot_voice/supabase_status_bridge.py`

ROS 토픽(`/task/status`, `/task/result`, `/conveyor/place_ready`)을 구독해
`robot_session.robot_state` / `robot_target_class`를 upsert. `_STATUS_TO_ROBOT_STATE`
매핑으로 ROS state → DB state 변환.

**필드명 주의**: `robot_session` 테이블에는 `robot_target_class` 컬럼만
존재하므로, 브릿지도 같은 이름으로 쓴다 (`target_class` 아님).

---

## 7. Web 측 (`web_stt_supabase_v2`)

React/Three.js/Vite 스택. `@supabase/supabase-js` 클라이언트로 `robot_session`을
upsert/구독.

### 7.1 핵심 모듈

| 파일 | 역할 |
|---|---|
| `src/lib/supabase.ts` | 클라이언트 생성, 환경변수 로드 |
| `src/lib/session.ts` | `robot_session.current` upsert/구독 헬퍼 |
| `src/hooks/useRobotSession.ts` | Realtime 채널 구독 + state normalize |
| `src/types/...` | `SessionConnection` 타입 |

**write 패턴**:

```ts
supabase.from('robot_session').upsert(
  { id: 'current', ...fields },
  { onConflict: 'id' }
);
```

`updated_at`은 클라이언트가 쓰지 않는다 — 서버 측 `touch_updated_at`
트리거가 `BEFORE UPDATE`마다 `now()`를 박는다.

**realtime 구독**:

```ts
supabase.channel(...).on('postgres_changes', ..., cb).subscribe();
```

### 7.2 환경변수

Vite는 `VITE_` prefix 붙은 env만 클라이언트 번들에 노출. 따라서 `.env`에:

```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_KEY=sb_publishable_xxxxxxxxxxxxxxxxxx
```

(`SUPABASE_URL` / `SUPABASE_KEY` 같은 prefix 없는 키는 무시됨 — 첫 셋업
시점에 실제로 막혔던 함정.)

### 7.3 `handleRobotSessionUpdate` 정규화 주의

`useRobotSession.ts`의 normalizer가 `robot_state` / `robot_target_class`를
output에서 빠뜨리면, status bridge가 매 픽마다 업데이트해도 React state는
영원히 첫 값(또는 undefined). `resolveSessionTheme`이 fallback으로 떨어져
"색이 첫 견과류에 고정"되는 회귀가 발생한다. 이 두 필드는 반드시 normalize
출력에 포함시켜야 한다 (`4a5b322` 커밋에서 수정).

---

## 8. Launch / Bringup

### 8.1 신규 launch 파일

- `cobot_bringup/launch/bringup_supabase.launch.py` — Supabase 전용 진입.
  - `db_env_path` 인자 (기본 `~/cobot_ws/src/cobot2/cobot_db/.env`)에서 키를
    파싱해 `SetEnvironmentVariable`로 `SUPABASE_URL` / `SUPABASE_KEY`를
    프로세스 env에 주입. 자식 노드들이 그대로 상속.
  - `order_source` 기본 `supabase`.
  - `enable_supabase_status_bridge` 기본 `true`.
  - 내부적으로 `full_system.launch.py`를 include.

### 8.2 기존 launch에 추가된 인자

`host_system.launch.py` / `full_system.launch.py`:
- `enable_supabase_status_bridge` 인자 (기본 `true`).
- 새 `supabase_status_bridge` Node 액션 추가.

### 8.3 bashrc alias

`~/.bashrc:141`에 추가:

```bash
alias bringup_supabase='ros2 launch cobot_bringup bringup_supabase.launch.py \
    task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false \
    dsr_mode:=real config_robot_control:=$(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config/robot_control.real.yaml'
```

---

## 9. 운영 절차

### 9.1 최초 1회 설정

1. **Supabase 프로젝트 준비**
   - 대시보드에서 Project URL과 Publishable key 확보.
2. **DDL 적용**
   - Dashboard → SQL Editor → `cobot_db/sql/init.sql` 통째로 붙여넣고 Run.
   - 재실행 안전 (idempotent).
3. **.env 파일 두 개 생성**
   - `cobot_db/.env` (ROS 노드용):
     ```
     SUPABASE_URL=https://<proj>.supabase.co
     SUPABASE_KEY=sb_publishable_xxxxxxxxxxxxxx
     ```
   - `web_stt_supabase_v2/.env` (브라우저용 — **VITE_ prefix 필수**):
     ```
     VITE_SUPABASE_URL=https://<proj>.supabase.co
     VITE_SUPABASE_KEY=sb_publishable_xxxxxxxxxxxxxx
     ```
4. **Python 의존성**
   ```bash
   pip install 'supabase>=2.0' 'python-dotenv>=1.0'
   ```
5. **Web 의존성**
   ```bash
   cd web_stt_supabase_v2 && npm install
   ```

### 9.2 매 세션 실행

ROS 측:
```bash
cd ~/cobot_ws && colcon build --packages-select cobot_db cobot_voice cobot_task_manager cobot_bringup
source install/setup.bash
bringup_supabase                   # 또는 ros2 launch cobot_bringup bringup_supabase.launch.py
```

Web 측 (별도 터미널):
```bash
cd ~/cobot_ws/src/cobot2/web_stt_supabase_v2
npm run dev                        # http://localhost:5173
```

### 9.3 E2E 흐름 검증

1. 브라우저 → 음성 주문 (wake word → 컨디션 → 강도 → 추천)
2. `robot_session.current` 행이 `success=true`, `combo=[...]`, `request_id=<new>`로 갱신됨 (대시보드 Table Editor)
3. `ros2 service call /task/start std_srvs/srv/Trigger`
4. 콘솔에 `SupabaseOrderProvider reading robot_session.current`
5. 브릿지 콘솔에 `robot_state='picking' robot_target_class='cashew'` 같은 라인
6. 브라우저 색깔이 픽 진행에 따라 변화 (`robot_target_class` 갱신 반영)
7. 픽 성공할 때마다 `inventory_logs`에 `primary_pick_success` 행 추가
8. 부족분 발생 시 `exception_logs`에 `verification_round / COUNT_MISMATCH` 행

---

## 10. 디버깅 / 흔한 함정

| 증상 | 원인 | 해결 |
|---|---|---|
| 브라우저 검은 화면 | `.env`에 `VITE_` prefix 없음 | `VITE_SUPABASE_URL` / `VITE_SUPABASE_KEY`로 수정 후 dev 서버 재시작 |
| `Invalid API key` (REST 401) | 키에 placeholder(`REPLACE_ME`) 남음, 또는 키 회전됨 | 실제 publishable key 채우기 |
| `relation "robot_session" does not exist` | init.sql 미적용 또는 robot_session 섹션 누락 | 최신 `init.sql` SQL Editor에서 Run |
| `supabase publish failed: SUPABASE_URL must be set` | 노드 실행 CWD에 `.env` 없음 + `db_env_path` 미지정 | `bringup_supabase`는 자동 처리. 수동 ros2 launch면 `set -a; . cobot_db/.env; set +a` 후 실행 |
| 픽이 시작되지만 색깔이 첫 견과류에 고정 | `handleRobotSessionUpdate`가 `robot_target_class` 누락 | `useRobotSession.ts`에서 두 필드 normalize 추가 (이미 fix) |
| Realtime 채널이 에러로 닫힘 | `supabase_realtime` publication에 `robot_session` 없음 | Dashboard → Database → Replication → toggle ON |
| `update_inventory_atomic` 함수 못 찾음 | RPC 권한 누락 (init.sql 재적용 시 grant 누락) | `init.sql`의 grant 두 줄 (anon/authenticated) 재실행 |
| 픽은 도는데 inventory_logs 비어있음 | `db_logging_enabled: false` 또는 키 누락으로 lazy init 실패 후 swallow | task_manager 로그에서 `db update_inventory ... failed` 워닝 확인 |
| `FirestoreOrderProvider reading ...` 로그가 뜸 | `order_source`가 여전히 `firestore` | launch 인자 `order_source:=supabase` 또는 `bringup_supabase` 사용 |

---

# 부록

## 부록 A: Firebase 경로(레거시) 개요 및 즉시 롤백

Supabase 경로 도입 이전 운용된 Firebase/Firestore 경로가 코드에 그대로
남아 있다. 데모 환경에서 즉시 롤백이 필요할 때 launch 인자만으로 전환
가능하다.

### A.1 구성

- **백엔드**: Firebase Firestore (`/robot_session/current` 단일 문서).
- **Web**: `web_stt_firebase_v2` (firebase-js 클라이언트, `onSnapshot` 구독).
- **ROS**: `cobot_voice/firebase_status_bridge.py` (firebase_admin SDK로
  `set({merge:true})`).
- **Order provider**: `FirestoreOrderProvider`.

### A.2 데이터 흐름

```
[Browser web_stt_firebase_v2]
     │ setDoc({merge:true})
     ▼
[Firestore /robot_session/current]
     │ onSnapshot
     ▼
[Browser UI]

[ROS firebase_status_bridge]
     │ firebase_admin.set({merge})
     ▼
[Firestore /robot_session/current]
     ▲
     │ onSnapshot
     ▼
[Browser UI ← robot_state 표시]
```

재고/예외 로그는 Firestore 경로에는 없다 (이력/재고는 Supabase 도입 이후
새로 들어온 기능).

### A.3 즉시 롤백 명령

전체 환경을 손 안 대고 launch 인자만 토글:

```bash
ros2 launch cobot_bringup full_system.launch.py \
    order_source:=firestore \
    enable_firebase_status_bridge:=true \
    enable_supabase_status_bridge:=false \
    ... (나머지 기존 인자)
```

기존 `bringup` alias도 그대로 동작 (firebase + firestore 기본).

## 부록 B: Firestore ↔ Supabase 매핑표

### B.1 백엔드 개념

| Firestore | Supabase | 비고 |
|---|---|---|
| `/robot_session/current` 문서 | `robot_session` 테이블 (1행, `id='current'`) | 구조 1:1 대응 |
| `serverTimestamp()` | `BEFORE UPDATE` 트리거 `touch_updated_at` | 서버측 자동 갱신 |
| `setDoc(ref, fields, {merge:true})` | `upsert({id, ...fields}, {onConflict:'id'})` | merge 시맨틱 |
| `onSnapshot(ref, cb)` | `supabase.channel(...).on('postgres_changes', ..., cb).subscribe()` | Realtime 구독 |
| Security Rules | RLS 정책 (`init.sql:121-160`) | 권한 모델 |

### B.2 필드명 차이

| Firebase 측 | Supabase 측 | 비고 |
|---|---|---|
| `target_class` | `robot_target_class` | `robot_session` 테이블 컬럼명 |

### B.3 Web 파일 매핑

| `web_stt_firebase_v2` | `web_stt_supabase_v2` | 변경 |
|---|---|---|
| `src/lib/firebase.ts` | `src/lib/supabase.ts` | 클라이언트 생성 |
| `setDoc(ref, fields, {merge:true})` | `supabase.from(t).upsert(...)` | `src/lib/session.ts` |
| `onSnapshot` | Realtime channel | `useRobotSession.ts` |
| `FirestoreConnection` 타입 | `SessionConnection` | `types.ts` |

### B.4 ROS 브릿지 매핑

| Firebase 측 | Supabase 측 |
|---|---|
| `cobot_voice/firebase_status_bridge.py` | `cobot_voice/supabase_status_bridge.py` |
| `firebase_admin.firestore` | `CobotDbManager.set_robot_state` |
| `enable_firebase_status_bridge` launch 인자 | `enable_supabase_status_bridge` |

구독 토픽, `_STATUS_TO_ROBOT_STATE` 매핑, parse 함수는 1:1 동일.

## 부록 C: 관련 커밋

- `69e86dd` — `feat: end-to-end Supabase migration (cobot_db + web + bridges)`
- `4a5b322` — `fix(web_stt_supabase_v2): propagate robot_state + robot_target_class through normalizer`
- `ac40c3d` — `Merge branch 'feat/supabase-migration' into main`
