# 검증 라운드 및 부족분 보정 루프 보고서

> **대상**: 픽 사이클 마무리 단계의 "최종 견과류 개수 확인 → 부족분 재픽" 로직.
> 주문 처리가 일단 끝났다고 보이는 시점에서, 실제로 옮겨진 개수와 주문 사이의
> 차이를 검출 결과로 검증하고, 차이가 있으면 자동으로 사이클을 재개해 누락분을
> 채우는 메커니즘.
>
> **관련 코드**: `cobot_task_manager/cobot_task_manager/task_manager_node.py`
>   (특히 `_count_detected_objects`, `_detect_counts_from_home`,
>   `_remaining_from_verification`, `_process_order_book`, `_run`)
>
> **시점**: 2026-05-09 작업 (`2ab751b feat(task_manager): port verification rounds from install to src`)

---

## 1. 배경 — 기존 구조의 빈자리

### 1.1 픽 사이클의 결과 신호

picking 액션은 다음 중 하나로 끝난다.

| 결과 | task_manager 처리 |
|---|---|
| `success=True` | `order.consume_one(target_class)` — 주문 카운트 1 차감 |
| `failure_code=2` (grasp_not_detected) | retry / skip 분기 |
| `failure_code=3,4,5` (motion/cancel/workspace) | ABORT |

문제는 `success=True`가 곧 "**견과류가 컨베이어에 안착했다**"를 의미하지
않는다는 것이다. RG2 그리퍼의 grip-detected 비트는 close 직후 손가락 사이
뭔가가 있다는 것만 보여주고, lift→transit 도중 떨어져도 액션은 success로
끝난다. 결과적으로 **주문 N개를 처리했다고 보고했지만 실제로는 N-1개만
도착하는 케이스**가 발생.

### 1.2 직전 구조 (정상 처리만 가정)

```
fetch order → home → for each (class, count):
                         detect → pick → consume_one
                     → done
```

이 흐름은 **각 액션이 success를 반환하면 그만큼 컨베이어로 옮겨졌다**는
가정에 의존한다. 실패 케이스(transit 중 drop)는 구조적으로 보정되지 않음.

---

## 2. 설계 — 사이클 시작/종료 시점의 "관측"으로 차이 측정

### 2.1 핵심 아이디어

> 사이클 **시작 시 detect → 주문 처리 → 시작 카운트와 끝 카운트의 차이**가
> 실제로 옮겨진 양. 주문 수량과 비교해 부족분이 있으면 **부족분만 새 OrderBook
> 으로 만들어 다시 처리**하고, 라운드별로 detect-기반 재계산 반복.

이 설계는 두 가지 invariant에 기댄다.

1. **워크스페이스 안의 너트만 detection**된다 (workspace 게이트 적용).
   따라서 컨베이어로 옮겨진 너트는 다음 detection에서 자동 제외.
2. detect_once는 **trigger 기반**으로 결정성이 보장됨 (06번 문서 참조).
   같은 정지 상태에서 호출하면 동일한 카운트가 나옴.

### 2.2 데이터 흐름

```
[INIT]
  │
  ├─ home + settle
  │
  ├─ initial_detect → initial_counts (per-class)
  │
  ▼
[PRIMARY] _process_order_book(order, "primary")
  │  detect → pick × 주문 수량
  │
  ▼
[VERIFY 루프] for round in range(max_verification_rounds):
  │  ┌─ _detect_counts_from_home(...) → final_counts
  │  ├─ remaining = _remaining_from_verification(ordered, initial, final)
  │  ├─ if remaining empty: break
  │  └─ _process_order_book(OrderBook(remaining), "verifyN")
  │
  ▼
[DONE] publish 결과 (성공/부족분 보고)
```

### 2.3 remaining 계산

```python
moved_estimated = initial_counts - final_counts     # 사이클 동안 사라진 양
remaining = max(0, ordered_counts - moved_estimated)   # 부족분
remaining = min(remaining, ordered_counts)             # over-pick 클램프
```

세 가지 카운트가 같은 게이트(conf, transform_valid, depth, workspace)를
통과한 detection만 세므로 일관성 보장. `target_selector`가 픽 후보로 쓰는
필터와 동일한 함수 (`_count_detected_objects`)를 사용.

---

## 3. 구현 상세

### 3.1 `_count_detected_objects` (task_manager_node.py:301-326)

DetectedObjectArray를 클래스별로 카운트. 게이트:

```python
counts = {cls: 0 for cls in self._priority}
for obj in objects_msg.objects:
    if obj.class_name not in counts: continue
    if obj.confidence < self._conf_gate: continue
    if not obj.transform_valid: continue
    if obj.base_xyz.z <= self._min_depth_mm: continue
    if not workspace.contains(obj.base_xyz): continue
    counts[obj.class_name] += 1
```

`_priority`는 yaml의 `class_priority` (almond, cashew, pistachio, walnut).
priority 외 클래스(예: 검출 노이즈성 미지정 클래스)는 카운트되지 않음.

### 3.2 `_detect_counts_from_home(label)` (task_manager_node.py:328-340)

각 검증 라운드의 entry point. 일관된 관측 조건을 보장:

1. `_call_home()` — 홈 자세 이동 (`/robot/home` 서비스)
2. `time.sleep(self._inter_pick_delay_sec)` — 카메라 buffer settle
3. `_detect_once()` — perception 호출
4. `_count_detected_objects(...)` — 카운트 추출

home 도착 후 settle delay (기본 0.5s)를 두는 이유: 카메라 publish 큐에
모션 중 frame이 남아있을 수 있음. trigger 기반이라도 settle 직후 호출이
안전.

### 3.3 `_remaining_from_verification` (task_manager_node.py:342-357)

```python
remaining = {}
for cls in self._priority:
    ordered = max(0, ordered_counts[cls])
    initial = max(0, initial_counts[cls])
    final = max(0, final_counts[cls])
    moved_estimated = initial - final
    remaining[cls] = min(ordered, max(0, ordered - moved_estimated))
return remaining
```

세 가지 max(0, ...) 클램프와 over-pick 보호 (`min(ordered, ...)`)가
들어있다. 이유:
- detection 노이즈로 final이 일시적으로 initial보다 클 수 있음 → moved
  음수 가능 → max(0, ordered - moved) = ordered + |moved| > ordered가 되면
  주문보다 더 픽하게 됨. `min(ordered, ...)`로 차단.

### 3.4 `_process_order_book(order, phase)` (task_manager_node.py:421-509)

Primary와 verify 라운드가 **공유**하는 픽 루프. `phase` 문자열은 로그/state
info용 (예: "primary", "verify1", "verify2"). 반환값:
- `True` — 주문 소진 (정상 완주)
- `False` — ABORT 또는 safety_stop

동일 함수를 재사용함으로써 retry 정책 / cluster 분기 / 게이트 등이 두 단계
모두에서 일관되게 적용된다.

### 3.5 `_run` 오케스트레이션 (task_manager_node.py:513-593)

```python
def _run(self):
    self._cluster_push_counts = {}                 # 사이클별 cap 리셋
    order = self._order_provider.fetch()
    ordered_counts = dict(order.counts)            # 원래 주문 보존

    if not self._call_home(): ABORT
    time.sleep(inter_pick_delay)

    initial_counts = None
    if verification_enabled:
        objects_msg = self._detect_once()
        if objects_msg is None: ABORT_initial_verify_detect_failed
        initial_counts = self._count_detected_objects(objects_msg)

    if not self._process_order_book(order, "primary"): return

    final_counts = None
    correction_order = None
    if verification_enabled and initial_counts is not None:
        for round_index in range(max(0, max_verification_rounds)):
            final_counts = self._detect_counts_from_home(...)
            if final_counts is None: ABORT_final_verify_detect_failed
            remaining = self._remaining_from_verification(
                ordered_counts, initial_counts, final_counts
            )
            correction_order = OrderBook(counts=remaining)
            if not correction_order.has_remaining(): break
            if not self._process_order_book(correction_order, f"verify{round_index+1}"):
                return

    self._set_state(TaskState.DONE)
    if correction_order is not None and correction_order.has_remaining():
        # max_verification_rounds 다 돌아도 보정 못 한 부족분 보고
        self._publish_result(False, f"counts={order.counts} correction={correction_order.counts}")
    else:
        self._publish_result(order.all_done(), f"counts={order.counts} final_counts={final_counts}")
```

핵심 장면:
- `ordered_counts`를 사이클 시작 시 dict 복사로 보존. 이후 order.counts가
  consume으로 0으로 변하더라도 verification 계산에 영향 없음.
- 라운드 안에 `correction_order.has_remaining() == False`이면 즉시 break —
  자동 조기 종료.
- 라운드 모두 소진해도 부족분이 남으면 `_publish_result(False, ...)`로
  보고 (raise는 안 함; 외부 모니터링이 판단하도록 데이터만 publish).

---

## 4. 라운드별 동작 시나리오

### 4.1 정상 케이스 (drop 없음)

```
ordered = {almond: 2, cashew: 2}
initial = {almond: 2, cashew: 2}        ← 워크스페이스에 너트가 정확히 4개
[primary] pick almond x 2, pick cashew x 2 → success
final round 1 = {almond: 0, cashew: 0}  ← 모두 옮겨짐
remaining = {almond: 0, cashew: 0}
break (has_remaining()=False)
DONE: success
```

→ verification 라운드 1번만 돌고 즉시 종료 (오버헤드 ≈ home + detect_once).

### 4.2 1개 drop 케이스

```
ordered = {almond: 2}
initial = {almond: 2}
[primary] pick almond x 2 → success (그러나 1개는 transit에서 drop)
final round 1 = {almond: 1}             ← drop된 1개가 워크스페이스에 남음
moved = 2 - 1 = 1
remaining = {almond: max(0, 2-1)} = {almond: 1}
[verify1] pick almond x 1 → success
final round 2 = {almond: 0}
remaining = {almond: 0}
break
DONE: success
```

→ 부족분 1개를 verify 라운드 1에서 자동 보충.

### 4.3 max_verification_rounds 초과 케이스

```
ordered = {walnut: 2}
initial = {walnut: 2}
[primary] pick x 2 → success (모두 drop)
[verify1] final={walnut:2}, remaining={walnut:2} → pick x 2 → success (또 drop)
[verify2] final={walnut:2}, remaining={walnut:2} → pick x 2 → success (또 drop)
...
[verify5] 같은 패턴 반복 (max_verification_rounds = 5)
DONE: failure (correction_order.has_remaining()=True)
publish: "counts={...} correction={walnut: 2} skipped=[]"
```

→ 5라운드 cap. 같은 패턴이 반복되면 외부 모니터링이 알도록 result에 부족분
명시.

### 4.4 over-pick 클램프가 작동하는 케이스

```
ordered = {almond: 2}
initial = {almond: 1}                   ← 검출 노이즈로 1개만 잡힘
[primary] pick x 2 (어쨌든 주문은 2) → success
final round 1 = {almond: 0}
moved = 1 - 0 = 1
remaining = min(2, max(0, 2-1)) = 1     ← 클램프 없으면 1, 있어도 1 (이 경우 동일)

# 다른 노이즈 케이스
initial = {almond: 0}, final = {almond: 0}, moved = 0
remaining = min(2, max(0, 2-0)) = 2
[verify1] pick x 2 (워크스페이스에 너트 없으면 detect_miss → skip)
```

`min(ordered, ...)` 클램프는 "moved < 0 → ordered - moved > ordered"
케이스에서 추가 픽을 막는다. 이 보호가 없으면 detection 흔들림이
verification 라운드를 무한히 반복시킬 수 있음.

---

## 5. 파라미터

`cobot_task_manager/config/task_manager.yaml`:

```yaml
verification_enabled: true
max_verification_rounds: 5
inter_pick_delay_sec: 0.5
```

| 파라미터 | 기본값 | 의미 |
|---|---|---|
| `verification_enabled` | `true` | 라운드 자체 on/off |
| `max_verification_rounds` | 5 | cap (이후는 부족분 그대로 보고) |
| `inter_pick_delay_sec` | 0.5 | home 도착 후 detect까지 settle |

`max_verification_rounds = 0` 으로 두면 verify 단계 자체를 스킵 (primary
끝나면 곧장 DONE).

---

## 6. State 토픽 / Result 토픽

매 라운드 진입 시 `/task/status`에 publish:

```
[state] verify round=1
[state] detect verify1
[state] select_target almond
[state] pick_and_place almond
...
[state] verify round=2
...
[state] done
```

`/task/result`에는 사이클 종료 시 한 번 publish:

```
success counts={almond: 0, cashew: 0} final_counts={almond: 0, cashew: 0} skipped=[]
```

또는 부족분 발생 시:

```
failure counts={almond: 0, cashew: 0} correction={walnut: 2} skipped=[]
```

이 메시지는 `firebase_status_bridge`가 Firestore에 미러링해 웹 UI가
"completed"/"partial" 상태를 표시하는 데 쓰인다.

---

## 7. 한계 / 향후 과제

### 7.1 워크스페이스 안 너트만 카운트됨

drop된 너트가 워크스페이스 밖으로 굴러가면 final_counts에 잡히지 않아
remaining이 0으로 계산되고 보충이 안 된다. 현재 워크스페이스 게이트가
보수적이라 (zmin 40 ~ zmax 80mm) 이 케이스는 드물지만, 굴러가는 견과류
(예: cashew의 곡선 표면)에서는 가능.

### 7.2 동일 식별자가 아니라 카운트만 비교

initial=2, final=1로 1개 픽됐다고 추정해도, 실제로는 "원래 너트 2개 다
사라지고 새로 1개 굴러 들어왔을" 경우 같은 결과가 나옴. 인스턴스 추적이
없어 이 ambiguity는 구조적으로 해소 안 됨. 실기에서 너트가 외부에서
들어올 일은 없으므로 무시 가능.

### 7.3 verification 라운드의 picking은 다시 grip 실패 가능

verify 라운드에서도 동일한 retry 정책이 적용되지만, 같은 너트가 같은
이유로 grip 실패하면 결국 `max_grasp_failures`에 걸려 skip된다.
이 경우 final_counts에 그대로 남아있으므로 다음 라운드에서 다시 시도되고,
max_verification_rounds까지 가서 부족분으로 보고.

---

## 8. 참고 코드 위치

| 함수 | 파일:라인 |
|---|---|
| `_count_detected_objects` | task_manager_node.py:301 |
| `_detect_counts_from_home` | task_manager_node.py:328 |
| `_remaining_from_verification` | task_manager_node.py:342 |
| `_process_order_book` | task_manager_node.py:421 |
| `_run` | task_manager_node.py:513 |

## 9. 관련 문서

- `docs/changelog/2026-05-09_130418.md` §6 (verification 도입 일지)
- `docs/01_system_architecture.md` §2 (E2E 흐름)
- `docs/06_perception_trigger_redesign.md` (이 메커니즘이 의존하는 detect_once의 결정성)
