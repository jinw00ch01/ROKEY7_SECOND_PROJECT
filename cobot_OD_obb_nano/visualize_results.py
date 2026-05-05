"""
OBB 학습 결과 시각화 (experiment_03).

experiment_02 visualize_results.py와 거의 동일하나:
  - model.predict / model.val 호출 시 task='obb' 명시
  - sample predictions가 회전 박스로 그려짐 (ultralytics가 자동 처리)
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
NAMES = ["almond", "cashew", "pistachio", "walnut"]


def latest_run(prefix: str) -> Path:
    runs = sorted([p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(prefix)])
    if not runs:
        raise FileNotFoundError(f"No '{prefix}*' under {ROOT}")
    return runs[-1]


def auto_run() -> Path:
    for prefix in ("train_phase2_", "train_phase1_", "train_"):
        try: return latest_run(prefix)
        except FileNotFoundError: continue
    raise FileNotFoundError("No train_* runs found")


def plot_training_curves(run_dir: Path, out_dir: Path):
    csv = run_dir / "results.csv"
    if not csv.exists():
        print(f"[skip] {csv} not found"); return
    df = pd.read_csv(csv); df.columns = [c.strip() for c in df.columns]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    loss_pairs = [
        ("train/box_loss", "val/box_loss", "Box loss"),
        ("train/cls_loss", "val/cls_loss", "Cls loss"),
        ("train/dfl_loss", "val/dfl_loss", "DFL loss"),
    ]
    for ax, (tr, va, title) in zip(axes[0], loss_pairs):
        if tr in df: ax.plot(df["epoch"], df[tr], label="train", linewidth=2)
        if va in df: ax.plot(df["epoch"], df[va], label="val", linewidth=2, linestyle="--")
        ax.set_title(title); ax.set_xlabel("epoch"); ax.legend(); ax.grid(True, alpha=0.3)

    metric_keys = [
        ("metrics/precision(B)", "Precision"),
        ("metrics/recall(B)", "Recall"),
        ("metrics/mAP50(B)", "mAP@0.5"),
    ]
    for ax, (key, title) in zip(axes[1], metric_keys):
        if key in df:
            ax.plot(df["epoch"], df[key], color="tab:blue", linewidth=2)
            best_ep = int(df["epoch"][df[key].idxmax()])
            best_v = float(df[key].max())
            ax.scatter([best_ep], [best_v], color="red", zorder=5)
            ax.annotate(f"best={best_v:.3f}@{best_ep}", (best_ep, best_v),
                        textcoords="offset points", xytext=(10, -10))
        ax.set_title(title); ax.set_xlabel("epoch"); ax.grid(True, alpha=0.3)
    fig.suptitle(f"Training curves: {run_dir.name}", fontsize=14)
    fig.tight_layout()
    out = out_dir / f"training_curves_{run_dir.name}.png"
    fig.savefig(out, dpi=120); plt.close(fig); print(f"[ok] {out}")


def plot_per_class_metrics(model, data_yaml: Path, split: str, out_dir: Path, device):
    metrics = model.val(task="obb", data=str(data_yaml), split=split,
                        plots=False, verbose=False, device=device)
    p = np.asarray(metrics.box.p); r = np.asarray(metrics.box.r)
    map50 = np.asarray(metrics.box.ap50); map5095 = np.asarray(metrics.box.maps)
    if not len(p): print(f"[skip] no per-class metrics for {split}"); return
    x = np.arange(len(NAMES)); width = 0.2
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - 1.5*width, p, width, label="Precision", color="#4C9AFF")
    ax.bar(x - 0.5*width, r, width, label="Recall",    color="#36B37E")
    ax.bar(x + 0.5*width, map50, width, label="mAP@0.5", color="#FFAB00")
    ax.bar(x + 1.5*width, map5095, width, label="mAP@0.5:0.95", color="#FF5630")
    ax.set_xticks(x); ax.set_xticklabels(NAMES); ax.set_ylim(0, 1.05)
    ax.set_title(f"Per-class metrics on {split} set (OBB)")
    ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    for xi, vals in enumerate(zip(p, r, map50, map5095)):
        for off, v in zip([-1.5, -0.5, 0.5, 1.5], vals):
            ax.text(xi + off*width, v + 0.01, f"{v:.2f}", ha="center", fontsize=8)
    fig.tight_layout()
    out = out_dir / f"per_class_metrics_{split}.png"
    fig.savefig(out, dpi=120); plt.close(fig); print(f"[ok] {out}")


def copy_confusion_matrices(val_dirs, out_dir):
    for d in val_dirs:
        if not d.exists(): continue
        for fname in ("confusion_matrix.png", "confusion_matrix_normalized.png"):
            src = d / fname
            if src.exists():
                dst = out_dir / f"{d.name}_{fname}"
                dst.write_bytes(src.read_bytes())
                print(f"[ok] {dst}")


def plot_sample_predictions(model, data_yaml: Path, out_dir: Path, device, n=8):
    import yaml
    cfg = yaml.safe_load(data_yaml.read_text())
    test_img_dir = (data_yaml.parent / cfg.get("test", "test/images")).resolve()
    if not test_img_dir.exists():
        test_img_dir = (data_yaml.parent / cfg.get("val", "valid/images")).resolve()
    # extra_cashew (unseen session)도 보이도록 일반/extra 절반씩
    all_imgs = sorted(test_img_dir.glob("*.jpg"))
    extra = [p for p in all_imgs if p.stem.startswith("extra_cashew__")][:n//2]
    regular = [p for p in all_imgs if not p.stem.startswith("extra_cashew__")][:n - len(extra)]
    imgs = extra + regular
    if not imgs:
        print(f"[skip] no images in {test_img_dir}"); return

    cols = 4; rows = (len(imgs) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols*4, rows*3))
    axes = np.atleast_2d(axes)
    for ax, img_path in zip(axes.flat, imgs):
        result = model.predict(task="obb", source=str(img_path),
                               conf=0.25, verbose=False, device=device)[0]
        plotted = result.plot()
        ax.imshow(plotted[:, :, ::-1])
        is_extra = img_path.stem.startswith("extra_cashew__")
        title_color = "tab:red" if is_extra else "black"
        ax.set_title(("[extra] " if is_extra else "") + img_path.stem.split("__", 1)[0],
                     fontsize=9, color=title_color)
        ax.axis("off")
    for ax in axes.flat[len(imgs):]: ax.axis("off")
    fig.suptitle("Sample test predictions (OBB) — red title = unseen session", fontsize=12)
    fig.tight_layout()
    out = out_dir / "sample_predictions.png"
    fig.savefig(out, dpi=120); plt.close(fig); print(f"[ok] {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    ap.add_argument("--out", default="visualizations")
    args = ap.parse_args()

    run_dir = ROOT / args.run if args.run else auto_run()
    out_dir = ROOT / args.out; out_dir.mkdir(exist_ok=True)
    print(f"Using run : {run_dir}\nOut dir   : {out_dir}")

    for prefix in ("train_phase1_", "train_phase2_"):
        try: plot_training_curves(latest_run(prefix), out_dir)
        except FileNotFoundError: pass
    if not run_dir.name.startswith(("train_phase1_", "train_phase2_")):
        plot_training_curves(run_dir, out_dir)

    weights = run_dir / "weights" / "best.pt"
    if not weights.exists(): weights = run_dir / "weights" / "last.pt"
    if not weights.exists():
        print(f"[warn] no weights in {run_dir/'weights'}; skipping live evals"); return

    try:
        import torch
        from ultralytics import YOLO
    except ImportError:
        print("[warn] ultralytics not installed; skipping live evals"); return

    device = 0 if torch.cuda.is_available() else "cpu"
    model = YOLO(str(weights))
    data_yaml = ROOT / "data.yaml"

    plot_per_class_metrics(model, data_yaml, "val", out_dir, device)
    plot_per_class_metrics(model, data_yaml, "test", out_dir, device)

    val_dirs = []
    for prefix in ("val_", "test_", "test_tuned_"):
        try: val_dirs.append(latest_run(prefix))
        except FileNotFoundError: pass
    copy_confusion_matrices(val_dirs, out_dir)

    plot_sample_predictions(model, data_yaml, out_dir, device)
    print("\nDone. Open visualizations/ to view results.")


if __name__ == "__main__":
    main()
