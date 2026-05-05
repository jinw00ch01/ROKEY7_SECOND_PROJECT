"""
ROKEY7_SECOND_PROJECT/yolov8_obb_sources/ 내 24개 OBB 데이터셋 통합 (experiment_04).

experiment_03 대비 변경:
  - OBB 좌표를 [0, 1] 범위로 강제 클리핑하고 클리핑 통계 리포트 추가
    (Codex 리뷰 지적: 03 패치에 1.003... / 음수 좌표가 섞여 있어 Ultralytics가
    invalid로 처리하면서 학습 시 어노테이션/이미지가 누락될 수 있었음)
  - clip_eps를 넘는 큰 위반은 경고로 분리 (실제 라벨링 오류일 가능성)

OBB 라벨 포맷:
    class x1 y1 x2 y2 x3 y3 x4 y4   (9 토큰, 정규화 0~1, 회전 사각형 4꼭짓점)

표준 클래스 ID:
    0: almond, 1: cashew, 2: pistachio, 3: walnut
"""

import argparse
import collections
import os
import shutil
from pathlib import Path

import yaml

BASE = Path(r"C:\cobot_ws\ROKEY7_SECOND_PROJECT")
SOURCES = BASE / "yolov8_obb_sources"
ROOT = Path(__file__).parent
OUT_IMG = ROOT / "train" / "images"
OUT_LBL = ROOT / "train" / "labels"

STANDARD = ["almond", "cashew", "pistachio", "walnut"]
STD_ID = {n: i for i, n in enumerate(STANDARD)}

CLIP_EPS = 0.05  # 이 값을 넘는 위반은 경고 (보통은 부동소수 오차에 그침)


def tag_for(name: str) -> str:
    stem = name.replace(".yolov8-obb", "")
    if stem == "cashew_extra":
        return "extra_cashew"
    if stem.startswith("dense_"):
        return f"rd_{stem}"
    if stem.startswith(("a3_", "a4_", "c3_", "c4_", "w3_", "w4_")):
        return f"rb_{stem}"
    return stem.replace("_obb", "")


def normalize_names(names_field) -> list[str]:
    if isinstance(names_field, dict):
        return [names_field[k] for k in sorted(names_field)]
    return list(names_field)


def collect_datasets():
    if not SOURCES.exists():
        raise SystemExit(f"{SOURCES} not found")
    items = []
    for entry in sorted(os.listdir(SOURCES)):
        path = SOURCES / entry
        if path.is_dir() and entry.endswith(".yolov8-obb"):
            items.append((tag_for(entry), path))
    if not items:
        raise SystemExit(f"No *.yolov8-obb dataset directories under {SOURCES}")
    return items


def build_id_map(src_names, tag):
    mapping = {}
    warnings = []
    for src_idx, name in enumerate(src_names):
        key = name.lower()
        if name != key:
            warnings.append(f"[{tag}] class name '{name}' is not lowercase")
        if key not in STD_ID:
            raise ValueError(f"[{tag}] Unknown class '{name}' (not in {STANDARD})")
        mapping[src_idx] = STD_ID[key]
    return mapping, warnings


def clip_token(v: float) -> tuple[float, bool, bool]:
    """[0,1]로 클리핑. (clipped_value, was_clipped, was_extreme) 반환."""
    extreme = v < -CLIP_EPS or v > 1 + CLIP_EPS
    if v < 0.0:
        return 0.0, True, extreme
    if v > 1.0:
        return 1.0, True, extreme
    return v, False, False


def convert_obb_label(src_path: Path, dst_path: Path, id_map, tag: str, stats: dict) -> int:
    out_lines = []
    with open(src_path, "r") as f:
        for ln, raw in enumerate(f, 1):
            s = raw.strip()
            if not s:
                continue
            parts = s.split()
            if len(parts) != 9:
                raise ValueError(
                    f"[{tag}] {src_path.name}:{ln} expected 9 tokens (OBB), got {len(parts)}: {s!r}"
                )
            old_id = int(parts[0])
            if old_id not in id_map:
                raise ValueError(
                    f"[{tag}] {src_path.name}:{ln} class id {old_id} out of range"
                )
            new_id = id_map[old_id]
            line_clipped = False
            line_extreme = False
            new_tokens = [str(new_id)]
            for i in range(1, 9):
                v = float(parts[i])
                cv, was_clip, was_extreme = clip_token(v)
                line_clipped |= was_clip
                line_extreme |= was_extreme
                new_tokens.append(f"{cv:.6f}")
            if line_clipped:
                stats["clipped_lines"] += 1
            if line_extreme:
                stats["extreme_lines"].append(f"{tag}/{src_path.name}:{ln}")
            out_lines.append(" ".join(new_tokens))
    with open(dst_path, "w") as f:
        f.write("\n".join(out_lines))
        if out_lines:
            f.write("\n")
    return len(out_lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing merged output")
    args = ap.parse_args()

    if OUT_IMG.exists() and any(OUT_IMG.iterdir()):
        if not args.force:
            raise SystemExit(f"{OUT_IMG} not empty. Use --force to wipe.")
        shutil.rmtree(ROOT / "train")
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    OUT_LBL.mkdir(parents=True, exist_ok=True)

    datasets = collect_datasets()
    total_imgs = 0
    total_inst = 0
    per_class = collections.Counter()
    per_dataset = []
    all_warnings = []
    stats = {"clipped_lines": 0, "extreme_lines": []}

    for tag, path in datasets:
        with open(path / "data.yaml") as f:
            cfg = yaml.safe_load(f)
        names = normalize_names(cfg["names"])
        id_map, warns = build_id_map(names, tag)
        all_warnings.extend(warns)

        img_dir = path / "train" / "images"
        lbl_dir = path / "train" / "labels"

        ds_imgs = 0
        ds_inst = 0
        ds_class = collections.Counter()

        for img_src in sorted(img_dir.glob("*.jpg")):
            stem = img_src.stem
            lbl_src = lbl_dir / (stem + ".txt")
            if not lbl_src.exists():
                all_warnings.append(f"[{tag}] image {stem} has no label; skipped")
                continue

            new_stem = f"{tag}__{stem}"
            img_dst = OUT_IMG / (new_stem + ".jpg")
            lbl_dst = OUT_LBL / (new_stem + ".txt")
            shutil.copy2(img_src, img_dst)
            n = convert_obb_label(lbl_src, lbl_dst, id_map, tag, stats)

            ds_imgs += 1
            ds_inst += n
            with open(lbl_dst) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        ds_class[int(line.split()[0])] += 1

        per_class.update(ds_class)
        total_imgs += ds_imgs
        total_inst += ds_inst
        per_dataset.append((tag, ds_imgs, ds_inst, dict(ds_class), names, id_map))

    print(f"\n{'Source':<32} {'imgs':>5} {'inst':>6} | mapping (src_idx->std_idx)")
    print("-" * 110)
    for tag, n_img, n_box, _, names, id_map in per_dataset:
        m = " ".join(f"{i}({names[i]})->{j}" for i, j in id_map.items())
        print(f"{tag:<32} {n_img:>5} {n_box:>6} | {m}")

    print(f"\nTOTAL images: {total_imgs}")
    print(f"TOTAL OBB instances: {total_inst}")
    print("Per-class instances (standard ID):")
    for i, name in enumerate(STANDARD):
        print(f"  {i} {name:<10} {per_class[i]}")

    print(f"\n[Coordinate clipping]")
    print(f"  lines with at least one clipped token: {stats['clipped_lines']} "
          f"({stats['clipped_lines'] / max(total_inst, 1) * 100:.2f}%)")
    if stats["extreme_lines"]:
        print(f"  EXTREME violations (>|{CLIP_EPS}|), inspect manually: {len(stats['extreme_lines'])}")
        for e in stats["extreme_lines"][:20]:
            print(f"    - {e}")
    else:
        print(f"  no extreme violations beyond +/-{CLIP_EPS} (boundary float noise only)")

    if all_warnings:
        print(f"\n[WARNINGS] {len(all_warnings)}")
        for w in all_warnings:
            print(f"  - {w}")
    else:
        print("\n[OK] no warnings")

    print("\nNext: python analyze_dataset.py  then  python split_dataset.py")


if __name__ == "__main__":
    main()
