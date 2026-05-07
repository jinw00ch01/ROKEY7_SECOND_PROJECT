"""
cobot_object_detection_obb_04 - YOLOv8-OBB 2단계 학습 (experiment_04).

experiment_03 대비 변경:
  - 기본 백본을 yolov8s-obb.pt 로 상향 (03 후속 제안 #2: 모델 스케일 비교)
    → --weights 인자로 n/m도 즉시 교체 가능
  - extra_cashew unseen session 별도 평가 추가 (data_extra.yaml로 model.val)
  - walnut 보강을 위한 cls loss 가중치 옵션 (`--cls-gain`) 추가, 기본은 1.0 유지
  - 라벨 좌표 클리핑 적용된 데이터 사용 → Ultralytics가 invalid로 스킵하던
    문제 해소(Codex 리뷰 P2 반영)

성능 목표 (03에 더한 추가 항목):
    - test mAP@0.5 (OBB)              >= 0.97
    - test mAP@0.5:0.95 (OBB)         >= 0.78
    - test cashew recall              >= 0.95
    - extra_cashew (unseen) mAP@0.5   >= 0.90  ← 단독 측정
    - walnut mAP@0.5:0.95             >= 0.85  (03 = 0.816)
"""

import argparse
from datetime import datetime
from pathlib import Path

import torch
from ultralytics import YOLO

ROOT = Path(__file__).parent


def train_phase1(weights, data_yaml, ts, device, cls_gain):
    name = f"train_phase1_{ts}"
    model = YOLO(str(weights))
    model.train(
        task="obb",
        data=str(data_yaml),
        epochs=200,
        imgsz=640,
        batch=16,
        patience=30,
        project=str(ROOT),
        name=name,
        device=device,
        workers=8,
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        cos_lr=True,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3.0,
        cls=cls_gain,
        # 증강
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=180.0,
        translate=0.1,
        scale=0.5,
        shear=0.0,
        perspective=0.0,
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.0,
        close_mosaic=10,
        multi_scale=0.5,
        cache=True,
        amp=True,
        seed=42,
        deterministic=True,
        plots=True,
        save=True,
        verbose=True,
    )
    return ROOT / name


def train_phase2(phase1_dir: Path, data_yaml, ts, device, cls_gain):
    weights = phase1_dir / "weights" / "best.pt"
    if not weights.exists():
        raise FileNotFoundError(f"phase1 best.pt not found: {weights}")
    name = f"train_phase2_{ts}"
    model = YOLO(str(weights))
    model.train(
        task="obb",
        data=str(data_yaml),
        epochs=50,
        imgsz=800,
        batch=8,
        patience=20,
        project=str(ROOT),
        name=name,
        device=device,
        workers=8,
        optimizer="SGD",
        lr0=0.001,
        lrf=0.01,
        cos_lr=True,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=1.0,
        cls=cls_gain,
        hsv_h=0.015, hsv_s=0.5, hsv_v=0.3,
        degrees=180.0,
        translate=0.05, scale=0.3,
        flipud=0.5, fliplr=0.5,
        mosaic=0.0, mixup=0.0, copy_paste=0.0,
        close_mosaic=0, multi_scale=0.0,
        cache=True, amp=True,
        seed=42, deterministic=True,
        plots=True, save=True, verbose=True,
    )
    return ROOT / name


def evaluate(run_dir: Path, data_yaml, data_extra_yaml, ts, device, tta: bool):
    weights = run_dir / "weights" / "best.pt"
    if not weights.exists():
        raise FileNotFoundError(f"best.pt not found: {weights}")
    val_name = f"val_{ts}"
    test_name = f"test_{ts}"
    test_extra_name = f"test_extra_{ts}"

    model = YOLO(str(weights))
    model.val(task="obb", data=str(data_yaml), split="val",
              project=str(ROOT), name=val_name, plots=True, device=device, augment=tta)
    model.val(task="obb", data=str(data_yaml), split="test",
              project=str(ROOT), name=test_name, plots=True, device=device, augment=tta)
    if data_extra_yaml.exists():
        model.val(task="obb", data=str(data_extra_yaml), split="test",
                  project=str(ROOT), name=test_extra_name, plots=True, device=device, augment=tta)
        return ROOT / val_name, ROOT / test_name, ROOT / test_extra_name
    return ROOT / val_name, ROOT / test_name, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, choices=[1, 2, 12], default=12)
    ap.add_argument("--resume", help="phase1 run dir name (for --phase 2 only)")
    ap.add_argument("--no-tta", action="store_true")
    ap.add_argument("--weights", default="yolov8s-obb.pt",
                    help="initial weights (yolov8n-obb.pt / yolov8s-obb.pt / yolov8m-obb.pt)")
    ap.add_argument("--cls-gain", type=float, default=1.0,
                    help="cls loss gain (>1 to push minority classes harder; e.g. walnut)")
    args = ap.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not available.")
    device = 0
    print(f"Using device: cuda:{device} ({torch.cuda.get_device_name(device)})")

    data_yaml = ROOT / "data.yaml"
    data_extra_yaml = ROOT / "data_extra.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(f"{data_yaml} not found. Run merge + split first.")

    initial = ROOT / args.weights
    if not initial.exists():
        initial = args.weights  # ultralytics 자동 다운로드

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    phase1_dir = None
    if args.phase in (1, 12):
        phase1_dir = train_phase1(initial, data_yaml, ts, device, args.cls_gain)
    if args.phase in (2, 12):
        if args.phase == 2:
            if not args.resume:
                raise SystemExit("--resume <phase1_dir> required when --phase 2")
            phase1_dir = ROOT / args.resume
        phase2_dir = train_phase2(phase1_dir, data_yaml, ts, device, args.cls_gain)
        target = phase2_dir
    else:
        target = phase1_dir

    val_dir, test_dir, test_extra_dir = evaluate(target, data_yaml, data_extra_yaml, ts, device, tta=not args.no_tta)

    print("\n=== Done ===")
    if phase1_dir:
        print(f"phase1        : {phase1_dir}")
    if args.phase in (2, 12):
        print(f"phase2        : {target}")
    print(f"val run       : {val_dir}")
    print(f"test run      : {test_dir}")
    if test_extra_dir:
        print(f"test_extra run: {test_extra_dir}  (unseen session)")
    print(f"best.pt       : {target / 'weights' / 'best.pt'}")


if __name__ == "__main__":
    main()
