import json
import logging
from datetime import datetime
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from cobot_voice.nut_recommendation import recommend_nuts
from cobot_voice.object_aliases import NUT_KEYWORD_MAP, NUT_NAMES, find_nut_targets


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_DIR / "output" / "latest_order.json"
VALID_NUTS = {"almond", "cashew", "pistachio", "walnut"}
VALID_INTENSITIES = {"low", "normal", "high"}
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

PROMPT_CONTENT = """
당신은 사용자의 문장을 분석하여 action과 견과류 키워드를 추출해야 합니다.

<action 판단 기준>
- sort: 분류, 나눠, 집어, 가져와, 골라, 담아, 줘, pick, sort, 정리 등
- stop: 멈춰, 정지, 그만, stop 등
- home: 홈, 원점, home, 초기위치, 돌아가 등

<견과류 리스트>
호두(walnut), 아몬드(almond), 캐슈넛(cashew), 피스타치오(pistachio)

<STT 오인식/변형 힌트>
- 호두는 호도, 월넛으로 들릴 수 있습니다.
- 캐슈넛은 캐슈, 캐슈 너트, 케슈넛, 케슈 너트로 들릴 수 있습니다.
- 피스타치오는 피스타 치오, 비스타치오로 들릴 수 있습니다.

<출력 형식>
첫 줄: action (sort, stop, home 중 하나)
둘째 줄: 견과류 키워드를 영어 canonical name으로, 공백 구분. 없으면 "none"

<예시>
입력: "호두랑 아몬드 집어"
출력:
sort
walnut almond

입력: "멈춰"
출력:
stop
none

입력: "홈으로 가"
출력:
home
none

입력: "건강하게 나눠줘"
출력:
sort
none

입력: "피스타치오 가져와"
출력:
sort
pistachio

<사용자 입력>
"{user_input}"
"""


class KeywordExtractor:
    def __init__(self, openai_api_key):
        self.llm = ChatOpenAI(
            model="gpt-4o", temperature=0.0, openai_api_key=openai_api_key
        )
        self.prompt_template = PromptTemplate(
            input_variables=["user_input"], template=PROMPT_CONTENT
        )
        self.chain = self.prompt_template | self.llm

    def extract(self, text):
        """Extract action and target nut names from user text.

        Returns:
            (action, targets): action is 'sort'/'stop'/'home',
                               targets is list of canonical nut names.
        """
        response = self.chain.invoke({"user_input": text})
        lines = response.content.strip().split("\n")

        action = lines[0].strip().lower() if lines else "sort"
        if action not in ("sort", "stop", "home"):
            action = "sort"

        targets = []
        if len(lines) >= 2:
            raw_targets = lines[1].strip()
            if raw_targets != "none":
                for word in raw_targets.split():
                    canonical = NUT_KEYWORD_MAP.get(word, word)
                    if canonical in NUT_NAMES and canonical not in targets:
                        targets.append(canonical)

        for target in find_nut_targets(text):
            if target not in targets:
                targets.append(target)

        return action, targets


def build_latest_order(text):
    recommendation = recommend_nuts(text)
    return build_latest_order_from_recommendation(recommendation)


def build_latest_order_from_recommendation(recommendation):
    combo = normalize_combo(recommendation.get("combo", []))
    categories = list(recommendation.get("categories", []))
    success = bool(categories and combo)
    intensity = normalize_intensity(recommendation.get("intensity", "normal"))

    return {
        "request_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "recognized_text": str(recommendation.get("recognized_text", "")),
        "categories": categories,
        "intensity": intensity,
        "combo": combo,
        "combo_text": str(recommendation.get("combo_text", "")),
        "success": success,
    }


def normalize_combo(combo):
    normalized_by_nut = {}
    ordered_nuts = []
    if not isinstance(combo, list):
        logger.warning("Invalid combo type %s; using empty combo.", type(combo).__name__)
        return []

    for item in combo:
        if not isinstance(item, dict):
            logger.warning("Invalid combo item %r; skipped.", item)
            continue

        nut = item.get("nut")
        if nut not in VALID_NUTS:
            logger.warning("Unknown nut %r; skipped.", nut)
            continue

        try:
            count = int(item.get("count", 0))
        except (TypeError, ValueError):
            logger.warning("Invalid count for nut %r: %r; skipped.", nut, item.get("count"))
            continue

        if count <= 0:
            logger.warning("Non-positive count for nut %r: %s; skipped.", nut, count)
            continue

        if nut not in normalized_by_nut:
            normalized_by_nut[nut] = 0
            ordered_nuts.append(nut)
        normalized_by_nut[nut] += count

    return [{"nut": nut, "count": normalized_by_nut[nut]} for nut in ordered_nuts]


def normalize_intensity(intensity):
    intensity = str(intensity or "normal")
    if intensity not in VALID_INTENSITIES:
        logger.warning("Unknown intensity %r; defaulting to normal.", intensity)
        return "normal"
    return intensity


def save_latest_order_data(order, output_path=DEFAULT_OUTPUT_PATH):
    order = normalize_latest_order(order)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(order, file, ensure_ascii=False, indent=2)
        file.write("\n")

    logger.info("Saved latest order: %s success=%s", output_path, order["success"])
    return order


def normalize_latest_order(order):
    combo = normalize_combo(order.get("combo", []))
    categories = list(order.get("categories", []))
    success = bool(order.get("success", False) and categories and combo)
    intensity = normalize_intensity(order.get("intensity", "normal"))

    return {
        "request_id": str(order.get("request_id", datetime.now().strftime("%Y%m%d_%H%M%S"))),
        "recognized_text": str(order.get("recognized_text", "")),
        "categories": categories,
        "intensity": intensity,
        "combo": combo,
        "combo_text": str(order.get("combo_text", "")),
        "success": success,
    }


def save_latest_order(text, output_path=DEFAULT_OUTPUT_PATH):
    order = build_latest_order(text)
    return save_latest_order_data(order, output_path)


def save_recommendation_order(recommendation, output_path=DEFAULT_OUTPUT_PATH):
    order = build_latest_order_from_recommendation(recommendation)
    return save_latest_order_data(order, output_path)
