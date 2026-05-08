# 한국어 요약:
#   AI가 추천한 견과류 목록(categories)과 포만감(intensity)을 기반으로
#   너트 combo를 빌드하는 추천 엔진. JSON config에 정의된 매핑을 로드하여
#   포만감에 따른 할당 개수(low=3/normal=2/high=1)를 각 견과류에 동일하게 적용한다.
#   최대 개수 제한은 두지 않는다.
import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
SOURCE_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
VALID_INTENSITIES = {"low", "normal", "high"}

INTENSITY_KEYWORDS = {
    "low": ["조금", "약간", "살짝"],
    "normal": ["보통", "그냥", "어느 정도"],
    "high": ["많이", "너무", "매우", "완전", "진짜"],
}

NUT_LABELS_KO = {
    "almond": "아몬드",
    "cashew": "캐슈넛",
    "pistachio": "피스타치오",
    "walnut": "호두",
}

COUNT_LABELS_KO = {
    1: "한 개",
    2: "두 개",
    3: "세 개",
    4: "네 개",
    5: "다섯 개",
    6: "여섯 개",
}


def load_json(path):
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            logger.debug("Loaded JSON config: %s", path)
            return data
    except FileNotFoundError as exc:
        message = f"Required JSON config file not found: {path}"
        logger.error(message)
        raise FileNotFoundError(message) from exc
    except json.JSONDecodeError as exc:
        message = f"Failed to parse JSON config file: {path} ({exc.msg} at line {exc.lineno}, column {exc.colno})"
        logger.error(message)
        raise ValueError(message) from exc


def _get_config_dir():
    if SOURCE_CONFIG_DIR.exists():
        return SOURCE_CONFIG_DIR

    try:
        from ament_index_python.packages import get_package_share_directory

        share_config_dir = Path(get_package_share_directory("cobot_voice")) / "config"
        if share_config_dir.exists():
            return share_config_dir
    except Exception:
        pass

    return SOURCE_CONFIG_DIR



def build_combo(categories, intensity, combo_rules):
    if not categories:
        logger.info("No categories provided; combo is empty.")
        return []
    intensity_counts = combo_rules.get("intensity_counts", {})
    if intensity not in intensity_counts:
        logger.warning("Unknown intensity %r; using normal.", intensity)
        intensity = "normal"
    # intensity_counts는 low=3/normal=2/high=1. 견과류당 할당 개수.
    count_per_category = int(intensity_counts.get(intensity, intensity_counts.get("normal", 2)))

    combo_by_nut = {}
    ordered_nuts = []
    for nut in categories:
        if nut not in combo_by_nut:
            combo_by_nut[nut] = 0
            ordered_nuts.append(nut)
        combo_by_nut[nut] += count_per_category

    combo = [
        {"nut": nut, "count": int(combo_by_nut[nut])}
        for nut in ordered_nuts
        if combo_by_nut.get(nut, 0) > 0
    ]
    logger.debug(
        "Built combo=%s from categories=%s intensity=%s",
        combo,
        categories,
        intensity,
    )
    return combo


def format_combo_text(combo):
    if not combo:
        return ""

    parts = []
    for item in combo:
        nut = item.get("nut", "")
        count = int(item.get("count", 0))
        nut_label = NUT_LABELS_KO.get(nut, nut)
        count_label = COUNT_LABELS_KO.get(count, f"{count}개")
        parts.append(f"{nut_label} {count_label}")

    if len(parts) == 1:
        return parts[0]

    return "와 ".join(parts)


