from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from cobot_voice.object_aliases import NUT_KEYWORD_MAP, NUT_NAMES, find_nut_targets

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
