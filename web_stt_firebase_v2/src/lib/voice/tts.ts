const TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech";
const DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB";
const DEFAULT_MODEL_ID = "eleven_flash_v2_5";
const DEFAULT_LANGUAGE_CODE = "ko";
const DEFAULT_OUTPUT_FORMAT = "mp3_44100_128";
const FALLBACK_LANG = "ko-KR";

type TtsOptions = {
  apiKey: string;
  voiceId?: string;
  modelId?: string;
  languageCode?: string;
  outputFormat?: string;
};

// Once ElevenLabs returns auth/quota status codes we stop hitting it for the
// rest of the session — the browser fallback is good enough and avoids the
// per-request latency of a guaranteed-to-fail API call.
let elevenLabsBlocked = false;

function speakWithBrowser(text: string, lang: string): Promise<void> {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return Promise.resolve();
  }
  // 동시 다발 발화 방지 — 새 utterance가 시작되면 이전 것은 끊는다.
  window.speechSynthesis.cancel();

  return new Promise<void>((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    const koreanVoice = window.speechSynthesis
      .getVoices()
      .find((voice) => voice.lang?.toLowerCase().startsWith("ko"));
    if (koreanVoice) utterance.voice = koreanVoice;

    utterance.onend = () => resolve();
    utterance.onerror = (event) => {
      console.warn("Browser TTS error:", event.error);
      resolve();
    };
    window.speechSynthesis.speak(utterance);
  });
}

async function tryElevenLabs(
  text: string,
  options: TtsOptions,
): Promise<"played" | "blocked" | "skipped"> {
  if (elevenLabsBlocked) return "blocked";

  const voiceId = options.voiceId ?? DEFAULT_VOICE_ID;
  const outputFormat = options.outputFormat ?? DEFAULT_OUTPUT_FORMAT;
  const url = `${TTS_URL}/${encodeURIComponent(voiceId)}?output_format=${encodeURIComponent(outputFormat)}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "xi-api-key": options.apiKey,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify({
        text,
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
  } catch (error) {
    console.warn("ElevenLabs TTS network error:", error);
    return "skipped";
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    console.warn(`ElevenLabs TTS failed (${response.status}): ${detail}`);
    // 401 무권한, 402 결제 필요, 429 rate-limit, 403 forbidden — 이번 세션 동안
    // 재시도 불필요한 상태 코드들. 그 외는 일시적일 수 있어 다음 호출에서 다시 시도.
    if ([401, 402, 403, 429].includes(response.status)) {
      elevenLabsBlocked = true;
      return "blocked";
    }
    return "skipped";
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
      console.warn("ElevenLabs playback failed:", error);
      cleanup();
    });
  });
  return "played";
}

export async function speak(text: string, options: TtsOptions): Promise<void> {
  const clean = text?.trim();
  if (!clean) return;

  // ElevenLabs는 "ko" 같은 짧은 코드를 받지만 Web Speech API는 BCP-47 ("ko-KR")
  // 형식을 권장. 짧은 코드면 매핑해 사용한다.
  const langMap: Record<string, string> = { ko: "ko-KR", en: "en-US" };
  const lang =
    langMap[options.languageCode ?? ""] || options.languageCode || FALLBACK_LANG;

  if (!options.apiKey) {
    await speakWithBrowser(clean, lang);
    return;
  }

  const result = await tryElevenLabs(clean, options);
  if (result === "played") return;

  // ElevenLabs blocked or skipped → browser TTS로 폴백.
  await speakWithBrowser(clean, lang);
}
