import type { RecordedAudio } from "./recorder";

const WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions";

function fileExtensionFor(mimeType: string): string {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("wav")) return "wav";
  return "webm";
}

export async function transcribe(
  audio: RecordedAudio,
  apiKey: string,
  language = "ko",
): Promise<string> {
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is missing — cannot run Whisper.");
  }

  const form = new FormData();
  const filename = `speech.${fileExtensionFor(audio.mimeType)}`;
  form.append("file", audio.blob, filename);
  form.append("model", "whisper-1");
  if (language) form.append("language", language);

  const response = await fetch(WHISPER_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Whisper request failed (${response.status}): ${detail}`);
  }

  const payload = (await response.json()) as { text?: string };
  return (payload.text ?? "").trim();
}
