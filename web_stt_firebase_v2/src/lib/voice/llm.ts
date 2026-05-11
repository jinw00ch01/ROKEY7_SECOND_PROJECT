import type { Intensity, NutClass } from "../types";

const CHAT_URL = "https://api.openai.com/v1/chat/completions";

const JOB_PROMPT = `사용자의 직업을 묻는 질문에 대한 답변을 분석하여, 직업 특성에 맞는 견과류를 1가지에서 최대 4가지까지 추천하고 판단 근거와 함께 안내 멘트를 작성해주세요.

<추천 가능한 견과류 종류>
- almond (아몬드)
- cashew (캐슈넛)
- pistachio (피스타치오)
- walnut (호두)

<출력 형식 (반드시 JSON 형식으로 출력)>
{
  "job": "교사",
  "recommended_nuts": ["walnut", "cashew"],
  "reasoning_message": "말씀을 많이 하시고 에너지가 필요하신 교사분이군요. 두뇌 회전에 좋은 호두와 피로 회복을 돕는 캐슈넛을 준비해 드릴게요."
}

<사용자 입력>
"{user_input}"`;

const SATIETY_PROMPT = `사용자의 현재 포만감을 나타내는 문장을 분석하여, 포만감 수준을 판단하고 판단 근거와 결과를 포함한 자연스러운 안내 멘트를 작성해주세요.

<포만감 수준 기준 (출력되는 satiety 값에 유의하세요)>
- 적음/배고픔 (견과류 3개씩 제공): low
- 보통/적당함 (견과류 2개씩 제공): normal
- 많음/배부름 (견과류 1개씩 제공): high

<출력 형식 (반드시 JSON 형식으로 출력)>
{
  "satiety": "low",
  "reasoning_message": "많이 출출하시군요. 든든하게 드실 수 있도록 넉넉히 준비해 드릴게요."
}

<사용자 입력>
"{user_input}"`;

const VALID_NUTS: NutClass[] = ["almond", "cashew", "pistachio", "walnut"];
const VALID_SATIETIES: Intensity[] = ["low", "normal", "high"];

async function callChat(prompt: string, apiKey: string): Promise<string> {
  const response = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o",
      temperature: 0.2,
      response_format: { type: "json_object" },
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`OpenAI chat failed (${response.status}): ${detail}`);
  }

  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  return payload.choices?.[0]?.message?.content?.trim() ?? "";
}

function safeJsonParse(content: string): Record<string, unknown> | null {
  try {
    let trimmed = content.trim();
    if (trimmed.startsWith("```json")) trimmed = trimmed.slice(7);
    else if (trimmed.startsWith("```")) trimmed = trimmed.slice(3);
    if (trimmed.endsWith("```")) trimmed = trimmed.slice(0, -3);
    return JSON.parse(trimmed.trim()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export type JobAnalysis = {
  recommended_nuts: NutClass[];
  reasoning_message: string;
};

export type SatietyAnalysis = {
  satiety: Intensity;
  reasoning_message: string;
};

export async function analyzeJob(
  text: string,
  apiKey: string,
): Promise<JobAnalysis> {
  if (!apiKey) {
    return { recommended_nuts: [], reasoning_message: "" };
  }
  try {
    const content = await callChat(
      JOB_PROMPT.replace("{user_input}", text),
      apiKey,
    );
    const parsed = safeJsonParse(content);
    if (!parsed) throw new Error("invalid JSON");
    const rawNuts = Array.isArray(parsed.recommended_nuts)
      ? parsed.recommended_nuts
      : [];
    const recommended_nuts = rawNuts
      .map((value) => String(value))
      .filter((value): value is NutClass =>
        (VALID_NUTS as string[]).includes(value),
      );
    return {
      recommended_nuts,
      reasoning_message: String(parsed.reasoning_message ?? ""),
    };
  } catch (error) {
    console.warn("JobAnalyzer failed:", error);
    return {
      recommended_nuts: [],
      reasoning_message: "직업을 파악하기 어렵네요.",
    };
  }
}

export async function analyzeSatiety(
  text: string,
  apiKey: string,
): Promise<SatietyAnalysis> {
  if (!apiKey) {
    return { satiety: "normal", reasoning_message: "" };
  }
  try {
    const content = await callChat(
      SATIETY_PROMPT.replace("{user_input}", text),
      apiKey,
    );
    const parsed = safeJsonParse(content);
    if (!parsed) throw new Error("invalid JSON");
    const raw = String(parsed.satiety ?? "normal");
    const validated: Intensity = (VALID_SATIETIES as string[]).includes(raw)
      ? (raw as Intensity)
      : "normal";
    return {
      satiety: validated,
      reasoning_message: String(parsed.reasoning_message ?? ""),
    };
  } catch (error) {
    console.warn("SatietyAnalyzer failed:", error);
    return {
      satiety: "normal",
      reasoning_message: "보통 양으로 준비해 드릴게요.",
    };
  }
}

// 메뉴 모드(menu prompt mode)에서 사용자가 번호/키워드로 답할 때 매칭용.
// 각 직업은 v1 JobAnalyzer 프롬프트와 동일한 4종(교사/개발자/운동선수/학생)이며,
// 추천 견과류 리스트는 직업 특성에 매핑한다 — AI 추론 없이 결정.
const MENU_JOB_CHOICES: Array<[NutClass[], string[]]> = [
  // 교사: 말 많이 함, 두뇌/회복 — walnut + cashew
  [["walnut", "cashew"], ["1", "1번", "일번", "첫째", "교사", "선생", "교수"]],
  // 개발자: 집중/혈당 — walnut + almond
  [["walnut", "almond"], ["2", "2번", "이번째", "둘째", "개발", "프로그래머", "엔지니어"]],
  // 운동선수: 회복/체중 — cashew + pistachio
  [["cashew", "pistachio"], ["3", "3번", "삼번", "셋째", "운동선수", "운동", "선수", "athlete"]],
  // 학생: 집중/혈당 — walnut + almond
  [["walnut", "almond"], ["4", "4번", "사번", "넷째", "학생", "수험생"]],
];

const MENU_SATIETY_CHOICES: Array<[Intensity, string[]]> = [
  ["low", ["1", "1번", "일번", "low", "적음", "조금", "배고", "출출", "허기"]],
  ["normal", ["2", "2번", "이번째", "normal", "보통", "적당", "그냥"]],
  ["high", ["3", "3번", "삼번", "high", "배부", "많이", "포만", "가득"]],
];

function tokenize(sample: string): Set<string> {
  return new Set(
    sample.split(/[\s,.?!　]+/u).filter((part) => part.length > 0),
  );
}

export function matchMenuJob(text: string): NutClass[] | null {
  const sample = (text ?? "").trim().toLowerCase();
  if (!sample) return null;
  const tokens = tokenize(sample);
  for (const [nuts, keywords] of MENU_JOB_CHOICES) {
    for (const kw of keywords) {
      if (!kw) continue;
      if (kw.length === 1 && kw.charCodeAt(0) < 128) {
        if (tokens.has(kw)) return nuts;
      } else if (sample.includes(kw)) {
        return nuts;
      }
    }
  }
  return null;
}

export function matchMenuSatiety(text: string): Intensity | null {
  const sample = (text ?? "").trim().toLowerCase();
  if (!sample) return null;
  const tokens = tokenize(sample);
  for (const [canonical, keywords] of MENU_SATIETY_CHOICES) {
    for (const kw of keywords) {
      if (!kw) continue;
      if (kw.length === 1 && kw.charCodeAt(0) < 128) {
        if (tokens.has(kw)) return canonical;
      } else if (sample.includes(kw)) {
        return canonical;
      }
    }
  }
  return null;
}
