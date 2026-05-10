type QuestionFlowMessages = Record<string, string>;

let cached: QuestionFlowMessages | null = null;

async function load(): Promise<QuestionFlowMessages> {
  if (cached) return cached;
  const response = await fetch("/config/question_flow.json");
  if (!response.ok) {
    throw new Error(`Failed to load question_flow.json: ${response.status}`);
  }
  cached = (await response.json()) as QuestionFlowMessages;
  return cached;
}

export async function getMessage(
  key: string,
  vars: Record<string, string> = {},
): Promise<string> {
  const messages = await load();
  const template = messages[key];
  if (template === undefined) {
    throw new Error(`Unknown question flow key: ${key}`);
  }
  return template.replace(/\{(\w+)\}/g, (_, name: string) => vars[name] ?? "");
}
