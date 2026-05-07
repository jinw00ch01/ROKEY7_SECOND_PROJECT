# 정리 아카이브 — 2026-05-08

이 폴더는 2026-05-08에 활성 저장소 트리에서 **이동된**(삭제되지 않은) 파일들을
보관한다. 참조 검증 결과 사용되지 않는 것으로 확인되었으나, 이동은 보수적으로
수행되었다:

- 이동은 `git mv`로 수행되어 히스토리가 보존된다.
- 작업 트리 사본은 이 디렉터리 아래에 그대로 존재한다.
- 소스 코드, ROS 패키지 디렉터리, launch / config / msg / srv / action 파일,
  캘리브레이션 파일, 사용 중인 모델 가중치, 그리고 `docs/03_run_manual.md`나
  운영자 스크립트에서 참조하는 파일은 어느 것도 이동되지 않았다.

여기로 이동한 항목 중 필요한 것이 있으면 다음 명령으로 복원한다:

```bash
git mv _archive_cleanup/20260508/<archived-path> <original-path>
```

---

## 1. 이동된 파일 (6개)

### `cobot_voice/scripts/publish_robot_session_scenarios.py`

| 항목 | 값 |
|---|---|
| 원본 경로 | `cobot_voice/scripts/publish_robot_session_scenarios.py` |
| 아카이브 경로 | `_archive_cleanup/20260508/cobot_voice/scripts/publish_robot_session_scenarios.py` |
| 사유 | 데모 시나리오용 독립 실행형 Firestore 상태 주입기. 프로덕션 음성 루프의 일부가 아니다. |
| 근거 | (1) `cobot_voice/setup.py`의 `console_scripts`에 포함되어 있지 않다 (`voice_processing`, `voice_web_demo`, `web_voice_bridge_server`, `firebase_status_bridge`만 노출됨). (2) `cobot_*/`, `conveyor_controller/`, `scripts/`, `web_stt_firebase/src/`, `docs/0*.md` 전반에 걸쳐 `grep -RnE "publish_robot_session_scenarios"`를 실행해도 파일 자체 외에는 결과가 없다. (3) 다른 어떤 Python 모듈에서도 import하지 않는다. |
| 리스크 수준 | **낮음** |

### `web_stt_firebase/STEPS2WEBinLOCAL.md`

| 항목 | 값 |
|---|---|
| 원본 경로 | `web_stt_firebase/STEPS2WEBinLOCAL.md` |
| 아카이브 경로 | `_archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md` |
| 사유 | 554바이트 분량의 독립 로컬 셋업 메모. 웹 구동 절차는 이제 `docs/03_run_manual.md` §6.5에 존재한다. |
| 근거 | `grep -RnE "STEPS2WEBinLOCAL"`을 실행해도 파일 자체 외에는 결과가 없다. `web_stt_firebase/README.md`, `firebase.json`, `package.json`, 또는 `docs/01..04` 어디에서도 참조되지 않는다. |
| 리스크 수준 | **낮음** |

### `experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv`

| 항목 | 값 |
|---|---|
| 원본 경로 | `experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` |
| 아카이브 경로 | `_archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` |
| 사유 | YOLO 신뢰도 임계값 스윕 결과(CSV). 어떤 런타임 코드도 로드하지 않는 순수 과거 산출물이다. |
| 근거 | 모든 소스 디렉터리와 `docs/0*.md`에 대해 `grep -RnE "conf_sweep"`을 실행하면 0건의 결과를 반환한다. |
| 리스크 수준 | **낮음** |

### `experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv`

| 항목 | 값 |
|---|---|
| 원본 경로 | `experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` |
| 아카이브 경로 | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` |
| 사유 | nano 변형과 동일: YOLO 신뢰도 임계값 스윕 결과. |
| 근거 | 동일한 `grep`이 0건의 결과를 반환한다. 또한 "small" 모델은 어차피 프로덕션 모델이 아니다 (프로덕션은 `cobot_OD_obb_nano`의 `train_phase2_20260504_173049/weights/best.pt`이다). |
| 리스크 수준 | **낮음** |

### `experiments/cobot_OD_obb_small/train_log.txt`

| 항목 | 값 |
|---|---|
| 원본 경로 | `experiments/cobot_OD_obb_small/train_log.txt` |
| 아카이브 경로 | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt` |
| 사유 | 일회성 YOLO 학습 실행에서 나온 908 KB 분량의 stdout 로그. 순수 과거 산출물이다. |
| 근거 | 소스 디렉터리와 활성 문서 전반에 대해 `grep -RnE "train_log\.txt"`를 실행하면 0건의 결과를 반환한다. |
| 리스크 수준 | **낮음** |

### `experiments/cobot_OD_obb_small/tune_log.txt`

| 항목 | 값 |
|---|---|
| 원본 경로 | `experiments/cobot_OD_obb_small/tune_log.txt` |
| 아카이브 경로 | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt` |
| 사유 | `inference_tune.py` 실행에서 나온 40 KB 분량의 stdout 로그. |
| 근거 | `grep -RnE "tune_log\.txt"`를 실행하면 0건의 결과를 반환한다. |
| 리스크 수준 | **낮음** |

---

## 2. 명시적으로 이동하지 않은 파일 (규칙에 따라 보류)

다음 파일들은 이전 정리 보고서에서 "사용되지 않음 확정"으로 분류되었으나,
사용자가 제공한 규칙이 카테고리 단위로 이를 제외하기 때문에 **활성 트리에
유지되었다**. 이들은 명시적인 소유자 승인을 요구하는 후속 작업의 후보로
남는다.

| 경로 | 유지된 사유 |
|---|---|
| `cobot_config/config/handeye.yaml` | 규칙 3 (config 파일) 및 규칙 4 (캘리브레이션 파일). 어떤 런타임 로더도 읽지 않지만, 내용이 캘리브레이션 값이며 제거 시 문서화된 참조가 사라진다. |
| `cobot_config/config/workspace.yaml` | 규칙 3 (config 파일). |
| `cobot_config/config/slot_poses.yaml` | 규칙 3 (config 파일). |
| `cobot_config/config/policy_config.yaml` | 규칙 3 (config 파일). |
| `cobot_config/config/object_aliases.yaml` | 규칙 3 (config 파일). |
| `cobot_bringup/config/params.yaml` | 규칙 3 (config 파일). 현재 어떤 launch에서도 로드되지 않는다고 문서화되어 있다. 권고 사항은 아카이브가 아니라 연결하는 것이다. |
| `cobot_safety/` (패키지 전체) | 규칙 2 (ROS 패키지 디렉터리). 빈 스텁뿐이지만, 규칙에 따라 패키지 레이아웃은 보존된다. |
| `cobot_policy/` (패키지 전체) | 규칙 2 (ROS 패키지 디렉터리). |
| `nuts_data_recording/` (패키지 전체) | 규칙 2 (ROS 패키지 디렉터리). 캘리브레이션 도구 — 이동 전에 소유자 승인이 필요하다. |
| `cobot_voice/cobot_voice/voice_processing_node.py` 및 `voice_processing` 엔트리 포인트 | 규칙 1 (활성 소스 코드 — legacy로 문서화되어 있으나 `cobot_voice`의 일부로 빌드 및 설치된다). |
| `cobot_voice/keyword_extraction.py`, `cobot_voice/voice_order_flow.py` (최상위 shim) | 규칙 1 (패키지 내 소스). |
| `experiments/cobot_OD_obb_*/{analyze_dataset.py, inference_tune.py, merge_datasets.py, split_dataset.py, visualize_results.py, yolo_train.py}` | 재학습 유틸리티 — 그대로 두면 향후 재학습 세션을 이 아카이브에서 복원하지 않고도 experiments 디렉터리에서 실행할 수 있다. |
| `experiments/cobot_OD_obb_*/train_phase1_2026*/{args.yaml,results.csv}` | `args.yaml`은 config 파일과 유사하다 (규칙 3의 더 엄격한 해석); `results.csv`는 그것과 짝을 이룬다. Phase-1 학습은 phase-2로 대체되었으나 산출물은 함께 보관된다. |
| `experiments/cobot_OD_obb_*/{data.yaml, data_extra.yaml, dataset_stats.json, experiment_03.md, experiment_04.md}` | `data*.yaml`은 학습 데이터 매니페스트이다 (규칙 3의 광범위한 해석); `experiment_*.md` 파일은 루트 `.gitignore`(22번째 줄)에 명시적으로 이름이 들어가 있다. |
| `web_stt_firebase/.firebase/.graphqlrc`, `INSTRUCTIONS.md`, `web_stt_firebase/dataconnect/.dataconnect/schema/prelude.gql` | 이들은 이제 `.gitignore`에 매칭되지만 현재까지 인덱스에 남아 있다. 권장 조치는 (이전 `.gitignore` 업데이트 단계에 따라) `git rm --cached <path>`이다 — 아카이브가 아니라 untrack 처리되어야 한다. **여기서는 이동하지 않았다.** |
| Legacy `docs/{run_manual,voice_to_robot_integration_plan,three_firebase_bridge_*,nut_recommendation_*,stt_db_tts_robot_integration}.md` | 본 작업의 범위 밖이다 — 이들은 이미 표준 문서 루트로 확정한 `docs/` 아래에 위치하며, 제안된 `docs/_archive/` 마이그레이션은 별도로 계획된 단계이다. |

---

## 3. 비고

- 6건의 이동 모두 `git mv`를 사용했으므로, `git log --follow <archived path>`로
  파일의 이동 이전 전체 히스토리를 확인할 수 있다.
- 이번 이동으로 활성 트리에서 회수된 디스크 용량 합계: 약 960 KB
  (대부분 두 개의 로그 파일).
- 이 아카이브 디렉터리 자체는 `.gitignore`에 추가되어 있지 **않다** —
  의도된 것으로, 이동된 파일들이 새 위치에서 계속 버전 관리되도록 하기 위함이다.
- 후속 커밋에서 이들 중 일부를 완전히 삭제하기로 결정한다면 그것은 별개의
  작업이다. 이 디렉터리는 그때까지 트리에 그대로 남아 있을 것이다.
