# 한국어 요약:
#   STT 오인식과 한국어 표기 변형(호도/월넛/케슈넛/비스타치오 등)을 흡수하기
#   위한 alias map과 정규화 헬퍼. raw 텍스트에서 canonical 영문 너트명을
#   직접 찾아내어 LLM 추출 결과를 보강한다.
import re


# Canonical nut name mapping (Korean/English variants -> canonical English name)
# 한 canonical name(예: walnut)에 한국어 표준어/오타/STT 오인식/영문 변형을
# 모두 매핑하여 입력 다양성을 흡수한다.
NUT_KEYWORD_MAP = {
    "호두": "walnut",
    "호도": "walnut",
    "월넛": "walnut",
    "월넛츠": "walnut",
    "walnuts": "walnut",
    "walnut": "walnut",
    "아몬드": "almond",
    "알몬드": "almond",
    "almonds": "almond",
    "almond": "almond",
    "캐슈넛": "cashew",
    "캐슈 너트": "cashew",
    "캐슈너트": "cashew",
    "케슈넛": "cashew",
    "케슈 너트": "cashew",
    "케슈너트": "cashew",
    "캐슈": "cashew",
    "케슈": "cashew",
    "cashews": "cashew",
    "cashew": "cashew",
    "피스타치오": "pistachio",
    "피스타 치오": "pistachio",
    "피스타치오넛": "pistachio",
    "피스타치오 너트": "pistachio",
    "비스타치오": "pistachio",
    "pistachios": "pistachio",
    "pistachio": "pistachio",
}

# All valid canonical nut names
NUT_NAMES = {"walnut", "almond", "cashew", "pistachio"}


def normalize_keyword(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", text.lower())


def find_nut_targets(text: str) -> list[str]:
    """Find nut targets directly from raw STT text.

    This catches inflected Korean like "호두랑" and common STT variants like
    "호도", "캐슈 너트", and "피스타 치오".
    """
    normalized_text = normalize_keyword(text)
    matches: list[tuple[int, str]] = []

    for alias, canonical in NUT_KEYWORD_MAP.items():
        normalized_alias = normalize_keyword(alias)
        if not normalized_alias:
            continue

        index = normalized_text.find(normalized_alias)
        if index >= 0:
            matches.append((index, canonical))

    targets: list[str] = []
    for _, canonical in sorted(matches, key=lambda item: item[0]):
        if canonical not in targets:
            targets.append(canonical)

    return targets
