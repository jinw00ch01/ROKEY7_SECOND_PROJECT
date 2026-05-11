# Supabase 마이그레이션

이 문서는 `feat/supabase-migration` 브랜치에서 도입되어 `main`에 머지된
Supabase 백엔드 통합을 다룬다. 기존 Firebase/Firestore 경로는 그대로
유지되며, **launch 인자 토글로 어느 백엔드로 갈지 선택**한다. 두 경로가
공존하는 이유 — 데모 환경에서 즉시 롤백이 필요할 수 있고, 음성/UI 흐름과
영속화(재고/예외 로깅) 둘 다 동시에 재작성하기엔 위험이 크기 때문이다.

## 문서 세트와의 관계

- `docs/01_system_architecture.md` — 전체 시스템 설계 (Firestore 기준).
- `docs/02_ros_node_architecture.md` — ROS 인터페이스 (Firestore 기준).
- `docs/03_run_manual.md` — 운영자 실행 절차 (Firestore 경로).
- `docs/09_supabase_migration.md` — **이 파일**. Supabase 경로의 모든 차이점.

01~03의 본문은 의도적으로 손대지 않았다. 운영자가 Supabase 경로로 가려면
이 문서를 본 후 01~03의 firestore/firebase 언급을 본 문서의 Supabase
등가물로 치환해 읽으면 된다.

## 목차

1. 마이그레이션 동기와 범위
2. 추가/변경된 패키지
3. Supabase 스키마 (SQL)
4. RLS / RPC / Realtime 정책
5. 데이터 흐름 (Firestore vs Supabase 비교)
6. ROS 측 변경 (cobot_db, task_manager, cobot_voice)
7. Web 측 변경 (web_stt_supabase_v2)
8. Launch / Bringup
9. 운영 절차 (Supabase 경로)
10. 디버깅 / 흔한 함정

---

## 1. 마이그레이션 동기와 범위

원래 `cobot2`는 두 가지 영속화 요구를 가졌다.

- **실시간 세션 동기화**: 음성 STT 흐름이 작성하는 주문/상태/테마를 웹 UI가
  실시간으로 구독. → Firestore가 잘 맞았다.
- **이력/재고 관리**: 픽 성공/실패 로그, 재고 차감, 예외 분류. → SQL이
  더 자연스러웠다.

초기 의도는 "실시간은 Firebase, 이력/재고는 Supabase"였으나, 두 백엔드를
동시에 운용하면 자격증명/보안 모델/네트워크 의존 표면이 두 배가 되어
데모 환경의 운영 부담이 컸다. 그래서 Supabase 하나로 통일하는 경로를
추가했다 — 단, Firebase 경로는 즉시 폐기하지 않고 launch 토글로 공존한다.

**범위:**

- (포함) 주문 publish/subscribe, 로봇 상태 미러링, 재고/예외 로깅, 단일 세션
  realtime 동기화.
- (제외) 사용자 인증 (anon publishable 키 하나만 사용), 다중 세션, 음성
  파일 storage. 향후 별도 도입 시 docs를 갱신.

---

## 2. 추가/변경된 패키지

| 패키지 | 종류 | 변경 |
|---|---|---|
| `cobot_db/` | **신규** ament_python | Supabase 영속화 레이어. `CobotDbManager`, SQL 스키마, 통합 예제. |
| `cobot_task_manager/` | 수정 | `SupabaseOrderProvider` 추가, cluster_push/verification_round/primary_pick hooks. |
| `cobot_voice/` | 수정 | `supabase_status_bridge.py` 추가 (firebase 버전과 병행). |
| `cobot_bringup/` | 수정 | `bringup_supabase.launch.py` 추가, `enable_supabase_status_bridge` 인자. |
| `web_stt_supabase_v2/` | **신규** Vite/React | `web_stt_firebase_v2`의 Supabase 포트. firebase-js → supabase-js. |

---

## 3. Supabase 스키마 (SQL)

원본: `cobot_db/sql/init.sql`. SQL Editor에 통째로 붙여 Run (idempotent —
재실행 안전).

### 3.1 테이블 요약

| 테이블 | 키 | 용도 |
|---|---|---|
| `public.exception_logs` | `id uuid PK` | task 종류별 실패 기록 |
| `public.inventory` | `nut_type text PK` | 견과류별 현재 재고 (4 rows) |
| `public.inventory_logs` | `id uuid PK` | 모든 재고 변동의 append-only 원장 |
| `public.robot_session` | `id text PK = 'current'` | 단일 행 세션 (web ↔ ROS 인터럽) |

### 3.2 exception_logs

`task_name`에 CHECK 제약으로 `'cluster_push'` 또는 `'verification_round'`만
허용. 새 task 종류를 늘리려면 ALTER TABLE로 CHECK를 갈고 `cobot_db_manager._VALID_TASKS`도
함께 갱신해야 한다 (의도적인 마찰).

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | uuid | `uuid_generate_v4()` |
| `created_at` | timestamptz | now() default |
| `task_name` | text | CHECK 두 값만 |
| `state` | text | free-form short tag (예: `ENTRY_HIT`, `COUNT_MISMATCH`, `MOTION_FAIL`) |
| `error_code` | int4 | 0 default (또는 action server failure_code) |
| `error_msg` | text | nullable |
| `target_class` | text | nullable |
| `target_xyz` | jsonb | `{"x":..,"y":..,"z":..}` |
| `robot_pose` | jsonb | `{"j1":..,...}` |

### 3.3 inventory

```sql
nut_type      text PK    -- CHECK in (almond,cashew,pistachio,walnut)
current_stock int4 NOT NULL DEFAULT 1000 CHECK (current_stock >= 0)
```

차감/리필은 **반드시 RPC `update_inventory_atomic`로만** 한다.
직접 UPDATE는 RLS로 차단 (anon은 SELECT만). 이유: 클라이언트 측에서
`UPDATE inventory SET current_stock = current_stock - 1` 같은 형식이
race를 유발하므로 server-side 단일 트랜잭션으로 강제.

### 3.4 inventory_logs

append-only. `reason` 컬럼이 자유 텍스트라서 `primary_pick_success`,
`verify_pick_success_round_N`, `refill` 같은 라벨로 시계열 분석 가능.

### 3.5 robot_session

Firestore의 `robot_session/current` 문서와 1:1 대응. **단일 행** 운영을
`CHECK (id = 'current')` 제약으로 강제. 모든 write는 upsert(onConflict='id').

| 컬럼 | 타입 | Firestore 등가 |
|---|---|---|
| `id` | text PK | doc id `current` |
| `display_state` | text | 동일 |
| `question` / `transcript` | text | 동일 |
| `categories` / `combo` / `theme` | jsonb | 동일 (구조 보존) |
| `intensity` / `combo_text` / `confirm_message` / `error` | text | 동일 |
| `success` | boolean | 동일 |
| `robot_state` / `robot_target_class` | text | 동일 (status bridge가 작성) |
| `request_id` | text | 주문 dedup용 |
| `updated_at` | timestamptz | Firestore의 `serverTimestamp()` → 트리거 `touch_updated_at` |

`serverTimestamp()` 대체로 `BEFORE UPDATE` 트리거가 매번 `now()`를 박는다.
클라이언트는 신경 쓰지 않는다.

---

## 4. RLS / RPC / Realtime 정책

### 4.1 키 모델

- 로봇/브라우저 양쪽 모두 **publishable(anon) 키** 하나만 사용.
- `service_role` 키는 로봇/브라우저에 절대 두지 않는다.
- DDL/스키마 변경은 Supabase 대시보드 SQL Editor에서만.

### 4.2 RLS 정책 (init.sql:121-160)

| 테이블 | anon SELECT | anon INSERT/UPDATE/DELETE | 비고 |
|---|---|---|---|
| `inventory` | ✓ | ✗ (RPC만) | 직접 쓰기 금지 |
| `inventory_logs` | ✓ | ✗ (RPC만) | append-only ledger는 RPC 안에서만 |
| `exception_logs` | ✓ | ✓ INSERT만 | 로봇이 자기 실패를 직접 기록 |
| `robot_session` | ✓ | ✓ ALL | 브라우저+ROS가 권위 있는 writer |

### 4.3 RPC `update_inventory_atomic`

`SECURITY DEFINER`, `plpgsql`. 시그니처:

```sql
update_inventory_atomic(p_nut_type text, p_change_amount int4, p_reason text)
  returns table (nut_type text, current_stock int4)
```

`change_amount`는 부호 있음 — `-1`은 차감, `+N`은 리필.
underflow는 함수가 raise (에러 코드 23514).

### 4.4 Realtime publication

`supabase_realtime` publication에 `robot_session`을 add. `init.sql`의 do-block이
이 작업을 idempotent하게 수행. 권한 부족으로 silent skip된 경우 대시보드
**Database → Replication**에서 수동 토글.

---

## 5. 데이터 흐름 (Firestore vs Supabase)

### 5.1 Firestore 경로 (legacy)

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

### 5.2 Supabase 경로

```
[Browser web_stt_supabase_v2]
     │ supabase.from('robot_session').upsert({id:'current', ...})
     ▼
[Postgres robot_session] ── Realtime postgres_changes ──► [Browser UI]
     ▲
     │ supabase.upsert (CobotDbManager.set_robot_state)
[ROS supabase_status_bridge]
```

`/task/status`, `/task/result`, `/conveyor/place_ready` 토픽 흐름은 동일.
브릿지가 호출하는 백엔드만 다를 뿐.

---

## 6. ROS 측 변경

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
| `log_robot_exception(task_name, state, error_code, error_msg, target_class, target_xyz, robot_pose)` | exception_logs insert |
| `update_inventory(nut_type, amount, reason)` | RPC 호출 (원자 차감/리필) |
| `get_inventory()` / `get_stock(nut_type)` | 조회 |
| `set_robot_state(state, **fields)` | robot_session upsert (status bridge용) |
| `read_robot_session()` | robot_session 조회 (SupabaseOrderProvider용) |

클라이언트는 lazy: 첫 호출 시점에 `create_client` 수행. 따라서 import-time
실패 안 함. `.env`는 `env_path` 인자 또는 CWD `.env`에서 로드.

### 6.2 `cobot_task_manager` 변경

- **`order_provider.py`**: `SupabaseOrderProvider` 추가 (FirestoreOrderProvider의
  미러 — request_id dedup, success=false 거부).
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

### 6.3 `cobot_voice/supabase_status_bridge.py` (신규)

`firebase_status_bridge.py`의 기능적 트윈. 구독 토픽, `_STATUS_TO_ROBOT_STATE`
매핑, parse 함수까지 1:1. write 백엔드만 `CobotDbManager.set_robot_state`로
대체. firebase_admin 의존 없음.

**필드명 차이**: firebase 버전은 `target_class`로 썼으나, supabase 버전은
`robot_target_class` — `robot_session` 테이블에는 이 이름의 컬럼만 존재.

---

## 7. Web 측 변경 (`web_stt_supabase_v2`)

`web_stt_firebase_v2`의 직접 포트. 같은 React/Three.js/Vite 스택,
firebase-js만 `@supabase/supabase-js`로 교체.

### 7.1 파일 매핑

| Firestore 시절 | Supabase | 변경 |
|---|---|---|
| `src/lib/firebase.ts` | `src/lib/supabase.ts` | 클라이언트 생성 |
| `setDoc(ref, fields, {merge:true})` | `supabase.from(t).upsert({id, ...fields}, {onConflict:'id'})` | session.ts |
| `serverTimestamp()` | `touch_updated_at` 트리거 (서버 측) | 클라이언트는 미설정 |
| `onSnapshot(ref, cb)` | `supabase.channel(...).on('postgres_changes', ..., cb).subscribe()` | useRobotSession.ts, session.ts |
| `FirestoreConnection` 타입 | `SessionConnection` | types.ts |

### 7.2 환경변수

Vite는 `VITE_` prefix 붙은 env만 클라이언트 번들에 노출. 따라서 .env에:

```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_KEY=sb_publishable_xxxxxxxxxxxxxxxxxx
```

(`SUPABASE_URL` / `SUPABASE_KEY` 같은 prefix 없는 키는 무시됨 — 첫 마이그레이션
시점에 실제로 막혔던 함정.)

### 7.3 `handleRobotSessionUpdate` 정규화 함정

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
  - `enable_firebase_status_bridge` 기본 `false`, `enable_supabase_status_bridge`
    기본 `true`.
  - 내부적으로 `full_system.launch.py`를 include.

### 8.2 기존 launch 변경

- `host_system.launch.py` / `full_system.launch.py`:
  - `enable_supabase_status_bridge` 인자 추가 (기본 `true`).
  - `enable_firebase_status_bridge` 기본 `true` → `false`로 변경 (Supabase
    경로가 디폴트라는 신호).
  - 새 `supabase_status_bridge` Node 액션 추가.

### 8.3 bashrc alias

`~/.bashrc:141`에 추가:

```bash
alias bringup_supabase='ros2 launch cobot_bringup bringup_supabase.launch.py \
    task_autostart:=false enable_realsense:=false enable_dsr_bringup:=false \
    dsr_mode:=real config_robot_control:=$(ros2 pkg prefix cobot_robot_control)/share/cobot_robot_control/config/robot_control.real.yaml'
```

기존 `bringup`(firebase + firestore)은 그대로 두고 병행.

---

## 9. 운영 절차 (Supabase 경로)

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
| `FirestoreOrderProvider reading ...` 로그가 뜸 | `order_source`가 여전히 `firestore` | launch 인자 `order_source:=supabase` 또는 `bringup_supabase` 사용 |
| Realtime 채널이 에러로 닫힘 | `supabase_realtime` publication에 `robot_session` 없음 | Dashboard → Database → Replication → toggle ON |
| `update_inventory_atomic` 함수 못 찾음 | RPC 권한 누락 (init.sql 재적용 시 grant 누락) | `init.sql`의 grant 두 줄 (anon/authenticated) 재실행 |
| 픽은 도는데 inventory_logs 비어있음 | `db_logging_enabled: false` 또는 키 누락으로 lazy init 실패 후 swallow | task_manager 로그에서 `db update_inventory ... failed` 워닝 확인 |

---

## 부록 A: Firebase 경로로 즉시 롤백

전체 환경을 손 안 대고 launch 인자만 토글:

```bash
ros2 launch cobot_bringup full_system.launch.py \
    order_source:=firestore \
    enable_firebase_status_bridge:=true \
    enable_supabase_status_bridge:=false \
    ... (나머지 기존 인자)
```

기존 `bringup` alias도 그대로 동작.

## 부록 B: 관련 커밋

- `69e86dd` — `feat: end-to-end Supabase migration (cobot_db + web + bridges)`
- `4a5b322` — `fix(web_stt_supabase_v2): propagate robot_state + robot_target_class through normalizer`
- `ac40c3d` — `Merge branch 'feat/supabase-migration' into main`
