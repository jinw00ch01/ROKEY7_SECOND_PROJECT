const TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech";
const DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB";
const DEFAULT_MODEL_ID = "eleven_flash_v2_5";
const DEFAULT_LANGUAGE_CODE = "ko";
const DEFAULT_OUTPUT_FORMAT = "mp3_44100_128";

type TtsOptions = {
  apiKey: string;
  voiceId?: string;
  modelId?: string;
  languageCode?: string;
  outputFormat?: string;
};

export async function speak(text: string, options: TtsOptions): Promise<void> {
  const clean = text?.trim();
  if (!clean) return;
  if (!options.apiKey) {
    console.warn("ElevenLabs API key missing; skipping TTS.");
    return;
  }

  const voiceId = options.voiceId ?? DEFAULT_VOICE_ID;
  const outputFormat = options.outputFormat ?? DEFAULT_OUTPUT_FORMAT;
  const url = `${TTS_URL}/${encodeURIComponent(voiceId)}?output_format=${encodeURIComponent(outputFormat)}`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "xi-api-key": options.apiKey,
      "Content-Type": "application/json",
      Accept: "audio/mpeg",
    },
    body: JSON.stringify({
      text: clean,
      model_id: options.modelId ?? DEFAULT_MODEL_ID,
      language_code: options.languageCode ?? DEFAULT_LANGUAGE_CODE,
      voice_settings: {
        stability: 0.5,
        similarity_boost: 0.75,
        style: 0.0,
        use_speaker_boost: true,
      },
    }),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    console.warn(`ElevenLabs TTS failed (${response.status}): ${detail}`);
    return;
  }

  const blob = await response.blob();
  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);

  await new Promise<void>((resolve) => {
    const cleanup = () => {
      URL.revokeObjectURL(audioUrl);
      resolve();
    };
    audio.addEventListener("ended", cleanup, { once: true });
    audio.addEventListener("error", cleanup, { once: true });
    audio.play().catch((error) => {
      console.warn("TTS playback failed:", error);
      cleanup();
    });
  });
}
