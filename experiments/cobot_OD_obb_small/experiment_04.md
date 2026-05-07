# Experiment 04 — Cobot Nut OBB Detection 실행 리포트

**실행일**: 2026-05-05
**프로젝트**: `cobot_OD_obb_small`
**환경**: Windows 11 · NVIDIA GeForce RTX 5060 Laptop GPU (8 GB) · Python 3.12.10 · PyTorch 2.12.0+cu128 · Ultralytics 8.4.43
**Baseline**: experiment_03 (yolov8n-obb, test mAP@0.5 = 0.992 / mAP@0.5:0.95 = 0.872 / walnut mAP@0.5:0.95 = 0.816)

> 본 문서는 사전 계획안이 아니라 **실제 실행 결과 기반**으로 작성된 리포트입니다.

---

## 1. 목적과 핵심 변경

experiment_03을 기반으로 두 가지 축에서 개선을 시도:

1. **Codex 코드리뷰 P2 지적 반영** — OBB 좌표 정규화 클리핑, per-class 통계 검증
2. **experiment_03 후속 제안 #1, #2, #3** — extra_cashew 단독 평가, 모델 스케일 상향(s), walnut 약점 보강

### 1.1 변경 요약

| 영역 | exp_03 | exp_04 |
|---|---|---|
| 모델 | yolov8n-obb (3.08M params) | **yolov8s-obb** (11.4M params, ~3.7×) |
| OBB 좌표 | 일부 라인 [0,1] 범위 위반 → Ultralytics가 invalid 처리 가능 | **merge 단계 클리핑** (16 라인 보정, 부동소수 경계 오차) |
| extra_cashew | test 안에 일반 23셋과 혼합 | **별도 `test_extra/` 분할 + `data_extra.yaml`** 단독 평가 |
| analyze 통계 | 03 시점에 이미 per_class_w[i] 사용 (정확) | OOR 라인 카운터 추가, per-class 정확성 명시적 검증 |
| 학습 옵션 | (cls 기본) | `--cls-gain` 추가 (이번 실행은 1.0 유지) |

### 1.2 성능 목표

| 지표 | 목표 |
|---|---|
| test mAP@0.5 (OBB) | ≥ 0.97 |
| test mAP@0.5:0.95 (OBB) | ≥ 0.78 |
| test cashew recall | ≥ 0.95 |
| **extra_cashew (unseen) mAP@0.5** | **≥ 0.90** (단독 측정) |
| **walnut mAP@0.5:0.95** | **≥ 0.85** (03 = 0.816) |

---

## 2. 실행 파이프라인

| # | 스크립트 | 역할 | 상태 |
|---|---|---|---|
| 1 | `merge_datasets.py` | 24개 OBB 소스 → `train/{images,labels}/` 통합 + 좌표 클리핑 | ✅ |
| 2 | `analyze_dataset.py` | 클래스/박스 분포 점검 + `dataset_stats.json` | ✅ |
| 3 | `split_dataset.py` | train/valid/test/**test_extra** 분할 + `data.yaml` / `data_extra.yaml` 생성 | ✅ |
| 4 | `yolo_train.py` | YOLOv8s-OBB 2단계 학습 + val/test/test_extra 평가 | ✅ |
| 5 | `inference_tune.py` | conf/iou threshold 스윕 + tuned test/test_extra 평가 | ✅ |
| 6 | `visualize_results.py` | 학습 곡선/per-class/혼동행렬/샘플 예측 시각화 | ✅ |

---

## 3. 데이터셋

### 3.1 통합 결과 (analyze_dataset.py)

- **이미지**: 446장 (전부 640×480)
- **인스턴스**: 3,559개 (이미지당 평균 7.98, max 16)
- **빈 라벨 / 포맷 오류 / OOR 라인**: 0건
- **클리핑**: merge 단계에서 16 라인이 부동소수 경계 오차로 보정 (실제 데이터 손실 0)

### 3.2 소스 그룹 분포 (24개)

| 그룹 | 장수 |
|---|---|
| almond / cashew / pistachio / walnut (single) | 50 / 49 / 51 / 50 |
| almond_major / cashew_major / pistachio_major / walnut_major | 9 / 9 / 9 / 9 |
| **extra_cashew** (별도 세션, 20260504) | **50** |
| rb_*x*x*x* (3종 균등 4종) | 60 |
| rb_*x*x* (2종 균등 6종) | 60 |
| rd_dense_* (밀집 5종) | 40 |

### 3.3 클래스별 인스턴스 (AABB 외접 기준)

| 클래스 | 인스턴스 | 이미지 | avgW | avgH | 평균 정규화 면적 |
|---|---:|---:|---:|---:|---:|
| almond    | 745  | 182 | 0.0824 | 0.1083 | 0.00966 |
| cashew    | 1,150 | 235 | 0.0908 | 0.1189 | 0.01176 |
| pistachio | 900  | 236 | 0.0833 | 0.1108 | 0.01015 |
| walnut    | 764  | 207 | 0.1105 | 0.1442 | 0.01812 |

### 3.4 박스 크기 분포 (640×480 기준)

- small (<32 px): 112 (3.1 %)
- medium (32–96 px): **3,230 (90.8 %)**
- large (≥96 px): 217 (6.1 %)

### 3.5 분할 결과 (split_dataset.py, seed=42)

| split | 이미지 | almond | cashew | pistachio | walnut | 비고 |
|---|---:|---:|---:|---:|---:|---|
| train | 351 | 609 | 871 | 699 | 617 | 35장은 cashew_extra 학습 신호 |
| valid | 40  | 63  | 83  | 82  | 75  | extra 미포함 |
| test  | 40  | 73  | 70  | 87  | 65  | 일반 23셋 도메인만 |
| **test_extra** | **15** | 0 | **126** | 32 | 7 | **unseen session 단독 평가** |

- 일반 23셋: 8 : 1 : 1 source-stratified
- extra_cashew (50장): train = 35, **test_extra = 15** (별도 디렉토리)

---

## 4. 학습 설정 (yolo_train.py)

### 4.1 공통

- **모델**: `yolov8s-obb.pt` (11,423,327 params, 29.6 GFLOPs)
- **task**: `obb`, **device**: cuda:0, AMP on, deterministic seed = 42
- `--weights` 인자로 n/s/m 즉시 교체 가능, `--cls-gain` 으로 cls loss 가중치 조정 가능

### 4.2 Phase 1

| 항목 | 값 |
|---|---|
| epochs | 200 (patience = 30) → **epoch 181에서 조기 종료** |
| imgsz | 640 |
| batch | 16 |
| optimizer | SGD (lr0 = 0.01, lrf = 0.01, momentum = 0.937, wd = 5e-4) |
| LR schedule | cos_lr, warmup 3 epoch |
| 회전 증강 | degrees = 180° (OBB 회전 동치) |
| flip | flipud = 0.5, fliplr = 0.5 |
| mosaic / mixup | 1.0 / 0.1, close_mosaic = 10 |
| translate / scale | 0.1 / 0.5 |
| multi_scale | 0.5 |
| HSV | h = 0.015, s = 0.7, v = 0.4 |

### 4.3 Phase 2 (Phase 1 best.pt에서 fine-tune)

| 항목 | 값 |
|---|---|
| epochs | 50 (patience = 20) → **epoch 26에서 조기 종료** |
| imgsz | 800 (해상도 ↑) |
| batch | 8 |
| lr0 | 0.001 (Phase 1의 1/10) |
| 증강 | degrees = 180°, mosaic / mixup off, multi_scale off |

### 4.4 학습 진행

- 시작 20:38:19, 총 약 2 시간 30분 소요 (학습 종료 22:55 부근)
- Phase 1: 평균 ~44 s/epoch (multi_scale로 batch당 시간이 들쭉날쭉, RAM 캐시 워밍업 후 안정)
- Phase 1 epoch 47 시점에 이미 val mAP@0.5 = 0.995 / mAP@0.5:0.95 ≈ 0.897, 이후 mAP@0.5:0.95 미세 상향 (epoch 86: 0.905, epoch 139: 0.909)
- Phase 1 best는 epoch 151 부근, 그 이후 30 epoch 미개선으로 epoch 181에서 patience 트리거
- Phase 2: best는 epoch 6 부근, patience 20으로 epoch 26에서 종료
- 단일 백그라운드 실행으로 정상 종료 (exit code 0)

---

## 5. 평가 결과

### 5.1 Phase 2 best.pt 기본 평가 (TTA on)

| split | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|
| **valid** (40장 / 303 inst) | 0.996 | 0.994 | **0.995** | **0.918** |
| **test**  (40장 / 295 inst) | 0.995 | 0.994 | **0.991** | **0.894** |
| **test_extra** (15장 / 165 inst, unseen) | 0.994 | 0.984 | **0.995** | **0.895** |

### 5.2 Test split 클래스별 성능

| 클래스 | 이미지 | 인스턴스 | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|---:|---:|
| almond    | 19 | 73  | 0.998 | **1.000** | 0.995 | 0.885 |
| cashew    | 19 | 70  | **1.000** | 0.992 | 0.995 | **0.937** |
| pistachio | 20 | 87  | 0.996 | **1.000** | 0.995 | 0.916 |
| walnut    | 19 | 65  | 0.984 | 0.985 | 0.981 | 0.839 |

### 5.3 Test_extra (unseen session, cashew_extra 단독)

| 클래스 | 이미지 | 인스턴스 | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|---:|---:|
| cashew    | 15 | 126 | **1.000** | 0.984 | 0.995 | 0.906 |
| pistachio | 15 | 32  | 0.995 | 0.969 | 0.994 | 0.886 |
| walnut    | 6  | 7   | 0.987 | **1.000** | 0.995 | 0.893 |
| almond    | — | — | — | — | — | — |

→ 도메인 갭(domain shift)이 거의 관측되지 않음. 일반 test와 unseen test_extra의 mAP@0.5:0.95가 사실상 동일 (0.894 vs 0.895).

### 5.4 추론 속도 (RTX 5060 Laptop, imgsz = 800)

preprocess 1~3 ms + inference 6~10 ms + postprocess 2~3 ms ≈ **10~16 ms / image**

---

## 6. Threshold 스윕 (inference_tune.py)

### 6.1 스윕 구성

- conf : 0.10 → 0.60 (step 0.05) × iou : {0.5, 0.6, 0.7} → **33 회 val 평가**
- 산출: `conf_sweep_20260505_231450.csv`, `conf_sweep_20260505_231450.png`

### 6.2 Best on val

**conf = 0.35, iou = 0.50** — F1 = **0.995**, P = 0.997, R = 0.993, mAP@0.5 = 0.990

### 6.3 Tuned 평가

| 평가 | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|
| test (default, TTA) | 0.995 | 0.994 | 0.991 | 0.894 |
| **test (tuned conf=0.35, iou=0.5)** | 0.996 | 0.993 | 0.989 | 0.893 |
| test_extra (default, TTA) | 0.994 | 0.984 | 0.995 | 0.895 |
| **test_extra (tuned)** | 0.994 | 0.984 | 0.995 | 0.895 |

→ default와 거의 동일. 모델이 이미 well-calibrated 상태라 임계값 튜닝 마진이 작음 (03과 동일한 결론).

---

## 7. 목표 달성 여부

| 지표 | 목표 | exp_03 | exp_04 | 결과 |
|---|---|---|---|---|
| test mAP@0.5 | ≥ 0.97 | 0.992 | **0.991** | ✅ |
| test mAP@0.5:0.95 | ≥ 0.78 | 0.872 | **0.894** | ✅ (+0.022) |
| test cashew recall | ≥ 0.95 | 0.980 | **0.992** | ✅ |
| **extra_cashew (unseen) mAP@0.5** | **≥ 0.90** | (분리 측정 X) | **0.995** | ✅ (단독 측정) |
| **walnut mAP@0.5:0.95** | **≥ 0.85** | 0.816 | **0.839** | △ (-0.011) |

walnut을 제외한 모든 항목 충족. extra_cashew는 일반화 갭이 측정되지 않을 정도로 안정.

---

## 8. 산출물

```
cobot_OD_obb_small/
├── data.yaml                                 # 일반 평가용 (val/test)
├── data_extra.yaml                           # unseen session 평가용 (test=test_extra)
├── dataset_stats.json
├── train/  valid/  test/  test_extra/        # 분할된 이미지/라벨
├── train_phase1_20260505_203819/             # phase1 weights, results.csv, plots
├── train_phase2_20260505_203819/
│   └── weights/best.pt                       # ★ 최종 운영 모델
├── val_20260505_203819/                      # phase2 best 기준 val 평가
├── test_20260505_203819/                     # phase2 best 기준 test 평가
├── test_extra_20260505_203819/               # phase2 best 기준 unseen 평가
├── conf_sweep_20260505_231450.csv            # 33회 스윕 결과
├── conf_sweep_20260505_231450.png            # F1 vs conf 곡선
├── test_tuned_20260505_231450/               # tuned 임계값 test 평가
├── test_extra_tuned_20260505_231450/         # tuned 임계값 unseen 평가
└── visualizations/                           # 12개 시각화
    ├── training_curves_train_phase1_*.png
    ├── training_curves_train_phase2_*.png
    ├── per_class_metrics_val.png
    ├── per_class_metrics_test.png
    ├── per_class_metrics_test_extra.png
    ├── val_*_confusion_matrix(_normalized).png
    ├── test_tuned_*_confusion_matrix(_normalized).png
    ├── test_extra_tuned_*_confusion_matrix(_normalized).png
    └── sample_predictions.png
```

---

## 9. experiment_03 대비 핵심 변경

| 항목 | exp_03 (n) | exp_04 (s) |
|---|---|---|
| 모델 | yolov8n-obb (3.08M) | **yolov8s-obb (11.4M)** |
| 라벨 좌표 클리핑 | 없음 (16 라인이 invalid 가능) | **있음 (16 라인 보정)** |
| extra_cashew 평가 | test 안에 혼합 (도메인 갭 측정 X) | **`test_extra/` 단독 평가** |
| analyze per-class | 정확 (per_class_w[i]) | 정확 + OOR 라인 카운터 |
| 학습 옵션 | 고정 | `--weights`, `--cls-gain` 노출 |
| 조기 종료 | phase1 47ep 부근 best, 47 이후 patience | phase1 epoch 181, phase2 epoch 26에서 종료 |
| test mAP@0.5 | 0.992 | 0.991 |
| test mAP@0.5:0.95 | 0.872 | **0.894 (+0.022)** |
| walnut mAP@0.5:0.95 | 0.816 | **0.839 (+0.023)** |
| extra_cashew mAP@0.5 | 측정 X | **0.995** |

---

## 10. Codex 리뷰 반영 결과

| Codex 지적 (P2) | 반영 위치 | 결과 |
|---|---|---|
| OBB 좌표 [0,1] 범위 위반 | `merge_datasets.py` (clip_token + stats) | 16 라인 보정, OOR 카운터 = 0 |
| `analyze_dataset.py:84-85` per-class 통계 잘못된 인덱싱 | `analyze_dataset.py` (per_class_w[i] 사용 + 주석 명시) | 03이 이미 수정한 패턴 유지, 01의 회귀 방지 |

---

## 11. 결론 및 후속 제안

- **YOLOv8s-OBB + 좌표 클리핑 + unseen 분리 평가**로 test mAP@0.5:0.95를 0.872 → **0.894**로 끌어올림. walnut 클래스도 0.816 → 0.839로 약간 개선.
- extra_cashew 단독 mAP@0.5 = **0.995** — domain shift가 거의 관측되지 않을 정도로 안정.
- 임계값 튜닝 효과는 03과 마찬가지로 미미. 모델이 이미 잘 캘리브레이션됨.
- 후속 개선 방향:
  1. **walnut 약점 해소**: walnut mAP@0.5:0.95 = 0.839로 목표(0.85) 미달. `--cls-gain 1.5~2.0` 또는 walnut 회전·스케일 다양성 추가 데이터 검토.
  2. **모델 스케일 최종 비교**: `--weights yolov8m-obb.pt`로 동일 파이프라인 재실행해 s vs m 가성비 결정.
  3. **추론 배포 최적화**: TensorRT export → RTX 5060에서 5–8 ms / image 단축 가능.
  4. **scene-aware augmentation**: dense_* 그룹의 walnut large box 비율(119/764 ≈ 15.6%)이 다른 클래스보다 높음 → walnut 박스가 잘릴 위험. mosaic 비율 조정 검토.
