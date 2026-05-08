# 한국어 요약:
#   사용자 발화 텍스트에서 카테고리/강도를 키워드 기반으로 추출하고
#   너트 combo를 빌드하는 추천 엔진. JSON config에 정의된 매핑을 로드하여
#   intensity_counts(low=1/normal=2/high=3)와 max_total_count=6 cap을 적용.
#   다중 카테고리 overflow 시 카테고리 등장 순서를 우선순위로 사용해
#   낮은 우선순위 너트부터 count를 줄인다.
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


def extract_categories(text, categories_config):
    normalized_text = str(text or "").strip().lower()
    if not normalized_text:
        logger.info("Empty STT text; no categories extracted.")
        return []

    category_items = categories_config.get("categories", categories_config)
    matches = []

    for category, config in category_items.items():
        keywords = config.get("keywords", [])
        matched_indexes = [
            normalized_text.find(keyword.lower())
            for keyword in keywords
            if keyword.lower() in normalized_text
        ]
        if matched_indexes:
            matches.append((min(matched_indexes), category))

    # 텍스트 내 등장 위치(index)가 빠른 카테고리를 더 높은 우선순위로 본다.
    categories = [category for _, category in sorted(matches, key=lambda item: item[0])]
    logger.debug("Extracted categories=%s from text=%r", categories, text)
    return categories


def extract_intensity(text):
    normalized_text = str(text or "").strip().lower()
    if not normalized_text:
        logger.info("Empty intensity text; defaulting intensity to normal.")
        return "normal"

    matches = []

    for intensity, keywords in INTENSITY_KEYWORDS.items():
        for keyword in keywords:
            index = normalized_text.find(keyword.lower())
            if index >= 0:
                matches.append((index, intensity))

    if not matches:
        logger.info("No intensity keyword found; defaulting intensity to normal.")
        return "normal"

    intensity = sorted(matches, key=lambda item: item[0])[0][1]
    if intensity not in VALID_INTENSITIES:
        logger.warning("Unknown intensity %r; defaulting to normal.", intensity)
        return "normal"

    logger.debug("Extracted intensity=%s from text=%r", intensity, text)
    return intensity


def build_combo(categories, intensity, combo_rules, categories_config):
    if not categories:
        logger.info("No categories provided; combo is empty.")
        return []

    category_items = categories_config.get("categories", categories_config)
    intensity_counts = combo_rules.get("intensity_counts", {})
    if intensity not in intensity_counts:
        logger.warning("Unknown intensity %r; using normal.", intensity)
        intensity = "normal"
    # intensity_counts는 보통 low=1/normal=2/high=3. 카테고리당 너트 개수.
    count_per_category = int(intensity_counts.get(intensity, intensity_counts.get("normal", 2)))
    # 전체 combo 합계의 상한(기본 6개). 초과 시 우선순위 낮은 너트부터 감산.
    max_total_count = int(combo_rules.get("max_total_count", 6))

    combo_by_nut = {}
    ordered_nuts = []
    for category in categories:
        nut = category_items.get(category, {}).get("nut")
        if not nut:
            logger.warning("Category %r has no nut mapping; skipped.", category)
            continue
        if nut not in combo_by_nut:
            combo_by_nut[nut] = 0
            ordered_nuts.append(nut)
        combo_by_nut[nut] += count_per_category

    combo_by_nut = _cap_combo_by_priority(combo_by_nut, ordered_nuts, max_total_count)
    combo = [
        {"nut": nut, "count": int(combo_by_nut[nut])}
        for nut in ordered_nuts
        if combo_by_nut.get(nut, 0) > 0
    ]
    logger.debug(
        "Built combo=%s from categories=%s intensity=%s max_total_count=%s",
        combo,
        categories,
        intensity,
        max_total_count,
    )
    return combo


def _cap_combo_by_priority(combo_by_nut, ordered_nuts, max_total_count):
    """Limit total count by reducing lower-priority nuts first.

    Category order is preserved as priority. Later nuts lose count before earlier
    nuts, and may be reduced to zero if max_total_count is very small.
    """
    total_count = sum(combo_by_nut.values())
    if total_count <= max_total_count:
        return combo_by_nut

    logger.info(
        "Combo total %s exceeds max_total_count %s; capping by priority.",
        total_count,
        max_total_count,
    )

    # category_order(=ordered_nuts) 역순으로 순회하여 낮은 우선순위 너트의
    # count부터 한 개씩 줄여 max_total_count 이내로 맞춘다.
    for nut in reversed(ordered_nuts):
        while total_count > max_total_count and combo_by_nut.get(nut, 0) > 0:
            combo_by_nut[nut] -= 1
            total_count -= 1
        if total_count <= max_total_count:
            break

    return combo_by_nut


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


def recommend_nuts(text):
    clean_text = str(text or "").strip()
    if not clean_text:
        logger.info("Empty STT text; returning empty recommendation.")
        return {
            "recognized_text": "",
            "categories": [],
            "intensity": "normal",
            "combo": [],
            "combo_text": "",
        }

    config_dir = _get_config_dir()
    categories_config = load_json(config_dir / "keyword_categories.json")
    combo_rules = load_json(config_dir / "nut_combo_rules.json")

    categories = extract_categories(clean_text, categories_config)
    intensity = extract_intensity(clean_text)
    combo = build_combo(categories, intensity, combo_rules, categories_config)

    recommendation = {
        "recognized_text": clean_text,
        "categories": categories,
        "intensity": intensity,
        "combo": combo,
        "combo_text": format_combo_text(combo),
    }
    logger.info(
        "Recommendation built: categories=%s intensity=%s combo=%s",
        categories,
        intensity,
        combo,
    )
    return recommendation
