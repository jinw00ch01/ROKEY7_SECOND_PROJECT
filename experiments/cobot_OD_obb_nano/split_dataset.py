"""
8:1:1 source-stratified split + cashew_extra "unseen session" 분리 (experiment_03).

experiment_02와 다른 점:
  - cashew_extra (tag='extra_cashew')는 다른 촬영 세션이므로 다음과 같이 분배:
      * 70% train, 0% valid, **30% test**
        → test가 "보지 않은 세션"에서의 일반화 성능을 측정 (exp_01 §6.3.1 권고)
      * train으로 가는 35장은 cashew 학습 신호 보강 (cashew_extra의 73%가 cashew)
  - cashew oversampling 옵션은 제거 (cashew_extra가 그 역할을 더 잘함)
  - 나머지 23개 소스는 기존대로 8:1:1 source-stratified
"""

import collections
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
SRC_IMG = ROOT / "train" / "images"
SRC_LBL = ROOT / "train" / "labels"

REGULAR_SPLITS = {"train": 0.8, "valid": 0.1, "test": 0.1}
EXTRA_TAG = "extra_cashew"
EXTRA_SPLITS = {"train": 0.7, "valid": 0.0, "test": 0.3}
SEED = 42
NAMES = ["almond", "cashew", "pistachio", "walnut"]


def already_split() -> bool:
    for sp in ("valid", "test"):
        d = ROOT / sp / "images"
        if d.exists() and any(d.iterdir()):
            return True
    return False


def count_classes(label_paths):
    c = collections.Counter()
    for lp in label_paths:
        if not lp.exists(): continue
        for line in open(lp):
            line = line.strip()
            if line:
                c[int(line.split()[0])] += 1
    return c


def split_group(files, ratios, rng):
    files = sorted(files)
    rng.shuffle(files)
    n = len(files)
    n_train = round(n * ratios["train"])
    n_valid = round(n * ratios["valid"])
    n_test = n - n_train - n_valid
    if n_train == 0 and n > 0:
        n_train = 1
        n_valid = max(0, n_valid - 1) if n_valid else 0
        n_test = n - n_train - n_valid
    return {
        "train": files[:n_train],
        "valid": files[n_train:n_train + n_valid],
        "test":  files[n_train + n_valid:],
    }


def main():
    if already_split():
        raise SystemExit("valid/ or test/ already populated. Aborting.")

    images = sorted(SRC_IMG.glob("*.jpg"))
    if not images:
        raise SystemExit(f"No images in {SRC_IMG}")

    groups = collections.defaultdict(list)
    for p in images:
        prefix = p.stem.split("__", 1)[0]
        groups[prefix].append(p)

    rng = random.Random(SEED)
    assignments = {sp: [] for sp in REGULAR_SPLITS}
    extra_assignments = {sp: [] for sp in REGULAR_SPLITS}

    for prefix, files in groups.items():
        ratios = EXTRA_SPLITS if prefix == EXTRA_TAG else REGULAR_SPLITS
        per_split = split_group(files, ratios, rng)
        target = extra_assignments if prefix == EXTRA_TAG else assignments
        for sp in ("train", "valid", "test"):
            target[sp].extend(per_split[sp])

    for sp in REGULAR_SPLITS:
        (ROOT / sp / "images").mkdir(parents=True, exist_ok=True)
        (ROOT / sp / "labels").mkdir(parents=True, exist_ok=True)

    # 합쳐서 이동
    for sp in REGULAR_SPLITS:
        for img_src in assignments[sp] + extra_assignments[sp]:
            lbl_src = SRC_LBL / (img_src.stem + ".txt")
            img_dst = ROOT / sp / "images" / img_src.name
            lbl_dst = ROOT / sp / "labels" / lbl_src.name
            if img_src == img_dst:
                continue
            shutil.move(str(img_src), str(img_dst))
            if lbl_src.exists():
                shutil.move(str(lbl_src), str(lbl_dst))

    print(f"\n{'split':>6} {'imgs':>5} {'lbls':>5} | classes")
    print("-" * 70)
    for sp in REGULAR_SPLITS:
        n_img = len(list((ROOT / sp / "images").glob("*.jpg")))
        n_lbl = len(list((ROOT / sp / "labels").glob("*.txt")))
        cls_counts = count_classes(list((ROOT / sp / "labels").glob("*.txt")))
        breakdown = " ".join(f"{NAMES[i]}={cls_counts[i]}" for i in range(len(NAMES)))
        print(f"{sp:>6} {n_img:>5} {n_lbl:>5} | {breakdown}")

    # extra split 별도 보고
    print(f"\n[extra_cashew dispatch] "
          f"train={len(extra_assignments['train'])}, "
          f"valid={len(extra_assignments['valid'])}, "
          f"test={len(extra_assignments['test'])} "
          f"(이 중 test는 'unseen session' 평가용)")

    yaml_path = ROOT / "data.yaml"
    yaml_path.write_text(
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "\n"
        "nc: 4\n"
        "names: ['almond', 'cashew', 'pistachio', 'walnut']\n"
    )
    print(f"Updated {yaml_path}")


if __name__ == "__main__":
    main()
