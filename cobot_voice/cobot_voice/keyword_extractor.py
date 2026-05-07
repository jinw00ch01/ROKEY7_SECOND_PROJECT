# 한국어 요약:
#   OpenAI gpt-4o LLM을 사용해 사용자 발화에서 action/너트 키워드와
#   상태(category)/강도(intensity)를 추출하는 legacy extractor 모듈.
#   save_recommendation_order는 latest_order.json 스키마의 단일 진실 소스.
#   normalize_combo는 중복 너트 제거 및 count 합산 후 success 여부를
#   categories와 combo가 모두 비어있지 않을 때만 True로 판정한다.
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


def build_latest_order(text: str):
    from cobot_voice.env import get_required_env
    from cobot_voice.keyword_extractor import StateAnalyzer, IntensityAnalyzer
    api_key = get_required_env("OPENAI_API_KEY")
    
    # Analyze state using AI
    state_analyzer = StateAnalyzer(openai_api_key=api_key)
    state_result = state_analyzer.analyze(text)
    
    category = state_result.get("category")
    categories = [category] if category else []
    reasoning = state_result.get("reasoning_message", "")
    
    # Default intensity
    intensity = "normal"
    
    if categories:
        intensity_analyzer = IntensityAnalyzer(openai_api_key=api_key)
        intensity_result = intensity_analyzer.analyze(text)
        intensity = intensity_result.get("intensity", "normal")
        # Combine reasoning if both exist
        if intensity_result.get("reasoning_message"):
            reasoning += " " + intensity_result.get("reasoning_message")

    from cobot_voice.nut_recommendation import recommend_nuts
    combo, combo_text = recommend_nuts(categories, intensity)
    
    order = build_latest_order_from_recommendation({
        "recognized_text": text,
        "categories": categories,
        "intensity": intensity,
        "combo": combo,
        "combo_text": combo_text
    })
    # 화면(UI)에는 AI 판단 근거 대신 결과 텍스트만 표시하여 UI 클린 유지
    order["confirm_message"] = combo_text
    # AI 판단 근거는 내부 로그용 혹은 필요시 TTS용으로 보존
    order["ai_reasoning"] = reasoning 
    return order


def build_latest_order_from_recommendation(recommendation):
    combo = normalize_combo(recommendation.get("combo", []))
    categories = list(recommendation.get("categories", []))
    # success는 카테고리도 있고 combo도 비어있지 않은 경우에만 True.
    # 두 조건 중 하나라도 비면 추천 실패로 간주한다.
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
    # 같은 너트가 여러 번 등장하면 count를 합산하면서 첫 등장 순서는 보존한다.
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

STATE_ANALYZER_PROMPT = """
사용자의 기분, 상태, 또는 목적을 나타내는 문장을 분석하여, 가장 적절한 카테고리를 하나 선택하고 판단 근거와 함께 어떤 견과류를 준비할지 자연스러운 안내 멘트를 작성해주세요.

<선택 가능한 카테고리>
- fatigue (피로/회복) -> 캐슈넛
- blood_sugar (혈당 관리) -> 아몬드
- diet (다이어트/체중) -> 피스타치오
- focus (집중/두뇌) -> 호두

<출력 형식 (반드시 JSON 형식으로 출력)>
{{
  "category": "fatigue",
  "reasoning_message": "요즘 많이 피곤하시군요. 피로 회복에 도움을 주는 캐슈넛을 준비해 드릴게요."
}}

<사용자 입력>
"{user_input}"
"""

INTENSITY_ANALYZER_PROMPT = """
사용자가 원하는 견과류의 양을 나타내는 문장을 분석하여, 양(강도)을 판단하고 판단 근거와 결과를 포함한 자연스러운 안내 멘트를 작성해주세요.

<양 판단 기준>
- low (적게): 1개 (예: 조금, 맛만, 하나만)
- normal (보통): 2개 (예: 적당히, 보통, 알아서)
- high (많이): 3개 이상 (예: 많이, 듬뿍, 왕창)

<출력 형식 (반드시 JSON 형식으로 출력)>
{{
  "intensity": "high",
  "reasoning_message": "기운이 팍팍 나도록 넉넉하게 준비해 드릴게요."
}}

<사용자 입력>
"{user_input}"
"""

class StateAnalyzer:
    def __init__(self, openai_api_key):
        self.llm = ChatOpenAI(
            model="gpt-4o", temperature=0.2, openai_api_key=openai_api_key
        )
        self.prompt_template = PromptTemplate(
            input_variables=["user_input"], template=STATE_ANALYZER_PROMPT
        )
        self.chain = self.prompt_template | self.llm

    def analyze(self, text):
        response = self.chain.invoke({"user_input": text})
        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Failed to parse StateAnalyzer JSON response: %s", response.content)
            return {"category": "", "reasoning_message": "잘 알아듣지 못했지만, 기본 견과류를 준비해 드릴게요."}

class IntensityAnalyzer:
    def __init__(self, openai_api_key):
        self.llm = ChatOpenAI(
            model="gpt-4o", temperature=0.2, openai_api_key=openai_api_key
        )
        self.prompt_template = PromptTemplate(
            input_variables=["user_input"], template=INTENSITY_ANALYZER_PROMPT
        )
        self.chain = self.prompt_template | self.llm

    def analyze(self, text):
        response = self.chain.invoke({"user_input": text})
        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Failed to parse IntensityAnalyzer JSON response: %s", response.content)
            return {"intensity": "normal", "reasoning_message": "보통 양으로 준비해 드릴게요."}
