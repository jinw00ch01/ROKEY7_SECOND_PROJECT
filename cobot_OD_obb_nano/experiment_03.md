# Experiment 03 — Cobot Nut OBB Detection 실행 리포트

**실행일**: 2026-05-04
**프로젝트**: `cobot_OD_obb_nano`
**환경**: Windows 11 · NVIDIA GeForce RTX 5060 Laptop GPU (8 GB) · Python 3.12.10 · PyTorch 2.12.0+cu128 · Ultralytics 8.4.43
**Baseline**: experiment_01 (axis-aligned, test mAP@0.5 = 0.985 / mAP@0.5:0.95 = 0.79 / cashew R = 0.88)

> 본 문서는 사전에 작성된 계획안(이전 버전)을 **실제 실행 결과 기반**으로 다시 정리한 리포트입니다.

---

## 1. 목적과 핵심 변경

axis-aligned 박스 대비 회전 사각형(OBB) 라벨로 4종 견과류(almond, cashew, pistachio, walnut)를 검출. 24개 OBB 소스를 통합하고 `cashew_extra`(별도 촬영 세션, 20260504)를 test에 분리 배치해 **미경험 세션 일반화**까지 측정.

### 1.1 성능 목표

| 지표 | 목표 |
|---|---|
| test mAP@0.5 (OBB) | ≥ 0.97 |
| test mAP@0.5:0.95 (OBB) | ≥ 0.78 |
| test cashew recall | ≥ 0.95 |
| extra_cashew (unseen session) test mAP@0.5 | ≥ 0.90 |

---

## 2. 실행 파이프라인

| # | 스크립트 | 역할 | 상태 |
|---|---|---|---|
| 1 | `merge_datasets.py` | 24개 OBB 소스 → `train/{images,labels}/` 통합 | 기존 통합 결과 재사용 (446장) |
| 2 | `analyze_dataset.py` | 클래스/박스 분포 점검 + `dataset_stats.json` | ✅ |
| 3 | `split_dataset.py` | train/valid/test 분할 + `data.yaml` 생성 | ✅ |
| 4 | `yolo_train.py` | YOLOv8-OBB 2단계 학습 + val/test 평가 | ✅ |
| 5 | `inference_tune.py` | conf/iou threshold 스윕 + tuned test 평가 | ✅ |
| 6 | `visualize_results.py` | 학습 곡선/per-class/혼동행렬/샘플 예측 시각화 | ✅ |

---

## 3. 데이터셋

### 3.1 통합 결과 (analyze_dataset.py)
- **이미지**: 446장 (전부 640×480)
- **인스턴스**: 3,559개 (이미지당 평균 7.98, max 16)
- **빈 라벨 / 포맷 오류**: 0건

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
| almond    | 745  | 182 | 0.082 | 0.108 | 0.0097 |
| cashew    | 1,150 | 235 | 0.091 | 0.119 | 0.0118 |
| pistachio | 900  | 236 | 0.083 | 0.111 | 0.0102 |
| walnut    | 764  | 207 | 0.111 | 0.144 | 0.0181 |

### 3.4 박스 크기 분포 (640×480 기준)
- small (<32 px): 112 (3.1 %)
- medium (32–96 px): **3,229 (90.7 %)**
- large (≥96 px): 218 (6.1 %)
→ 중간 크기 객체가 압도적이라 imgsz=640이 충분.

### 3.5 분할 결과 (split_dataset.py, seed=42)

| split | 이미지 | almond | cashew | pistachio | walnut |
|---|---:|---:|---:|---:|---:|
| train | 351 | 609 | 871 | 699 | 617 |
| valid | 40  | 63  | 83  | 82  | 75  |
| test  | 55  | 73  | **196** | 119 | 72  |

- 일반 23셋: 8 : 1 : 1 source-stratified
- **extra_cashew (50장)**: train = 35, valid = 0, **test = 15** → unseen session 평가용

---

## 4. 학습 설정 (yolo_train.py)

### 4.1 공통
- **모델**: `yolov8n-obb.pt` (3.08 M params, 8.4 GFLOPs, OBB head를 nc=4로 어댑트)
- **task**: `obb`, **device**: cuda:0, AMP on, deterministic seed = 42
- 모델 사이즈는 코드의 `--weights` 인자로 즉시 교체 가능 (`yolo_train.py:133`).

### 4.2 Phase 1

| 항목 | 값 |
|---|---|
| epochs | 200 (patience = 30) |
| imgsz | 640 |
| batch | 16 |
| optimizer | SGD (lr0 = 0.01, lrf = 0.01, momentum = 0.937, wd = 5e-4) |
| LR schedule | cos_lr, warmup 3 epoch |
| 회전 증강 | **degrees = 180°** (axis-aligned 실험은 10°였음) |
| flip | flipud = 0.5, fliplr = 0.5 |
| mosaic / mixup | 1.0 / 0.1, close_mosaic = 10 |
| translate / scale | 0.1 / 0.5 |
| multi_scale | 0.5 |
| HSV | h = 0.015, s = 0.7, v = 0.4 |

### 4.3 Phase 2 (Phase 1 best.pt에서 fine-tune)

| 항목 | 값 |
|---|---|
| epochs | 50 |
| imgsz | **800** (해상도 ↑) |
| batch | 8 |
| lr0 | 0.001 (Phase 1의 1/10) |
| 증강 | degrees = 180° 유지, mosaic / mixup off, multi_scale off |

### 4.4 학습 진행 관찰
- 시작 17:30:49, Phase 1 epoch당 약 9 초 (train ~3 s + val ~0.3 s + 오버헤드).
- epoch 47 시점에 이미 val mAP@0.5 = 0.995 / mAP@0.5:0.95 = 0.886 도달 → 매우 빠른 수렴.
- GPU 메모리: 학습 중 1 ~ 6 GB 변동, 8 GB VRAM 안에서 안정.
- Phase 1 + Phase 2 + val/test 평가까지 단일 백그라운드 실행으로 정상 종료 (exit code 0).

---

## 5. 평가 결과

### 5.1 Phase 2 best.pt 기본 평가

| split | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|
| **valid** (40장 / 303 inst) | 0.991 | 0.986 | **0.995** | **0.905** |
| **test**  (55장 / 460 inst) | 0.987 | 0.984 | **0.992** | **0.872** |

### 5.2 Test split 클래스별 성능

| 클래스 | 이미지 | 인스턴스 | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|---:|---:|
| almond    | 19 | 73  | **1.000** | 0.999 | 0.995 | 0.870 |
| cashew    | 34 | 196 | 0.997 | **0.980** | 0.995 | 0.901 |
| pistachio | 35 | 119 | 0.967 | **1.000** | 0.994 | 0.899 |
| walnut    | 25 | 72  | 0.985 | 0.958 | 0.982 | 0.816 |

### 5.3 추론 속도 (test, RTX 5060 Laptop, imgsz = 800)
preprocess 2.1 ms + inference 7.4 ms + postprocess 5.6 ms ≈ **15 ms / image**

---

## 6. Threshold 스윕 (inference_tune.py)

### 6.1 스윕 구성
- conf : 0.10 → 0.60 (step 0.05) × iou : {0.5, 0.6, 0.7} → **33 회 val 평가**
- 산출: `conf_sweep_20260504_175042.csv`, `conf_sweep_20260504_175042.png`

### 6.2 Best on val
**conf = 0.40, iou = 0.50** — F1 = **0.993**, P = 0.994, R = 0.992, mAP@0.5 = 0.990

### 6.3 Tuned test 평가

| 평가 | P | R | mAP@0.5 | mAP@0.5:0.95 |
|---|---:|---:|---:|---:|
| test (default) | 0.987 | 0.984 | **0.992** | **0.872** |
| test (tuned conf=0.4 / iou=0.5) | 0.987 | 0.984 | 0.982 | 0.866 |

→ default와 큰 차이 없음. 모델이 이미 well-calibrated 상태라 임계값 튜닝 마진이 작음.

---

## 7. 목표 달성 여부

| 지표 | 목표 | 실측 | 결과 |
|---|---|---|---|
| test mAP@0.5 (OBB) | ≥ 0.97 | **0.992** | ✅ |
| test mAP@0.5:0.95 (OBB) | ≥ 0.78 | **0.872** | ✅ |
| test cashew recall | ≥ 0.95 | **0.980** | ✅ |
| extra_cashew (unseen) mAP@0.5 | ≥ 0.90 | (별도 분리 평가 미수행, 통합 test = 0.992) | △ 통합 측정만 |

> extra_cashew 단독 분리 평가는 inference_tune.py 주석에 향후 작업으로 언급되어 있음. 현 단계에서는 test 전체 mAP가 0.992로 매우 높아 일반화 실패 신호는 관측되지 않음.

---

## 8. 산출물

```
cobot_OD_obb_nano/
├── data.yaml
├── dataset_stats.json
├── train/  valid/  test/                     # 분할된 이미지/라벨
├── train_phase1_20260504_173049/             # phase1 weights, results.csv, plots
├── train_phase2_20260504_173049/
│   └── weights/best.pt                       # ★ 최종 운영 모델
├── val_20260504_173049/                      # phase2 best 기준 val 평가
├── test_20260504_173049/                     # phase2 best 기준 test 평가
├── conf_sweep_20260504_175042.csv            # 33회 스윕 결과
├── conf_sweep_20260504_175042.png            # F1 vs conf 곡선
├── test_tuned_20260504_175042/               # tuned 임계값 test 평가
└── visualizations/                           # 9개 시각화
    ├── training_curves_train_phase1_*.png
    ├── training_curves_train_phase2_*.png
    ├── per_class_metrics_val.png
    ├── per_class_metrics_test.png
    ├── val_*_confusion_matrix(_normalized).png
    ├── test_tuned_*_confusion_matrix(_normalized).png
    └── sample_predictions.png
```

---

## 9. experiment_02 대비 핵심 변경

| 항목 | exp_02 (axis-aligned) | exp_03 (OBB, 본 실험) |
|---|---|---|
| 라벨 포맷 | class + 4 좌표 (5 토큰) | class + 8 좌표 (9 토큰, 4 꼭짓점) |
| Ultralytics task | `detect` | **`obb`** |
| 모델 | yolov8s.pt | **yolov8n-obb.pt** |
| 회전 증강 (degrees) | 10° | **180°** |
| 상하 반전 (flipud) | 0.0 | **0.5** |
| 데이터 소스 수 | 23 | **24** (cashew_extra 추가) |
| Unseen session 평가 | 없음 | **test 내 extra_cashew 15장** |
| copy_paste 증강 | 사용 | OBB 미지원으로 0.0 |

---

## 10. 결론 및 후속 제안

- YOLOv8n-OBB 만으로도 **test mAP@0.5 = 0.992** / **mAP@0.5:0.95 = 0.872** 달성. 일차 목표 3종 모두 충족.
- 임계값 튜닝 효과는 거의 없음 → 현 학습 결과가 이미 잘 캘리브레이션됨.
- 후속 개선 방향:
  1. **extra_cashew 단독 분리 평가**: test 디렉토리에서 `extra_cashew_` prefix 파일을 별도 split으로 분리해 일반화 갭(domain shift)을 정량화.
  2. **모델 스케일 비교**: `--weights yolov8s-obb.pt` / `yolov8m-obb.pt`로 동일 파이프라인 재실행해 가성비 비교.
  3. **walnut 보강**: walnut의 mAP@0.5:0.95 = 0.816 으로 다른 클래스 대비 약간 낮음 → 회전·크기 다양성 추가 데이터 검토.
  4. **추론 배포 최적화**: TensorRT export → RTX 5060에서 5–8 ms / image 단축 가능.
