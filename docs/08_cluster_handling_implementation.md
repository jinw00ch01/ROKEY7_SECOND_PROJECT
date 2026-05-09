# 군집 견과류 분산 처리 구현 보고서

> **대상**: 가까이 모여 있는 견과류 군집을 닫힌 그리퍼로 밀어 분산시킨 뒤
> 재관측해 정상 픽으로 돌아가는 메커니즘. 설계 명세 문서
> (`docs/05_clustered_nuts_handling.md`)에 대응하는 **구현 보고서**.
>
> **관련 코드**:
> - `cobot_task_manager/cobot_task_manager/cluster_policy.py` (신규, 기하 로직)
> - `cobot_task_manager/cobot_task_manager/task_manager_node.py` (디스패치)
> - `cobot_task_manager/cobot_task_manager/task_state.py` (`CLUSTER_PUSH` 상태)
> - `cobot_task_manager/config/task_manager.yaml` (파라미터)
> - `cobot_robot_control/cobot_robot_control/motion_sequence.py` (모션)
> - `cobot_robot_control/cobot_robot_control/robot_control_node.py` (액션 분기)
>
> **시점**: 2026-05-09 작업 (커밋 미정 — 본 보고서 작성 시점에는 working tree).

---

## 1. 배경 — 군집 픽의 실패 패턴

너트가 서로 가까이 모여 있는 경우, 단일 픽 동작 중 다음 패턴이 관찰됨.

- 그리퍼가 pre_grasp_width로 벌어진 채 하강할 때, **인접 너트의 OBB가 그
  폭 안에 있으면** 닫는 동작이 인접 너트를 옆으로 튕긴다.
- 튕긴 너트는 워크스페이스 가장자리로 굴러가거나 다른 너트와 또 다른 군집을
  형성. 결과적으로 후속 픽에서 같은 너트가 detection은 되지만 위치가 변해
  잘못된 좌표를 잡으려다 실패.

설계 문서 05의 해결 방안:
> 군집 상태로 판단되는 견과류는 **밀어내기 동작 (push-apart)** 으로 군집을
> 분산시킨 후, 다시 관측 단계부터 본 작업을 재시작한다.

---

## 2. 설계 결정 (Why)

### 2.1 별도 액션 메시지 대신 sentinel target_class 재사용

새 `.action` 정의를 추가하면 `cobot_msgs` 패키지의 인터페이스 (C++/Python)
재생성, action client/server 양쪽 코드에 새 타입 binding 등이 필요. 이
세트의 부담이 본질적인 것이 아니라고 판단해, **`PickAndPlace` 액션을
그대로 쓰면서 `target_class == "__cluster_push__"` sentinel일 때 의미를
재해석**하는 방식 채택.

| 필드 | pick 의미 | cluster push 의미 |
|---|---|---|
| `target_class` | 클래스명 | sentinel (`__cluster_push__`) |
| `grasp_xyz` | 그립 위치 | 진입점 (descend 좌표) |
| `grasp_yaw` | 그립 yaw | push 방향 (atan2(dy, dx)) |
| `pre_grasp_width_mm` | pre-position 폭 | 0 (닫힌 채 진입) |
| `return_xyz` | 컨베이어 place | push 종점 |
| `return_zyz_deg` | place orientation | (사용 안 함) |

sentinel 문자열은 **`task_manager_node`와 `robot_control_node` 양쪽에
동일 상수**로 박혀 있고, "한쪽 변경 시 같이 갱신"이라는 주석을 양쪽에
남겨 sync 깨짐을 방지.

### 2.2 cluster_policy를 별도 모듈로

기하 계산을 task_manager_node에서 분리해:
- 단위 테스트 가능 (rclpy 의존 없이 import 가능)
- 다른 호출자(예: 디버그 스크립트)도 재사용 가능
- task_manager_node가 비대해지는 것 방지

같은 패턴으로 이미 분리되어 있는 `target_selector.py`를 따랐다.

### 2.3 push z = grasp z + offset (per-class 보정 분리)

초기 구현에서 push z를 그냥 `target.base_xyz.z`로 두었으나, grasp z는
`base_z + per_class_z_offset` (예: cashew=-2mm)이 적용되어 있어 둘이
어긋남. 사용자 의도 ("grasp보다 살짝 위에서 밀기")를 반영해:

```
push_z = base_z + per_class_z_offset_mm + cluster_push_z_offset_mm
```

`task_manager_node`에서 두 보정을 합쳐 `cluster_policy`에 전달. 결과적으로
**클래스별 grasp 깊이를 그대로 존중하면서 push만 일률적으로 +N mm 띄움**.
`cluster_push_z_offset_mm = 2.0`이 yaml 기본.

---

## 3. 데이터 흐름

```
[Detection 사이클 한 반복 안에서]

  detect_once → DetectedObjectArray
      │
      ▼
  choose_target(class) → candidate (1개 너트)
      │
      ▼
  ┌──────────────────────────────────────────────────────┐
  │ cluster check                                        │
  │                                                      │
  │  if cluster_enabled                                  │
  │     and counts[class] < max_pushes:                  │
  │     plan = choose_cluster_plan(                      │
  │         detections, target=candidate, workspace,     │
  │         dist_threshold, candidate_offset,            │
  │         push_scale,                                  │
  │         push_z_offset = per_class + cluster_push_z   │
  │     )                                                │
  │     if plan is not None:                             │
  │         counts[class] += 1                           │
  │         _send_cluster_push_goal(plan)                │
  │         continue → 사이클 처음으로                   │
  └──────────────────────────────────────────────────────┘
      │
      ▼
  일반 _send_pick_goal(class, candidate, ...)
```

`continue` 키워드가 핵심. push가 발생하면 detect→select→pick 루프의 그
반복은 거기서 끝나고 다음 반복이 시작된다. 다음 반복은 새 detect_once를
호출하므로 분산된 새 장면이 관측된다.

---

## 4. cluster_policy 알고리즘

`choose_cluster_plan(...)` (`cluster_policy.py:42-102`).

### Step 1 — 유효 detection 필터 (target 자신 제외)

```python
valid = []
for d in detections:
    if d is target: continue
    if not d.transform_valid: continue
    if d.confidence < conf_gate: continue
    if d.base_xyz.z <= min_depth_mm: continue
    if not workspace.contains(d.base_xyz): continue
    valid.append(d)
```

`target_selector`와 같은 게이트를 적용. push 후보 평가에서 무효 검출이
영향을 못 주도록 함.

### Step 2 — 최근접 이웃 탐색

```python
neighbor = None
best_d2 = inf
for d in valid:
    d2 = (d.x-tx)**2 + (d.y-ty)**2
    if d2 < best_d2:
        best_d2, neighbor = d2, d
```

xy 평면 거리만 사용. 픽킹 너트는 모두 비슷한 z에 있으므로 z 거리는
의미 없음.

### Step 3 — 군집 판정

```python
dist = hypot(nx-tx, ny-ty)
if dist >= cluster_dist_threshold_mm or dist < 1e-6:
    return None
```

- `dist >= threshold`: 이웃이 멀어 군집 아님 → 일반 pick
- `dist < 1e-6`: 같은 너트가 두 번 검출된 dedup miss → push해도 의미 없음

### Step 4 — 수직축 산출

target→neighbor 직선의 단위 perpendicular vector:

```
T-N 방향 단위벡터:  (nx-tx, ny-ty) / dist
수직 단위벡터    :  (-(ny-ty), (nx-tx)) / dist
```

설계 문서 05에서 "두 BBox가 겹쳐서 생긴 변을 확장한 축"이라고 부르는 그
축. 수직 방향으로 진입해야 push 방향이 이웃 OBB와 수직이 되어 **target만
한쪽으로 밀어낼** 수 있음.

### Step 5 — 두 후보 진입점

```python
ax = -(ny-ty) / dist
ay =  (nx-tx) / dist
cand_a = (tx + ax * candidate_offset_mm, ty + ay * candidate_offset_mm)
cand_b = (tx - ax * candidate_offset_mm, ty - ay * candidate_offset_mm)
```

target에서 수직축으로 ±candidate_offset_mm 떨어진 두 점.

### Step 6 — 선정 우선순위

```python
blocked_a = _point_hits_other_box(cand_a, valid, ignore=(target,))
blocked_b = _point_hits_other_box(cand_b, valid, ignore=(target,))

if not blocked_a and blocked_b: return cand_a
if blocked_a and not blocked_b: return cand_b
if not blocked_a and not blocked_b:
    return cand_a if cand_a.y >= cand_b.y else cand_b
return None  # 둘 다 막힘 — push 포기, 일반 pick으로 fallback
```

설계 문서 §3.3의 우선순위 (1: BBox 비충돌, 2: y 큰 쪽)에 정확히 대응.

`_point_hits_other_box`는 `_point_in_oriented_box`로 각 다른 너트의 OBB
내부에 진입점이 있는지 검사. OBB는 (cx, cy, long_axis, short_axis, yaw)
로 정의되며, 점을 yaw로 회전한 local frame에서 `[-long/2, +long/2] ×
[-short/2, +short/2]` 안에 있는지 확인.

### Step 7 — 푸시 종점

```python
push_dx = chosen.x - target.x      # Δx
push_dy = chosen.y - target.y      # Δy
push_end = (target.x - push_scale * push_dx,
            target.y - push_scale * push_dy)
```

설계 문서 §3.4의 "이동량 = (-1.5 × Δx, -1.5 × Δy)"에 대응.
`push_scale = 1.5` (yaml 기본)에서 진입 변화량의 1.5배만큼 반대 방향으로.

### Step 8 — workspace 재확인

진입점, 푸시 종점 둘 다 z 보정 적용 후 워크스페이스 안에 있어야 함.
`tz`는 step 시작 시 `target.base_xyz.z + push_z_offset_mm`로 계산된
값 사용:

```python
if not workspace.contains(chosen.x, chosen.y, tz): return None
if not workspace.contains(end_x, end_y, tz): return None
```

밖이면 push 자체를 포기하고 None 반환 → task_manager는 일반 pick으로
fallback.

### Step 9 — ClusterPlan 반환

```python
return ClusterPlan(
    target=target, neighbor=neighbor,
    entry_xyz_mm=(chosen.x, chosen.y, tz),
    push_end_xyz_mm=(end_x, end_y, tz),
    neighbor_distance_mm=dist,
)
```

---

## 5. task_manager_node 디스패치

### 5.1 파라미터 (`task_manager_node.py:103-108`)

```python
self.declare_parameter("cluster_enabled", True)
self.declare_parameter("cluster_dist_threshold_mm", 35.0)
self.declare_parameter("cluster_candidate_offset_mm", 10.0)
self.declare_parameter("cluster_push_scale", 1.5)
self.declare_parameter("cluster_push_z_offset_mm", 2.0)
self.declare_parameter("max_cluster_pushes_per_class", 2)
```

### 5.2 사이클 시작 시 카운터 리셋 (`_run`)

```python
self._cluster_push_counts: Dict[str, int] = {}
```

새 주문이 들어올 때마다 0으로. 이전 사이클에서 cap에 걸렸던 클래스가
새 사이클에서는 다시 처음부터 push 가능.

### 5.3 cluster check 위치 (`_process_order_book`, PICK_AND_PLACE 직전)

```python
if (self._cluster_enabled
    and self._cluster_push_counts.get(target_class, 0)
        < self._max_cluster_pushes_per_class):
    push_z_total = (self._per_class_z_offset_mm.get(target_class, 0.0)
                    + self._cluster_push_z_offset_mm)
    plan = choose_cluster_plan(
        objects_msg.objects, candidate, self._workspace,
        cluster_dist_threshold_mm=...,
        candidate_offset_mm=...,
        push_scale=...,
        push_z_offset_mm=push_z_total,
        conf_gate=..., min_depth_mm=...,
    )
    if plan is not None:
        self._cluster_push_counts[target_class] += 1
        self._set_state(TaskState.CLUSTER_PUSH, ...)
        push_result = self._send_cluster_push_goal(plan)
        if push_result is None: ABORT
        if not push_result.success:    # motion fail → fallthrough
            log.warn(...)
        else:                          # 성공 → settle → 재관측
            time.sleep(self._inter_pick_delay_sec)
            continue
```

핵심:
- **카운터 cap이 cluster check 전체를 게이팅**. cap 초과 시 cluster_policy
  도 안 부르고 곧장 일반 pick으로.
- 실패 분기 두 단계:
  - `push_result is None` → 액션 서버 미가용/타임아웃 등 인프라 실패 →
    ABORT (verification으로도 회복 불가능한 상태로 간주).
  - `push_result.success == False` → motion 실패 (workspace, cancel 등) →
    fallthrough해 일반 pick 시도. 카운터는 이미 ++됐으므로 같은 target에
    push가 무한 반복되지는 않음.

### 5.4 `_send_cluster_push_goal(plan)` 헬퍼

```python
goal = PickAndPlace.Goal()
goal.target_class = CLUSTER_PUSH_TARGET_CLASS
goal.grasp_xyz = plan.entry_xyz_mm
goal.grasp_yaw = atan2(end_y - entry_y, end_x - entry_x)  # push 방향
goal.pre_grasp_width_mm = 0.0
goal.return_xyz = plan.push_end_xyz_mm
goal.return_zyz_deg = self._return_zyz_deg  # 사용 안 되지만 필드 채움
```

`grasp_yaw`를 `entry → push_end` 방향 atan2로 계산. push 동안 닫힌
그리퍼 손가락이 그 방향과 정렬되어 이웃과의 충돌 가능성을 줄임.

`pre_grasp_width_mm = 0`이라 액션 서버는 pre-position 단계를 건너뛰고,
push의 close 단계에서 직접 `gripper.close()` 호출.

---

## 6. robot_control_node 분기

`_execute_pick_and_place`에서 sentinel 검사
(`robot_control_node.py:312-340`):

```python
if goal.target_class == CLUSTER_PUSH_TARGET_CLASS:
    success, code, message = execute_closed_gripper_push(
        motion=self._motion, gripper=self._gripper, cfg=self._cfg,
        entry_xyz_mm=[goal.grasp_xyz.x, goal.grasp_xyz.y, goal.grasp_xyz.z],
        push_end_xyz_mm=[goal.return_xyz.x, goal.return_xyz.y, goal.return_xyz.z],
        push_yaw_rad=float(goal.grasp_yaw),
        feedback_cb=feedback_cb, is_cancelled=is_cancelled,
    )
else:
    success, code, message = execute_pick_and_place(...)  # 기존 로직
```

`place_ready` 토픽은 push 동안 변경되지 않음 (push 시작 시 False만 한 번
세팅; push가 끝나도 True를 set하지 않음 — 컨베이어가 작동할 일이 없으므로).

### `execute_closed_gripper_push` stage 시퀀스

`motion_sequence.py:273-360`. 7단계:

1. **`close_gripper`** — `gripper.close()` + settle 대기
2. **`approach`** — entry 위 `approach_offset_z_mm` 지점 (line move)
3. **`descend`** — entry z (slow speed)
4. **`push`** — push_end로 직선 (slow speed; 빠르면 너트 튕김)
5. **`retreat`** — push_end 위 approach 높이
6. **`home`** — joint move
7. **(마무리)** `gripper.open()` — 다음 사이클 첫 단계가 의외의 큰 width
   이동을 시작하지 않게 그리퍼 상태 정상화

failure_code는 `execute_pick_and_place`와 동일 매핑 (3=motion, 4=cancel,
5=workspace). grasp 관련 코드(1=approach_fail, 2=grasp_not_detected)는
push에 적용되지 않음 (open 그리퍼와 grip 검증이 없는 흐름).

---

## 7. 단위 검증

`cluster_policy.choose_cluster_plan`을 합성 detection으로 직접 호출 (실기 전):

| 케이스 | 입력 | 결과 |
|---|---|---|
| 1. 군집 (dist=5mm) | target (400,0), neighbor (400,5), 다른 너트 멀리 | plan 반환, entry는 BBox-clear & y 큰 쪽 |
| 2. 비군집 (dist >> threshold) | target (400,0), neighbor (500,100) | None |
| 3. BBox 차단 | 케이스 1 + 한쪽 후보 좌표에 다른 너트 OBB 배치 | 반대쪽 후보 자동 선정 |

세 케이스 모두 의도대로 동작 확인. 테스트 코드는 별도 파일로 커밋하지
않고 conversation log에만 기록 (간단한 dataclass mock으로 합성 가능한
함수형 모듈이라 별도 테스트 인프라가 비용 대비 가치 낮음).

---

## 8. 실기 튜닝 기록

세션 중 yaml 값을 다음 순서로 조정:

| 순번 | dist_threshold_mm | candidate_offset_mm | 비고 |
|---|---|---|---|
| 초기 | 35.0 | 10.0 | 첫 구현 |
| 1차 | 3.0 | 20.0 | 거의 발동 안 됨 (너트 중심 거리 ≥ 12mm) |
| 2차 | 25.0 | 15.0 | 정상 발동 시작 |
| 3차 | 25.0 | 25.0 | 진입점이 너트 OBB 안에 자주 들어가는 문제 → offset 키워 회피 |
| **최종** | **30.0** | **25.0** | 닿아 있는 두 번째 너트 페어 일부가 25mm 직전에 머물러 미발동 → 5mm 상향 |

추가로 push 동작 검증 중 "push z가 grasp z와 어긋나 보임"이 보고돼,
`cluster_push_z_offset_mm = 2.0` 신설 + per-class offset과 합쳐 전달하는
구조로 변경 (§2.3 참조).

**최종 실기 결과**: 군집 너트 정상 분산 + 재관측 → 정상 픽까지 사이클 성공.

---

## 9. 빌드/배포 메모

- 새 모듈 `cluster_policy.py`는 entry point 아님 → `setup.py`/`egg-info`
  갱신 불필요.
- `cobot_robot_control` install이 egg-link이고 build dir은 src 심링크 →
  src 수정이 즉시 install로 흐름.
- `cobot_task_manager`는 install이 site-packages **사본** → src→install
  수동 cp 필요.

따라서 **colcon build 없이 src 편집 + (task_manager 한정) install
동기화 + 노드 재시작**만으로 적용 가능. 본 세션은 cp만 사용.

> **주의**: yaml 변경 시 src와 install 둘 다 동기 상태인지 확인할 것.
> 세션 중 한 번 install이 stale 상태로 남아 임계값이 의도와 다르게
> 동작했던 사례 있음 (자세한 내용은 `docs/changelog/2026-05-09_165153.md`
> §6.1 참조).

---

## 10. 한계 / 향후 과제

설계 문서 05의 "추후 검토 사항" 중 미해결 항목:

### 10.1 push 후에도 군집이 유지되는 케이스

`max_cluster_pushes_per_class = 2`로 잠정 cap. push가 부족하게 미는 경우
(너트 표면이 매끄러워 손가락이 미끄러져 displacement가 작음), 같은 target
에 두 번 push 후 일반 pick으로 fallback. fallback 픽이 또 실패하면
verification 라운드에서 재시도. 실기에서 충분한지 추가 관찰 필요.

### 10.2 두 후보 좌표 모두 BBox 안인 경우

현재 구현: `choose_cluster_plan`이 None 반환 → `_process_order_book`이
일반 pick으로 fallthrough. 이 경우 그리퍼가 인접 너트와 충돌할 가능성이
높지만, 현재 fallback 외 옵션 없음. 향후 후보 offset을 동적으로 키우거나
3개 이상 후보를 고려하는 방안 검토.

### 10.3 임계값 metric 재검토

현재 `cluster_dist_threshold_mm`은 **중심 간 거리**. 너트 크기가 클래스별로
다르므로(walnut > almond > cashew), 같은 임계값이 모든 클래스에 적절하지
않을 수 있음. "OBB 간 gap" 또는 "long_axis 평균 + 마진" 같은 클래스-적응형
metric으로 바꾸는 것 검토.

### 10.4 verification 라운드의 cap 누적

`_cluster_push_counts`는 사이클 시작 시 한 번만 리셋. primary에서 cap에
걸린 클래스는 verification 라운드에서도 cap 그대로 유지된다. verification
을 새 사이클로 셀지 (즉 카운트 리셋), 같은 사이클로 둘지 (현재 동작) 정책
결정 필요.

---

## 11. 참고 코드 위치

| 파일 | 함수/라인 | 내용 |
|---|---|---|
| `cluster_policy.py` | 전체 (196 lines) | 군집 판정 + 후보 좌표 + 우선순위 + workspace 검사 |
| `task_manager_node.py:103-108` | declare params | yaml 파라미터 6종 선언 |
| `task_manager_node.py:528-560` | cluster check | `_process_order_book` 내 분기 |
| `task_manager_node.py:441-501` | `_send_cluster_push_goal` | sentinel goal 송출 |
| `task_state.py` | `CLUSTER_PUSH` | 상태 enum |
| `motion_sequence.py:273-360` | `execute_closed_gripper_push` | 7단계 모션 |
| `robot_control_node.py:40-50` | `CLUSTER_PUSH_TARGET_CLASS` | sentinel 상수 |
| `robot_control_node.py:312-340` | `_execute_pick_and_place` 내 분기 | sentinel 분기 |

## 12. 관련 문서

- `docs/05_clustered_nuts_handling.md` — 설계 명세 (이 보고서의 spec source)
- `docs/changelog/2026-05-09_165153.md` — 라이브 일지 + 튜닝 / 디버그 기록
- `docs/06_perception_trigger_redesign.md` — 이 메커니즘이 의존하는 detect_once의 결정성
- `docs/07_verification_and_correction_loop.md` — push 실패 시 부족분 보충에 들어가는 다음 단계
