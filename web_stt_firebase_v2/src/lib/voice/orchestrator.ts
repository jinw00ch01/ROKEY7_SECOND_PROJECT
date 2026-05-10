import type { CategoryId, Intensity, NutComboItem } from "../types";
import {
  analyzeIntensity,
  analyzeState,
  matchMenuIntensity,
  matchMenuState,
  type IntensityAnalysis,
  type StateAnalysis,
} from "./llm";
import { getMessage } from "./questionFlow";
import {
  buildCombo,
  extractCategories,
  extractIntensity,
  formatComboText,
  loadCategoriesConfig,
  loadComboRules,
} from "./recommendation";
import { getMicrophoneStream, recordAudio } from "./recorder";
import {
  buildTheme,
  publishCompleted,
  publishDispatching,
  publishError,
  publishQuestion,
  publishRecommendationResult,
  publishTranscript,
  resetSession,
  updateDisplayState,
  type SessionOrder,
} from "./session";
import { speak } from "./tts";
import { transcribe } from "./whisper";
import { listenForWakeWord, type WakeWordController } from "./wakeWord";

const RECORD_DURATION_MS = 5000;

function generateRequestId(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  );
}

const MENU_ASK_STATE =
  "오늘 컨디션을 골라주세요. " +
  "1번 피로, 2번 혈당, 3번 다이어트, 4번 집중. " +
  "번호나 키워드로 답해주세요.";
const MENU_ASK_INTENSITY =
  "정도를 골라주세요. 1번 약하게, 2번 보통, 3번 많이. " +
  "번호나 키워드로 답해주세요.";

export type OrchestratorConfig = {
  openaiApiKey: string;
  elevenLabsApiKey: string;
  promptMode?: "freeform" | "menu";
  ttsEnabled?: boolean;
  waitForWake?: boolean;
  /** Hook that fires after a successful order (mirrors dispatch_callback). */
  onDispatch?: (order: SessionOrder) => Promise<void> | void;
  /** Polling hook used between async steps to check for cancellation. */
  shouldContinue?: () => boolean;
};

export type OrchestratorHandle = {
  result: Promise<SessionOrder | null>;
  cancel: () => void;
};

class CancelledError extends Error {
  constructor() {
    super("Cancelled");
    this.name = "CancelledError";
  }
}

export function runRecommendationFlow(
  config: OrchestratorConfig,
): OrchestratorHandle {
  let cancelled = false;
  let activeWake: WakeWordController | null = null;
  let activeStream: MediaStream | null = null;

  const ttsEnabled = config.ttsEnabled !== false;

  const checkCancel = () => {
    if (cancelled) throw new CancelledError();
    if (config.shouldContinue && !config.shouldContinue()) {
      throw new CancelledError();
    }
  };

  const sayIfEnabled = async (text: string) => {
    if (!ttsEnabled) return;
    try {
      await speak(text, { apiKey: config.elevenLabsApiKey });
    } catch (error) {
      console.warn("TTS playback failed:", error);
    }
  };

  const listen = async (
    label: string,
    transcribingState: "transcribing_state" | "transcribing_intensity",
  ): Promise<string> => {
    checkCancel();
    if (!activeStream) {
      activeStream = await getMicrophoneStream();
    }
    const audio = await recordAudio(RECORD_DURATION_MS, activeStream);
    checkCancel();
    await updateDisplayState(transcribingState);
    const text = await transcribe(audio, config.openaiApiKey);
    console.info(`[STT] ${label}: ${text}`);
    return text;
  };

  const releaseStream = () => {
    if (activeStream) {
      for (const track of activeStream.getTracks()) track.stop();
      activeStream = null;
    }
  };

  const requestId = generateRequestId();

  const result = (async (): Promise<SessionOrder | null> => {
    await resetSession();

    try {
      if (config.waitForWake !== false) {
        activeWake = listenForWakeWord();
        const detected = await activeWake.promise;
        activeWake = null;
        checkCancel();
        if (!detected) {
          await updateDisplayState("idle");
          return null;
        }
      }

      const wakeResponse = await getMessage("wake_response");
      await publishQuestion(wakeResponse, "wake_detected");
      await sayIfEnabled(wakeResponse);

      const mode = config.promptMode ?? "freeform";
      const askState =
        mode === "menu" ? MENU_ASK_STATE : await getMessage("ask_state");
      await publishQuestion(askState, "asking_state");
      await sayIfEnabled(askState);
      await updateDisplayState("listening_state");

      let stateText = await listen("상태", "transcribing_state");
      await publishTranscript(stateText);

      const stateResult = await resolveState(stateText, config.openaiApiKey, mode);

      let category = stateResult.category;
      let reasoningMessage = stateResult.reasoning_message || "상태를 파악하기 어렵네요.";

      if (mode === "menu" && !category) {
        const retryPrompt = await getMessage("retry_state");
        await publishQuestion(retryPrompt, "asking_state");
        await sayIfEnabled(retryPrompt);
        await updateDisplayState("listening_state");

        const retryText = await listen("상태", "transcribing_state");
        const merged = [stateText, retryText].filter(Boolean).join(" ");
        await publishTranscript(merged);
        stateText = merged.trim();

        const retryResult = await resolveState(retryText, config.openaiApiKey, mode);
        category = retryResult.category;
        reasoningMessage = retryResult.reasoning_message || reasoningMessage;
      }

      const categories: CategoryId[] = category ? [category] : [];

      if (!categories.length) {
        const order: SessionOrder = {
          request_id: requestId,
          recognized_text: stateText,
          categories: [],
          intensity: "normal",
          combo: [],
          combo_text: "",
          success: false,
        };
        await publishError("상태 카테고리를 찾지 못했습니다.");
        await sayIfEnabled(reasoningMessage);
        return order;
      }

      await updateDisplayState("asking_intensity", {
        categories,
        theme: buildTheme(categories, []),
      });

      const simpleIntensityPrompt =
        mode === "menu" ? MENU_ASK_INTENSITY : await getMessage("ask_intensity");
      const combinedTtsPrompt =
        mode === "menu"
          ? simpleIntensityPrompt
          : `${reasoningMessage} ${simpleIntensityPrompt}`;

      await publishQuestion(simpleIntensityPrompt, "asking_intensity");
      await sayIfEnabled(combinedTtsPrompt);
      await updateDisplayState("listening_intensity");

      let intensityText = await listen("강도", "transcribing_intensity");
      await publishTranscript(
        [stateText, intensityText].filter(Boolean).join(" "),
      );

      const intensityResult = await resolveIntensity(
        intensityText,
        config.openaiApiKey,
        mode,
      );

      let intensity: Intensity = intensityResult.intensity || "normal";
      let intensityReasoning =
        intensityResult.reasoning_message || "적당량으로 준비해 드릴게요.";

      if (mode === "menu" && !matchMenuIntensity(intensityText)) {
        const retryPrompt = await getMessage("retry_intensity");
        await publishQuestion(retryPrompt, "asking_intensity");
        await sayIfEnabled(retryPrompt);
        await updateDisplayState("listening_intensity");

        const retryText = await listen("강도", "transcribing_intensity");
        await publishTranscript(
          [stateText, intensityText, retryText].filter(Boolean).join(" "),
        );
        intensityText = [intensityText, retryText].filter(Boolean).join(" ").trim();

        const retryResult = await resolveIntensity(
          retryText,
          config.openaiApiKey,
          mode,
        );
        intensity = retryResult.intensity || intensity;
        intensityReasoning = retryResult.reasoning_message || intensityReasoning;
      }

      await updateDisplayState("recommending");

      const [categoriesConfig, comboRules] = await Promise.all([
        loadCategoriesConfig(),
        loadComboRules(),
      ]);

      const combo: NutComboItem[] = buildCombo(
        categories,
        intensity,
        comboRules,
        categoriesConfig,
      );
      const comboText = formatComboText(combo);
      const recognizedText = [stateText, intensityText].filter(Boolean).join(" ");
      const success = categories.length > 0 && combo.length > 0;

      const simpleConfirm = await getMessage("confirm_template", {
        combo_text: comboText,
      });
      const confirmTts = `${intensityReasoning} ${simpleConfirm}`;

      const order: SessionOrder = {
        request_id: requestId,
        recognized_text: recognizedText,
        categories,
        intensity,
        combo,
        combo_text: comboText,
        confirm_message: simpleConfirm,
        success,
      };

      if (success) {
        await publishRecommendationResult(order);
        await sayIfEnabled(confirmTts);

        if (config.onDispatch) {
          await publishDispatching(order);
          await config.onDispatch(order);
          await publishCompleted(order);
        }
      } else {
        await publishError("추천 결과를 생성하지 못했습니다.");
      }

      return order;
    } catch (error) {
      if (error instanceof CancelledError) {
        await updateDisplayState("idle");
        return null;
      }
      const message = error instanceof Error ? error.message : String(error);
      await publishError(message);
      throw error;
    } finally {
      releaseStream();
      if (activeWake) activeWake.cancel();
    }
  })();

  return {
    result,
    cancel: () => {
      cancelled = true;
      if (activeWake) activeWake.cancel();
      releaseStream();
    },
  };
}

async function resolveState(
  text: string,
  apiKey: string,
  mode: "freeform" | "menu",
): Promise<StateAnalysis> {
  if (mode === "menu") {
    const canonical = matchMenuState(text);
    if (canonical) {
      return { category: canonical, reasoning_message: "" };
    }
    return { category: "", reasoning_message: "" };
  }

  // Freeform: keyword fast-path keeps us off the LLM if a strong keyword
  // already matches; otherwise call OpenAI.
  const config = await loadCategoriesConfig();
  const matched = extractCategories(text, config);
  if (matched.length === 1) {
    return { category: matched[0], reasoning_message: "" };
  }
  return analyzeState(text, apiKey);
}

async function resolveIntensity(
  text: string,
  apiKey: string,
  mode: "freeform" | "menu",
): Promise<IntensityAnalysis> {
  if (mode === "menu") {
    const canonical = matchMenuIntensity(text);
    if (canonical) {
      return { intensity: canonical, reasoning_message: "" };
    }
    return { intensity: "normal", reasoning_message: "" };
  }
  const matched = extractIntensity(text);
  if (matched !== "normal" || /보통|그냥|어느 정도/.test(text)) {
    return { intensity: matched, reasoning_message: "" };
  }
  return analyzeIntensity(text, apiKey);
}
