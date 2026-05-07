# 정리 삭제 제안서

> **이 문서는 어떠한 삭제도 수행하지 않는다.** 이는 제안서이며, 아래의 모든
> 명령은 텍스트로만 제시되고 이 문서에 의해 실행되지 않는다.
> `_archive_cleanup/20260508/cleanup_manifest.md`와 함께 읽어야 한다.

이 제안서는 의도적으로 보수적이다. 애매한 파일은 삭제하지 않고 아카이브
상태로 유지하며, 이전 정리 규칙에서 제외했던 항목들(ROS 패키지 디렉터리,
config 파일, 캘리브레이션 파일)은 참조 검색 결과가 0건이더라도 그대로
둔다. 그 근거는 복원은 비용이 적지만, 누군가 조용히 의존하던 파일을
잃는 비용은 크기 때문이다.

---

## 1. 안전하게 아카이브된 파일/폴더 (이미 이동됨)

다음 6개 파일은 2026-05-08에 `git mv`로 `_archive_cleanup/20260508/`로
이동되었다. 활성 트리에는 더 이상 존재하지 않으나 아카이브 내에서는
여전히 버전 관리된다. 이동 후 mock dry-run은 8/8 픽 성공으로
`[state] done`에 도달했으므로, 이 파일들 중 어느 것도 핵심 의존성이
아니었다.

| 원본 경로 | 아카이브 경로 |
|---|---|
| `cobot_voice/scripts/publish_robot_session_scenarios.py` | `_archive_cleanup/20260508/cobot_voice/scripts/publish_robot_session_scenarios.py` |
| `web_stt_firebase/STEPS2WEBinLOCAL.md` | `_archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md` |
| `experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` |
| `experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` |
| `experiments/cobot_OD_obb_small/train_log.txt` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt` |
| `experiments/cobot_OD_obb_small/tune_log.txt` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt` |

---

## 2. 추후 영구 삭제 가능성이 높은 파일/폴더

세 가지 신뢰도 계층으로 나눈다. 계층이 높을수록 삭제 시 더 안전하다.

### Tier A — 이미 아카이브됨, 추후 삭제가 안전함

대기 기간(§6) 이후 높은 신뢰도로 제거 가능하다. `cobot_*/`,
`conveyor_controller/`, `scripts/`, `web_stt_firebase/`,
`docs/01..04` 전반에서 참조 히트가 **0건**이었고(이전 검증 보고서 §1 참조)
dry-run에서도 필요하지 않았다.

- `_archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt`

### Tier B — 아직 아카이브되지 않음, 소유자 승인 후 제거 안전

규칙 1–4에 의해 아카이브 이동에서 제외되었으나 검증 보고서가
미사용으로 확정한 항목들이다. 각 항목은 한 줄 짜리 소유자 승인이
필요하며 그 후 삭제 가능하다.

- `cobot_voice/cobot_voice/voice_processing_node.py` — legacy ROS 노드.
  해당 노드의 `/voice/text` / `/voice/status` 토픽을 구독하는 트리 내
  구독자가 없다. 운영 음성 경로(`scripts/voice_to_robot.py` →
  `voice_order_flow` → `task_manager_dispatcher`)는 ROS 토픽을 완전히
  우회한다. 이 파일을 제거할 경우 `cobot_voice/setup.py`의 26행
  (`voice_processing = …` `console_scripts` 항목)도 함께 제거해야 한다.
- `cobot_voice/keyword_extraction.py` (최상위 shim, 18행) —
  `scripts/voice_to_robot.py --text "..."`로 대체됨.
- `cobot_voice/voice_order_flow.py` (최상위 5행 shim) — *이미 대체된*
  문서에서만 참조됨. 기능적으로 `python3 -m cobot_voice.voice_order_flow`와
  동일.
- `cobot_config/config/handeye.yaml` — 참조용 값일 뿐. 런타임 바인딩은
  `cobot_perception/config/perception.yaml`의 `gripper2camera_npy`이다.
- `cobot_config/config/workspace.yaml` — 참조용 값일 뿐. 런타임 경계값은
  `task_manager.yaml`과 `robot_control.yaml`에 존재.
- `cobot_config/config/slot_poses.yaml` — 미구현된 `cobot_policy`
  패키지의 입력값.
- `cobot_config/config/policy_config.yaml` — 위와 동일.
- `cobot_config/config/object_aliases.yaml` — 런타임 alias 맵은
  `cobot_voice/cobot_voice/object_aliases.py`의 Python dict이다.

### Tier C — 제거 전 로드맵 결정 필요

유지되었으나 비어 있는 placeholder들이다. 구현하거나 제거해야 한다.
"스텁으로 유지"는 두 세계의 최악의 결합이며, 새로운 독자가 이를 실제
패키지로 오해할 수 있다.

- `cobot_safety/` (전체 패키지 — 0바이트 모듈 파일들) — 현재
  `cobot_safety/setup.py`에 `safety_manager` 엔트리 포인트가 선언되어
  있어 launch 시 크래시가 발생한다.
  `cobot_bringup/launch/host_system.launch.py:3`에 향후 단계의
  placeholder로 언급되어 있다.
- `cobot_policy/` (전체 패키지 — 0바이트 모듈 파일들) — 위와 동일.
- `nuts_data_recording/` (전체 패키지) — 캘리브레이션 데이터 기록 도구.
  빌드는 되나, 활성 launch나 문서에서 참조되지 않음. 팀이 재캘리브레이션을
  계획한다면 유지하고, 그렇지 않다면 제거.
- `cobot_bringup/config/params.yaml` — 권장 해결책은 이를
  **`cobot_bringup/launch/full_system.launch.py`에 연결하여**
  `ROS_DOMAIN_ID`와 `RMW_IMPLEMENTATION`이 실제로 적용되도록 하는 것이다.
  팀이 셸에서 설정하는 값을 선호한다면 삭제.
- `experiments/cobot_OD_obb_small/` (전체 대안 모델 실행. 단,
  `.gitignore`에 allow-list된 `weights/best.pt`는 제외) — 운영 모델은
  *nano* 변형이다. "small" 변형은 보존된 대안이며, 의도적으로 유지되는지
  확인할 것.
- `experiments/cobot_OD_obb_*/train_phase1_2026*/` — 페이즈 1 학습
  결과물로, 페이즈 2로 대체되었다. 각 디렉터리에는 `args.yaml`과
  `results.csv`만 존재한다(추가로 gitignore된 캐시/가중치). 순수 이력.

### Tier D — 범위 외, `rm`이 아닌 `git rm --cached`로 처리

이전 `.gitignore` 단계에서 식별된, 추적 중이지만 `.gitignore`에 매칭되는
Firebase 도구 캐시들이다. 이들은 인덱스에서 **추적 해제**해야 하지만
firebase-tools가 재생성하므로 디스크에는 **유지**해야 한다.

- `web_stt_firebase/.firebase/.graphqlrc`
- `web_stt_firebase/.firebase/INSTRUCTIONS.md`
- `web_stt_firebase/dataconnect/.dataconnect/schema/prelude.gql`

### Tier E — 재빌드 산출물 (git 외 삭제)

`install/cobot_voice/lib/cobot_voice/`의 오래된 `command_parser` 및
`firebase_state_bridge` 런처 스크립트는 통합 정리 이전 빌드의
install-tree 잔존물이다. 이들은 `cobot_voice/setup.py`에 포함되어 있지
않다. 정리 방법은 다음과 같다.

```bash
# Run NOTHING from this proposal automatically.
rm -rf build/ install/ log/
colcon build --symlink-install
```

이는 git 작업이 아닌 로컬 디스크 정돈이다.

---

## 3. 당분간 아카이브 상태로 유지해야 하는 파일/폴더

대기 기간 이후에도, 다음 아카이브된 파일들은 런타임 사용을 넘어선
하위 가치가 있으므로 즉시 삭제하지 말고 `_archive_cleanup/20260508/`에
유지하는 것이 바람직하다.

- `_archive_cleanup/20260508/cobot_voice/scripts/publish_robot_session_scenarios.py`
  — `robot_session/current` 스냅샷을 Firestore에 수동으로 푸시하는
  유일하게 알려진 도구. 로봇 없이 웹 UI를 시연할 때 유용하다.
  아카이브 유지하고, 시연을 재개하면 `cobot_voice/scripts/`로 다시
  승격할 것.

나머지 아카이브 파일들(conf_sweep CSV, train/tune 로그, 로컬 설정 메모)은
대기 기간이 지나면 위 Tier A에 따라 "아카이브됨"에서 "삭제됨"으로 전환
가능하다. 단, 아카이브의 이력 감사가 쉽도록 **piecemeal이 아닌 batch
단위로만** 처리해야 한다.

---

## 4. 복원되거나 제외된 파일/폴더

**아카이브에서 복원됨: 없음.** mock dry-run은 8개 픽 모두 성공하여
`[state] done`에 도달했으며, 이는 어떤 아카이브 파일도 필요하지 않았음을
확인한다.

**이 제안서에서 제외됨 (즉, 이동되지도, 삭제 후보로 제안되지도 않음):**

- 이전 검증 보고서 §3의 모든 항목
  (`cobot_voice/voice_processing_node.py`, 패키지 내 shim들,
  `nuts_data_recording/`, `cobot_safety/`, `cobot_policy/`, 7개의
  `cobot_config/*.yaml` 파일, `cobot_bringup/config/params.yaml`,
  `experiments/cobot_OD_obb_small/`, `train_phase1_*` 디렉터리,
  legacy `docs/*.md` 파일, Firebase 도구 캐시).
- 이전 검증 보고서 §2의 모든 "반드시 유지" 항목
  (활성 소스 코드, launch 파일에 연결된 ROS 패키지 디렉터리,
  `cobot_msgs/{msg,srv,action}/*`, 운영 모델 가중치, 4개의 정식
  `docs/0[1-4]_*.md` 파일, `cobot_voice/resource/{.env.example,
  hello_rokey_8332_32.tflite}`, `secrets_4_firebase_config/`,
  `web_stt_firebase/{src,public,…}` 소스 트리, 공유 단일 진실 소스인
  `pick_offsets.yaml` 등).

legacy 문서인 `docs/{run_manual.md, voice_to_robot_integration_plan.md,
three_firebase_bridge_*.md, nut_recommendation_*.md,
stt_db_tts_robot_integration.md}`는 `docs/01_system_architecture.md`
내부에 대체되었다고 명시되어 있다. 권장 경로는 삭제가 아닌
**`docs/_archive/`로의 이전**이다. 동일한 보수적 근거에 따른다. 이
문서들은 프로젝트의 설계 이력을 추적한다.

---

## 5. 리스크

| 리스크 | 영향 항목 | 완화책 |
|---|---|---|
| ML 재현성 손실 | Tier A `conf_sweep_*.csv`, `train_log.txt`, `tune_log.txt` | 이들은 운영 `best.pt`의 생성 과정을 문서화한다. 삭제되면 "데이터 → 하이퍼파라미터 → 모델"의 사슬이 더 이상 감사 가능하지 않다. **완화책**: 어떠한 `rm` 이전에 저장소 외부(S3, 내부 Drive)에 사본을 아카이브한다. |
| 시연 기능 손실 | `publish_robot_session_scenarios.py` | 웹 시연을 위한 유일하게 알려진 수동 주입 도구이다. **완화책**: 무기한 아카이브 유지(§3 참조). |
| 캘리브레이션 회귀 | Tier B `cobot_config/handeye.yaml` | 어떤 런타임 로더도 이를 읽지 않지만, 팀의 참조 심도 오프셋을 문서화한다. **완화책**: 삭제 전에 그 내용을 `docs/01_system_architecture.md`에 캘리브레이션 이력 노트로 복사한다. |
| 빈 패키지 재생성 비용 | Tier C `cobot_safety/`, `cobot_policy/` | 팀이 향후 구현하기로 결정한다면 `package.xml` + `setup.py` 골격 재생성에 패키지당 약 15분이 들지만, (이미 launch 주석에 사용된) 네임스페이스를 다시 가져와야 한다. **완화책**: 제거 전에 의도된 범위를 로드맵 문서에 기록한다. |
| 캘리브레이션 도구 재생성 | Tier C `nuts_data_recording/` | DSR_ROBOT2 컨벤션에 묶인 커스텀 도구. 처음부터 재구현하는 것은 단순하지 않다. **완화책**: 캘리브레이션 소유자에게 향후 어떠한 재캘리브레이션도 이를 사용하지 않을 것임을 확인받는다. |
| 발견 혼동 | Tier D Firebase 캐시 | `git rm --cached`가 실행되었지만 `.gitignore`가 아직 적용되지 않은 경우, 다음 `git add`가 이들을 다시 추적하게 된다. **완화책**: `git rm --cached` 실행 전에 이전 단계에서의 새 `.gitignore` 규칙이 커밋되었는지 확인한다. |
| legacy 문서를 통한 숨겨진 의존성 | `docs/`의 7개 legacy 문서 | 오래된 지침이 포함되어 있다. 팀원이 이를 읽고 단계를 따른다면 폐기된 `~/cobot_ws/` 경로와 `--z-override 315` 캘리브레이션 값이 그들을 오도할 것이다. **완화책**: 즉시 삭제보다는 `docs/_archive/`로의 이전을 선호하며, 각 아카이브 파일 상단에 새 문서를 가리키는 배너를 둔다. |
| 모델 대안 손실 | Tier C `experiments/cobot_OD_obb_small/` | small 모델 변형을 제거하면 nano 모델이 회귀할 경우 팀의 fallback이 사라진다. **완화책**: `weights/best.pt`(이미 gitignore allow-list)를 디스크에 유지하고, 운영에서 30일 이상 안정적인 nano 모델 릴리스 이후에만 `args.yaml`/`results.csv`/등을 아카이브한다. |
| 오래된 install-tree 산출물 | Tier E `install/cobot_voice/lib/cobot_voice/{command_parser, firebase_state_bridge}` | 이들은 로컬 디스크 전용이며 git이 아니다. **완화책**: 없음 — `rm -rf build/ install/ log/`는 비파괴적이며 재빌드로 복구 가능하다. |

---

## 6. 권장 삭제 전 대기 기간

> **모든 Tier A 항목의 가장 빠른 삭제일: 2026-06-07 (아카이브 후 30일).**

아래 일정은 각 계층을 단순한 달력 날짜가 아닌 게이트와 함께 짝지운다.
양쪽이 모두 충족되어야 한다.

| Tier | 달력 게이트 | 검증 게이트 |
|---|---|---|
| A — 이미 아카이브됨 | **30일** (2026-06-07) | 2026-05-08 이후, 4개 `docs/0[1-4]` 문서를 유일한 운영자 참조로 사용한 **실제 하드웨어** 시연 실행이 최소 1회 완료되었음. 아카이브 파일 복원 요청 없음. |
| B — 미사용 확정, 활성 트리에 존재 | **60일** (2026-07-07) | 커밋 메시지에 소유자 승인이 기록됨. 각 batch 이후 빌드 + dry-run + frontend 빌드 재검증. |
| C — 로드맵 결정 필요 | **고정 날짜 없음** | 패키지 소유자가 결정 (`cobot_safety`/`cobot_policy`/`nuts_data_recording` → 유지보수자, `cobot_config/*.yaml` → 캘리브레이션 소유자, `experiments/cobot_OD_obb_small/` → ML 리드). 시간 경과만으로 삭제하지 말 것. |
| D — Firebase 도구 캐시 | `git rm --cached` (`rm`이 아님)는 **현재 안전**. `.gitignore`가 이미 이를 커버한다. | 이전 단계의 `.gitignore` 변경이 먼저 커밋되어 있어야 함. |
| E — 오래된 install-tree | `rm -rf build/ install/ log/`는 **현재 안전** (로컬 디스크 전용). | 없음 — `colcon build`로 가역적이다. |

**엄격한 규칙**: 삭제 시점에서 다음 사전 점검 중 어느 하나라도 실패하는
경우 *어떠한 항목도* 삭제하지 말 것.

1. `colcon build --symlink-install`이 깨끗하게 완료된다.
2. `docs/03_run_manual.md` §5.2의 mock dry-run이 `[state] done`에 도달한다.
3. `web_stt_firebase/`에서 `npm run build`가 성공한다.
4. 삭제 대상 각 경로에 대해 `grep -RnE "<basename>" cobot_*/ conveyor_controller/ scripts/ web_stt_firebase/src/ docs/0*.md`가 0건의 히트를 반환한다.

이 중 하나라도 실패하면 중단하고 재평가한다.

---

## 7. 정확한 삭제 명령어 (이 문서에서 **실행하지 말 것**)

다음은 각 게이트가 충족되었을 때 사용할 셸 명령어 그 자체이다.
참조용으로 제시되며, 이 제안서가 **실행해서는 안 된다**.

### Tier A — 2026-06-07 이후, §6의 모든 조건이 충족된 후

```bash
# Operate from workspace root
cd ~/cobot2_ws

# Re-verify before deletion
colcon build --symlink-install
ros2 launch cobot_robot_control robot_control.launch.py &  # one terminal
ros2 run  cobot_perception mock_perception_node            &  # another
ros2 run  cobot_task_manager task_manager_node             &  # another
# Watch for [state] done in the task_manager terminal, then ^C all three

# Tier A deletions
git rm  _archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt

# Suggested commit
git commit -m "Tier A archive deletion: drop unused training logs and the local-setup memo"
```

`publish_robot_session_scenarios.py`는 이 목록에 **포함되지 않는다**.
§3에 따라 아카이브 상태를 유지한다.

### Tier B — 소유자 승인 후

```bash
# Voice-processing legacy node (also remove the entry-point line from setup.py)
git rm cobot_voice/cobot_voice/voice_processing_node.py
# Then manually edit cobot_voice/setup.py and delete the line:
#   'voice_processing = cobot_voice.voice_processing_node:main',

# Top-level shims
git rm cobot_voice/keyword_extraction.py
git rm cobot_voice/voice_order_flow.py

# Unused cobot_config YAMLs
git rm cobot_config/config/handeye.yaml
git rm cobot_config/config/workspace.yaml
git rm cobot_config/config/slot_poses.yaml
git rm cobot_config/config/policy_config.yaml
git rm cobot_config/config/object_aliases.yaml

# Re-verify after each batch
colcon build --symlink-install
# Repeat the dry-run from Tier A.

git commit -m "Tier B: remove confirmed-unused legacy modules and reference YAMLs"
```

### Tier C — 명시적 로드맵 결정 후에만

```bash
# Empty stub packages — only if the roadmap drops them
git rm -r cobot_safety/
git rm -r cobot_policy/

# Calibration tool — only after calibration-owner approval
git rm -r nuts_data_recording/

# bringup params.yaml — preferred path is to wire it in instead of removing
git rm cobot_bringup/config/params.yaml

# Alternative model variant — only after sustained nano-model stability
git rm -r experiments/cobot_OD_obb_small/

# Phase-1 training artifacts (both variants)
git rm -r experiments/cobot_OD_obb_nano/train_phase1_20260504_173049/
git rm -r experiments/cobot_OD_obb_small/train_phase1_20260505_203819/

git commit -m "Tier C: remove roadmap-resolved stubs and superseded experiment runs"
```

### Tier D — Firebase 도구 캐시 (추적 해제, 디스크에서 삭제하지 않음)

```bash
# Pre-condition: the .gitignore additions from the previous step must be committed.
git rm --cached web_stt_firebase/.firebase/.graphqlrc
git rm --cached web_stt_firebase/.firebase/INSTRUCTIONS.md
git rm --cached web_stt_firebase/dataconnect/.dataconnect/schema/prelude.gql

git commit -m "Untrack Firebase tooling caches (regenerated by firebase-tools)"
```

### Tier E — 오래된 install-tree 산출물 (git 관여 없음)

```bash
# Local-disk hygiene only; no commit
rm -rf build/ install/ log/
colcon build --symlink-install
```

### legacy 문서 이전 (삭제 아님)

7개 legacy `docs/*.md` 파일을 삭제하기로 결정하기 전에 이전을 선호한다.

```bash
mkdir -p docs/_archive
git mv docs/run_manual.md                          docs/_archive/
git mv docs/voice_to_robot_integration_plan.md     docs/_archive/
git mv docs/three_firebase_bridge_changes.md       docs/_archive/
git mv docs/three_firebase_bridge_integration_test.md docs/_archive/
git mv docs/nut_recommendation_changes.md          docs/_archive/
git mv docs/nut_recommendation_flow.md             docs/_archive/
git mv docs/stt_db_tts_robot_integration.md       docs/_archive/

# Then update the "Document set" block in docs/01_system_architecture.md
# so the supersession note points at docs/_archive/.

git commit -m "Move superseded design docs to docs/_archive/"
```

---

## 한 단락 요약

6개 파일이 `git mv`로 `_archive_cleanup/20260508/`에 안전하게
아카이브되었다. 빌드, mock dry-run, frontend 빌드 모두 이들 없이
통과한다. **2026-06-07 이전에는 어떠한 파일도 영구 삭제되어서는 안
되며**, 그 이후에도 Tier A 항목에 한정한다. Tier B와 Tier C는 명시적
소유자 승인이 필요하다. Tier D (Firebase 도구 캐시)와 Tier E (오래된
install 산출물)는 가역적인 로컬 전용 또는 추적 해제 전용 작업이며,
이전 `.gitignore` 변경이 커밋되는 시점에 진행 가능하다.
`publish_robot_session_scenarios.py`는 무기한 아카이브 상태로 유지되어야
한다. 7개 legacy 문서는 삭제보다 `docs/_archive/`로 이전하는 것이
가장 좋다. 의심스러울 경우 파일을 아카이브된 채로 두라. 복원은
비용이 적지만, 우발적 손실은 그렇지 않다.
