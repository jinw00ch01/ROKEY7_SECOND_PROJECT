"""
OBB 통합 데이터셋 정밀 분석 - experiment_04.

experiment_03 대비 변경:
  - per-class 통계는 03과 동일하게 per_class_w[i] / per_class_h[i] 만 사용
    (Codex 리뷰: 01 버전이 전역 box_w를 잘못 인덱싱한 버그를 회귀하지 않도록 명시)
  - OOR 좌표 카운터 추가: 클리핑은 merge에서 끝났지만, 분석 단계에서도 검증

OBB AABB 외접 박스 기준 (exp_01/02 비교 가능하도록 동일 기준 유지).
"""

import collections
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
IMG_DIR = ROOT / "train" / "images"
LBL_DIR = ROOT / "train" / "labels"
NAMES = ["almond", "cashew", "pistachio", "walnut"]
PX_W, PX_H = 640, 480


def size_bucket(area_norm: float) -> str:
    side = (area_norm * PX_W * PX_H) ** 0.5
    if side < 32:
        return "small"
    if side < 96:
        return "medium"
    return "large"


def parse_obb(line: str):
    parts = line.split()
    cid = int(parts[0])
    xs = [float(parts[i]) for i in (1, 3, 5, 7)]
    ys = [float(parts[i]) for i in (2, 4, 6, 8)]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    in_range = all(0.0 <= v <= 1.0 for v in xs + ys)
    return cid, w, h, in_range


def main():
    images = sorted(IMG_DIR.glob("*.jpg"))
    labels = sorted(LBL_DIR.glob("*.txt"))
    print(f"images: {len(images)}")
    print(f"labels: {len(labels)}")

    src_counter = collections.Counter()
    for p in images:
        src_counter[p.stem.split("__", 1)[0]] += 1
    print("\n[Source-group distribution]")
    for k, v in sorted(src_counter.items()):
        print(f"  {k:<25} {v}")

    res = collections.Counter()
    for p in images[:50]:
        with Image.open(p) as im:
            res[im.size] += 1
    print(f"\n[Image resolutions (sampled 50)]: {dict(res)}")

    per_class_inst = collections.Counter()
    per_image_class = collections.Counter()
    inst_per_image = []
    per_class_w = collections.defaultdict(list)
    per_class_h = collections.defaultdict(list)
    per_class_area = collections.defaultdict(list)
    per_class_size_bucket = {i: collections.Counter() for i in range(len(NAMES))}
    images_with_class = collections.defaultdict(set)
    images_with_cashew = []
    multi_label_imgs = collections.Counter()
    empty_imgs = 0
    overall_size_bucket = collections.Counter()
    bad_token_lines = 0
    out_of_range_lines = 0

    for lp in labels:
        stem = lp.stem
        lines = [l.strip() for l in open(lp) if l.strip()]
        if not lines:
            empty_imgs += 1
        inst_per_image.append(len(lines))
        present = set()
        for line in lines:
            if len(line.split()) != 9:
                bad_token_lines += 1
                continue
            cid, w, h, in_range = parse_obb(line)
            if not in_range:
                out_of_range_lines += 1
            per_class_inst[cid] += 1
            present.add(cid)
            # 의도: 해당 클래스의 박스만 per_class_w[cid]에 누적해야 클래스별 평균 폭이 의미를 가짐
            per_class_w[cid].append(w)
            per_class_h[cid].append(h)
            per_class_area[cid].append(w * h)
            bucket = size_bucket(w * h)
            per_class_size_bucket[cid][bucket] += 1
            overall_size_bucket[bucket] += 1
            images_with_class[cid].add(stem)
        if 1 in present:
            images_with_cashew.append(stem)
        for c in present:
            per_image_class[c] += 1
        multi_label_imgs[len(present)] += 1

    total_inst = sum(per_class_inst.values())
    avg_ipi = sum(inst_per_image) / len(inst_per_image) if inst_per_image else 0.0
    print(
        f"\n[OBB stats] total_instances={total_inst}, empty_label_files={empty_imgs}, "
        f"bad_token_lines={bad_token_lines}, out_of_range_lines={out_of_range_lines}"
    )
    print(
        f"  inst/img: avg={avg_ipi:.2f}, "
        f"min={min(inst_per_image) if inst_per_image else 0}, "
        f"max={max(inst_per_image) if inst_per_image else 0}"
    )

    print("\n[Per-class statistics (AABB envelope, only that class's boxes)]")
    print(f"  {'cls':<12} {'inst':>6} {'imgs':>5} {'avgW':>7} {'avgH':>7} {'avgArea':>9}")
    for i, n in enumerate(NAMES):
        ws = per_class_w[i]
        hs = per_class_h[i]
        areas = per_class_area[i]
        if areas:
            print(
                f"  {n:<12} {per_class_inst[i]:>6} {len(images_with_class[i]):>5} "
                f"{sum(ws) / len(ws):>7.4f} {sum(hs) / len(hs):>7.4f} "
                f"{sum(areas) / len(areas):>9.5f}"
            )
        else:
            print(f"  {n:<12} 0 0 - - -")

    print(f"\n[Box size buckets (640x480 ref, AABB envelope)]")
    for k in ("small", "medium", "large"):
        c = overall_size_bucket[k]
        pct = (c / total_inst * 100) if total_inst else 0
        rng = {"small": "<32px", "medium": "32-96px", "large": ">=96px"}[k]
        print(f"  {k:<6} ({rng:<8}): {c:>5} ({pct:.1f}%)")

    print("\n[Per-class size buckets]")
    print(f"  {'cls':<12} {'small':>6} {'medium':>6} {'large':>6}")
    for i, n in enumerate(NAMES):
        b = per_class_size_bucket[i]
        print(f"  {n:<12} {b['small']:>6} {b['medium']:>6} {b['large']:>6}")

    print(f"\n[Distinct classes per image]")
    for k in sorted(multi_label_imgs):
        print(f"  {k} class(es) in image: {multi_label_imgs[k]} images")

    out = {
        "total_images": len(images),
        "total_instances": total_inst,
        "empty_label_files": empty_imgs,
        "bad_token_lines": bad_token_lines,
        "out_of_range_lines": out_of_range_lines,
        "inst_per_image": {
            "avg": round(avg_ipi, 3),
            "min": min(inst_per_image) if inst_per_image else 0,
            "max": max(inst_per_image) if inst_per_image else 0,
        },
        "per_class_instances": {NAMES[i]: per_class_inst[i] for i in range(len(NAMES))},
        "per_class_images": {NAMES[i]: len(images_with_class[i]) for i in range(len(NAMES))},
        "per_class_avg_w": {NAMES[i]: (sum(per_class_w[i]) / len(per_class_w[i]) if per_class_w[i] else 0.0) for i in range(len(NAMES))},
        "per_class_avg_h": {NAMES[i]: (sum(per_class_h[i]) / len(per_class_h[i]) if per_class_h[i] else 0.0) for i in range(len(NAMES))},
        "per_class_size_bucket": {
            NAMES[i]: dict(per_class_size_bucket[i]) for i in range(len(NAMES))
        },
        "size_bucket_overall": dict(overall_size_bucket),
        "source_groups": dict(src_counter),
        "images_with_cashew": sorted(images_with_cashew),
        "multi_class_images": dict(multi_label_imgs),
    }
    json_path = ROOT / "dataset_stats.json"
    json_path.write_text(json.dumps(out, indent=2))
    print(f"\n[wrote] {json_path}")


if __name__ == "__main__":
    main()
