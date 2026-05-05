"""
8:1:1 source-stratified split + cashew_extra "unseen session" 별도 분리 (experiment_04).

experiment_03 대비 변경:
  - extra_cashew를 일반 test와 합치지 않고 별도 디렉토리 `test_extra/`로 분리
    → unseen session에 대한 일반화 갭(domain shift)을 단독 측정 가능
    → 통합 test와 비교 시 데이터 분포 차이를 직접 정량화
  - data.yaml에 일반 4개 split 외에 test_extra 경로도 명시 (커스텀 평가용)
  - 일반 23셋 분할 비율은 03과 동일 (8:1:1, source-stratified, seed=42)
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
EXTRA_SPLITS = {"train": 0.7, "test_extra": 0.3}  # train은 신호 보강, test_extra는 unseen 평가용
SEED = 42
NAMES = ["almond", "cashew", "pistachio", "walnut"]
ALL_SPLITS = ["train", "valid", "test", "test_extra"]


def already_split() -> bool:
    for sp in ("valid", "test", "test_extra"):
        d = ROOT / sp / "images"
        if d.exists() and any(d.iterdir()):
            return True
    return False


def count_classes(label_paths):
    c = collections.Counter()
    for lp in label_paths:
        if not lp.exists():
            continue
        for line in open(lp):
            line = line.strip()
            if line:
                c[int(line.split()[0])] += 1
    return c


def split_regular(files, ratios, rng):
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
        "test": files[n_train + n_valid:],
    }


def split_extra(files, ratios, rng):
    files = sorted(files)
    rng.shuffle(files)
    n = len(files)
    n_train = round(n * ratios["train"])
    return {
        "train": files[:n_train],
        "test_extra": files[n_train:],
    }


def main():
    if already_split():
        raise SystemExit("valid/, test/, or test_extra/ already populated. Aborting.")

    images = sorted(SRC_IMG.glob("*.jpg"))
    if not images:
        raise SystemExit(f"No images in {SRC_IMG}")

    groups = collections.defaultdict(list)
    for p in images:
        prefix = p.stem.split("__", 1)[0]
        groups[prefix].append(p)

    rng = random.Random(SEED)
    per_split = {sp: [] for sp in ALL_SPLITS}

    for prefix, files in groups.items():
        if prefix == EXTRA_TAG:
            parts = split_extra(files, EXTRA_SPLITS, rng)
            per_split["train"].extend(parts["train"])
            per_split["test_extra"].extend(parts["test_extra"])
        else:
            parts = split_regular(files, REGULAR_SPLITS, rng)
            for sp in ("train", "valid", "test"):
                per_split[sp].extend(parts[sp])

    for sp in ALL_SPLITS:
        (ROOT / sp / "images").mkdir(parents=True, exist_ok=True)
        (ROOT / sp / "labels").mkdir(parents=True, exist_ok=True)

    for sp in ALL_SPLITS:
        for img_src in per_split[sp]:
            lbl_src = SRC_LBL / (img_src.stem + ".txt")
            img_dst = ROOT / sp / "images" / img_src.name
            lbl_dst = ROOT / sp / "labels" / lbl_src.name
            if img_src == img_dst:
                continue
            shutil.move(str(img_src), str(img_dst))
            if lbl_src.exists():
                shutil.move(str(lbl_src), str(lbl_dst))

    print(f"\n{'split':>10} {'imgs':>5} {'lbls':>5} | classes")
    print("-" * 70)
    for sp in ALL_SPLITS:
        n_img = len(list((ROOT / sp / "images").glob("*.jpg")))
        n_lbl = len(list((ROOT / sp / "labels").glob("*.txt")))
        cls_counts = count_classes(list((ROOT / sp / "labels").glob("*.txt")))
        breakdown = " ".join(f"{NAMES[i]}={cls_counts[i]}" for i in range(len(NAMES)))
        print(f"{sp:>10} {n_img:>5} {n_lbl:>5} | {breakdown}")

    print(f"\n[extra_cashew dispatch] "
          f"train={len(per_split['train']) and sum(1 for p in per_split['train'] if p.stem.startswith(EXTRA_TAG))}, "
          f"test_extra={len(per_split['test_extra'])} "
          f"(test_extra는 unseen session 단독 평가용)")

    yaml_path = ROOT / "data.yaml"
    yaml_path.write_text(
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        "# unseen session - 별도 평가용 (yolo_train.py가 별도 model.val 호출)\n"
        "test_extra: test_extra/images\n"
        "\n"
        "nc: 4\n"
        "names: ['almond', 'cashew', 'pistachio', 'walnut']\n"
    )
    print(f"Updated {yaml_path}")

    # Ultralytics가 test_extra를 평가하려면 별도 yaml이 필요 (split= 인자가 train/val/test만 인식하므로
    # test_extra를 'test'로 가리키는 보조 yaml을 두면 model.val(split='test', data=this_yaml)로 호출 가능).
    extra_yaml = ROOT / "data_extra.yaml"
    extra_yaml.write_text(
        "train: train/images\n"
        "val: valid/images\n"
        "test: test_extra/images\n"
        "\n"
        "nc: 4\n"
        "names: ['almond', 'cashew', 'pistachio', 'walnut']\n"
    )
    print(f"Updated {extra_yaml} (unseen session 평가용)")


if __name__ == "__main__":
    main()
