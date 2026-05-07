"""
OBB 학습 후 conf/iou threshold 스윕 (experiment_04).

experiment_03 대비 변경:
  - test split에 더 이상 extra_cashew가 섞여 있지 않음 (split_dataset.py가 분리)
  - 따라서 tuned 평가도 (a) test (일반) + (b) test_extra (unseen) 둘 다 별도 보고
  - 보조 yaml `data_extra.yaml`을 사용해 ultralytics가 test_extra를 'test'로 인식하게 함
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from ultralytics import YOLO

ROOT = Path(__file__).parent


def latest_best() -> Path:
    for prefix in ("train_phase2_", "train_phase1_", "train_"):
        for d in sorted(ROOT.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith(prefix):
                w = d / "weights" / "best.pt"
                if w.exists():
                    return w
    raise FileNotFoundError("No train_*/weights/best.pt under project root")


def f1(p, r):
    return (2 * p * r / (p + r)) if (p + r) > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights")
    ap.add_argument("--conf-min", type=float, default=0.10)
    ap.add_argument("--conf-max", type=float, default=0.60)
    ap.add_argument("--conf-step", type=float, default=0.05)
    ap.add_argument("--ious", default="0.5,0.6,0.7")
    args = ap.parse_args()

    weights = Path(args.weights) if args.weights else latest_best()
    print(f"Using weights: {weights}")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not available.")
    device = 0
    model = YOLO(str(weights))
    data_yaml = ROOT / "data.yaml"
    data_extra_yaml = ROOT / "data_extra.yaml"

    confs = []
    c = args.conf_min
    while c <= args.conf_max + 1e-9:
        confs.append(round(c, 3))
        c += args.conf_step
    ious = [float(x) for x in args.ious.split(",")]

    rows = []
    print(
        f"\nSweeping conf={confs} x iou={ious} on val split (OBB)...\n"
        f"{'conf':>5} {'iou':>5} {'P':>6} {'R':>6} {'F1':>6} {'mAP50':>7}"
    )
    for iou in ious:
        for conf in confs:
            m = model.val(
                task="obb", data=str(data_yaml), split="val", device=device,
                conf=conf, iou=iou, plots=False, verbose=False,
            )
            P = float(m.box.mp); R = float(m.box.mr)
            F = f1(P, R); map50 = float(m.box.map50)
            rows.append({"conf": conf, "iou": iou, "P": P, "R": R, "F1": F, "mAP50": map50})
            print(f"{conf:>5.2f} {iou:>5.2f} {P:>6.3f} {R:>6.3f} {F:>6.3f} {map50:>7.3f}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = ROOT / f"conf_sweep_{ts}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["conf", "iou", "P", "R", "F1", "mAP50"])
        w.writeheader(); w.writerows(rows)
    print(f"\nWrote {csv_path}")

    fig, ax = plt.subplots(figsize=(10, 6))
    for iou in ious:
        sub = [r for r in rows if r["iou"] == iou]
        ax.plot([r["conf"] for r in sub], [r["F1"] for r in sub],
                marker="o", label=f"F1 (iou={iou})")
    ax.set_xlabel("conf"); ax.set_ylabel("F1")
    ax.set_title("Val F1 vs conf (OBB)"); ax.grid(True, alpha=0.3); ax.legend()
    fig_path = ROOT / f"conf_sweep_{ts}.png"
    fig.tight_layout(); fig.savefig(fig_path, dpi=120); plt.close(fig)
    print(f"Wrote {fig_path}")

    best = max(rows, key=lambda r: r["F1"])
    print(
        f"\n[BEST on val] conf={best['conf']} iou={best['iou']} "
        f"F1={best['F1']:.3f} P={best['P']:.3f} R={best['R']:.3f} mAP50={best['mAP50']:.3f}"
    )

    print("\nRe-evaluating test split (regular) with the best (conf, iou)...")
    tm = model.val(
        task="obb", data=str(data_yaml), split="test", device=device,
        conf=best["conf"], iou=best["iou"], plots=True, verbose=True,
        project=str(ROOT), name=f"test_tuned_{ts}",
    )
    print(
        f"[TEST tuned] P={float(tm.box.mp):.3f} R={float(tm.box.mr):.3f} "
        f"mAP50={float(tm.box.map50):.3f} mAP50-95={float(tm.box.map):.3f}"
    )

    if data_extra_yaml.exists():
        print("\nRe-evaluating test_extra (unseen session) with the best (conf, iou)...")
        em = model.val(
            task="obb", data=str(data_extra_yaml), split="test", device=device,
            conf=best["conf"], iou=best["iou"], plots=True, verbose=True,
            project=str(ROOT), name=f"test_extra_tuned_{ts}",
        )
        print(
            f"[TEST_EXTRA tuned] P={float(em.box.mp):.3f} R={float(em.box.mr):.3f} "
            f"mAP50={float(em.box.map50):.3f} mAP50-95={float(em.box.map):.3f}"
        )


if __name__ == "__main__":
    main()
