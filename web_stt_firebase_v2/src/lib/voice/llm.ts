import type { CategoryId, Intensity } from "../types";

const CHAT_URL = "https://api.openai.com/v1/chat/completions";

const STATE_PROMPT = `사용자의 기분, 상태, 또는 목적을 나타내는 문장을 분석하여, 가장 적절한 카테고리를 하나 선택하고 판단 근거와 함께 어떤 견과류를 준비할지 자연스러운 안내 멘트를 작성해주세요.

<선택 가능한 카테고리>
- fatigue (피로/회복) -> 캐슈넛
- blood_sugar (혈당 관리) -> 아몬드
- diet (다이어트/체중) -> 피스타치오
- focus (집중/두뇌) -> 호두

<출력 형식 (반드시 JSON 형식으로 출력)>
{
  "category": "fatigue",
  "reasoning_message": "요즘 많이 피곤하시군요. 피로 회복에 도움을 주는 캐슈넛을 준비해 드릴게요."
}

<사용자 입력>
"{user_input}"`;

const INTENSITY_PROMPT = `사용자가 원하는 견과류의 양을 나타내는 문장을 분석하여, 양(강도)을 판단하고 판단 근거와 결과를 포함한 자연스러운 안내 멘트를 작성해주세요.

<양 판단 기준>
- low (적게): 1개 (예: 조금, 맛만, 하나만)
- normal (보통): 2개 (예: 적당히, 보통, 알아서)
- high (많이): 3개 이상 (예: 많이, 듬뿍, 왕창)

<출력 형식 (반드시 JSON 형식으로 출력)>
{
  "intensity": "high",
  "reasoning_message": "기운이 팍팍 나도록 넉넉하게 준비해 드릴게요."
}

<사용자 입력>
"{user_input}"`;

const VALID_CATEGORIES: CategoryId[] = ["fatigue", "blood_sugar", "diet", "focus"];
const VALID_INTENSITIES: Intensity[] = ["low", "normal", "high"];

async function callChat(
  prompt: string,
  apiKey: string,
): Promise<string> {
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

export type StateAnalysis = {
  category: CategoryId | "";
  reasoning_message: string;
};

export type IntensityAnalysis = {
  intensity: Intensity;
  reasoning_message: string;
};

export async function analyzeState(
  text: string,
  apiKey: string,
): Promise<StateAnalysis> {
  if (!apiKey) {
    return { category: "", reasoning_message: "" };
  }
  try {
    const content = await callChat(
      STATE_PROMPT.replace("{user_input}", text),
      apiKey,
    );
    const parsed = safeJsonParse(content);
    if (!parsed) throw new Error("invalid JSON");
    const category = String(parsed.category ?? "");
    const validated: CategoryId | "" = (VALID_CATEGORIES as string[]).includes(
      category,
    )
      ? (category as CategoryId)
      : "";
    return {
      category: validated,
      reasoning_message: String(parsed.reasoning_message ?? ""),
    };
  } catch (error) {
    console.warn("StateAnalyzer failed:", error);
    return {
      category: "",
      reasoning_message: "잘 알아듣지 못했지만, 기본 견과류를 준비해 드릴게요.",
    };
  }
}

export async function analyzeIntensity(
  text: string,
  apiKey: string,
): Promise<IntensityAnalysis> {
  if (!apiKey) {
    return { intensity: "normal", reasoning_message: "" };
  }
  try {
    const content = await callChat(
      INTENSITY_PROMPT.replace("{user_input}", text),
      apiKey,
    );
    const parsed = safeJsonParse(content);
    if (!parsed) throw new Error("invalid JSON");
    const raw = String(parsed.intensity ?? "normal");
    const validated: Intensity = (VALID_INTENSITIES as string[]).includes(raw)
      ? (raw as Intensity)
      : "normal";
    return {
      intensity: validated,
      reasoning_message: String(parsed.reasoning_message ?? ""),
    };
  } catch (error) {
    console.warn("IntensityAnalyzer failed:", error);
    return {
      intensity: "normal",
      reasoning_message: "보통 양으로 준비해 드릴게요.",
    };
  }
}

const MENU_STATE_CHOICES: Array<[CategoryId, string[]]> = [
  ["fatigue", ["1", "1번", "일번", "첫째", "피로", "피곤"]],
  ["blood_sugar", ["2", "2번", "이번째", "둘째", "혈당", "당분"]],
  ["diet", ["3", "3번", "삼번", "셋째", "다이어트", "체중", "살빼"]],
  ["focus", ["4", "4번", "사번", "넷째", "집중", "두뇌", "공부"]],
];

const MENU_INTENSITY_CHOICES: Array<[Intensity, string[]]> = [
  ["low", ["1", "1번", "일번", "low", "조금", "약간", "약하", "맛만", "적게"]],
  ["normal", ["2", "2번", "이번째", "normal", "보통", "적당", "그냥"]],
  ["high", ["3", "3번", "삼번", "high", "많이", "듬뿍", "잔뜩", "왕창", "강하"]],
];

function matchMenu<T extends string>(
  text: string,
  choices: ReadonlyArray<readonly [T, readonly string[]]>,
): T | null {
  const sample = (text ?? "").trim().toLowerCase();
  if (!sample) return null;
  const tokens = new Set(
    sample.split(/[\s,.?!\u3000]+/u).filter((part) => part.length > 0),
  );
  for (const [canonical, keywords] of choices) {
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

export function matchMenuState(text: string): CategoryId | null {
  return matchMenu(text, MENU_STATE_CHOICES);
}

export function matchMenuIntensity(text: string): Intensity | null {
  return matchMenu(text, MENU_INTENSITY_CHOICES);
}
