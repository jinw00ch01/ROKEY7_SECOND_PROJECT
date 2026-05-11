import type { Intensity, NutClass, NutComboItem } from "../types";
import {
  analyzeJob,
  analyzeSatiety,
  matchMenuJob,
  matchMenuSatiety,
  type JobAnalysis,
  type SatietyAnalysis,
} from "./llm";
import { getMessage } from "./questionFlow";
import {
  buildCombo,
  formatComboText,
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
  waitForRobotCompletion,
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

const MENU_ASK_JOB =
  "당신의 직업을 골라주세요. " +
  "1번 교사, 2번 개발자, 3번 운동선수, 4번 학생. " +
  "번호나 키워드로 답해주세요.";
const MENU_ASK_SATIETY =
  "포만감을 골라주세요. 1번 적음, 2번 보통, 3번 배부름. " +
  "번호나 키워드로 답해주세요.";

const ALL_NUTS: NutClass[] = ["almond", "cashew", "pistachio", "walnut"];

function sampleRandomNuts(count: number): NutClass[] {
  // AI가 직업을 못 알아들었을 때 마지막 fallback: 견과류 중 무작위 N개.
  const pool = [...ALL_NUTS];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, Math.max(0, Math.min(count, pool.length)));
}

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

const RESULT_DISPLAY_MS = 5000;

export function runRecommendationFlow(
  config: OrchestratorConfig,
): OrchestratorHandle {
  let cancelled = false;
  let activeWake: WakeWordController | null = null;
  let activeStream: MediaStream | null = null;
  let idleResetTimer: ReturnType<typeof setTimeout> | null = null;

  const cancellableSleep = (ms: number) =>
    new Promise<void>((resolve) => {
      idleResetTimer = setTimeout(() => {
        idleResetTimer = null;
        resolve();
      }, ms);
    });

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
    transcribingState: "transcribing_job" | "transcribing_satiety",
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
      const askJob =
        mode === "menu" ? MENU_ASK_JOB : await getMessage("ask_job");
      await publishQuestion(askJob, "asking_job");
      await sayIfEnabled(askJob);
      await updateDisplayState("listening_job");

      let jobText = await listen("직업", "transcribing_job");
      await publishTranscript(jobText);

      const jobResult = await resolveJob(jobText, config.openaiApiKey, mode);

      let recommendedNuts = jobResult.recommended_nuts;
      let reasoningMessage =
        jobResult.reasoning_message || "직업을 파악하기 어렵네요.";

      if (mode === "menu" && !recommendedNuts.length) {
        const retryPrompt = await getMessage("retry_job");
        await publishQuestion(retryPrompt, "asking_job");
        await sayIfEnabled(retryPrompt);
        await updateDisplayState("listening_job");

        const retryText = await listen("직업", "transcribing_job");
        const merged = [jobText, retryText].filter(Boolean).join(" ");
        await publishTranscript(merged);
        jobText = merged.trim();

        const retryResult = await resolveJob(retryText, config.openaiApiKey, mode);
        recommendedNuts = retryResult.recommended_nuts;
        reasoningMessage = retryResult.reasoning_message || reasoningMessage;
      }

      if (!recommendedNuts.length) {
        // v1 동작과 일치: AI가 직업을 파악 못해도 사이클을 끊지 않고 무작위
        // 2종을 골라 진행한다. UX는 reasoningMessage로 안내.
        recommendedNuts = sampleRandomNuts(2);
        reasoningMessage =
          "직업을 정확히 파악하지 못해 무작위로 2가지를 골라 준비해 드릴게요.";
        console.info("[JobAnalyzer] empty result; random fallback:", recommendedNuts);
      }

      await updateDisplayState("asking_satiety", {
        categories: recommendedNuts,
        theme: buildTheme(recommendedNuts, []),
      });

      const simpleSatietyPrompt =
        mode === "menu" ? MENU_ASK_SATIETY : await getMessage("ask_satiety");
      const combinedTtsPrompt =
        mode === "menu"
          ? simpleSatietyPrompt
          : `${reasoningMessage} ${simpleSatietyPrompt}`;

      await publishQuestion(simpleSatietyPrompt, "asking_satiety");
      await sayIfEnabled(combinedTtsPrompt);
      await updateDisplayState("listening_satiety");

      let satietyText = await listen("포만감", "transcribing_satiety");
      await publishTranscript(
        [jobText, satietyText].filter(Boolean).join(" "),
      );

      const satietyResult = await resolveSatiety(
        satietyText,
        config.openaiApiKey,
        mode,
      );

      let satiety: Intensity = satietyResult.satiety || "normal";
      let satietyReasoning =
        satietyResult.reasoning_message || "적당량으로 준비해 드릴게요.";

      if (mode === "menu" && !matchMenuSatiety(satietyText)) {
        const retryPrompt = await getMessage("retry_satiety");
        await publishQuestion(retryPrompt, "asking_satiety");
        await sayIfEnabled(retryPrompt);
        await updateDisplayState("listening_satiety");

        const retryText = await listen("포만감", "transcribing_satiety");
        await publishTranscript(
          [jobText, satietyText, retryText].filter(Boolean).join(" "),
        );
        satietyText = [satietyText, retryText].filter(Boolean).join(" ").trim();

        const retryResult = await resolveSatiety(
          retryText,
          config.openaiApiKey,
          mode,
        );
        satiety = retryResult.satiety || satiety;
        satietyReasoning = retryResult.reasoning_message || satietyReasoning;
      }

      await updateDisplayState("recommending");

      const comboRules = await loadComboRules();
      const combo: NutComboItem[] = buildCombo(
        recommendedNuts,
        satiety,
        comboRules,
      );
      const comboText = formatComboText(combo);
      const recognizedText = [jobText, satietyText].filter(Boolean).join(" ");
      const success = recommendedNuts.length > 0 && combo.length > 0;

      const simpleConfirm = await getMessage("confirm_template", {
        combo_text: comboText,
      });
      const confirmTts = `${satietyReasoning} ${simpleConfirm}`;

      const order: SessionOrder = {
        request_id: requestId,
        recognized_text: recognizedText,
        categories: recommendedNuts,
        intensity: satiety,
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
          // /task/start 응답은 ack에 불과하다 — 실제 동작이 끝났는지는
          // firebase_status_bridge가 쓰는 robot_state=task_done/error를 봐야 안다.
          const completion = await waitForRobotCompletion();
          if (completion === "done") {
            await publishCompleted(order);
          } else if (completion === "error") {
            await publishError("로봇 동작 중 오류가 발생했습니다.");
          } else {
            await publishError("로봇 동작 응답이 시간 내에 오지 않았습니다.");
          }
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
      // publishError가 Firestore에 에러를 띄우고, finally 블록이 5초 뒤 idle로
      // reset한다. 굳이 다시 throw하지 않으면 hook은 phase를 idle로 두고 다음
      // 사이클을 받을 수 있다.
      const message = error instanceof Error ? error.message : String(error);
      console.warn("Voice flow failed:", message);
      await publishError(message);
      return null;
    } finally {
      releaseStream();
      if (activeWake) activeWake.cancel();
      // 결과 화면(완료/에러)을 잠깐 보여준 뒤 자동으로 idle로 reset해서
      // 새로고침해도 stale 상태가 남지 않도록 한다. cancel()이 들어오면
      // 타이머는 즉시 끊는다.
      if (!cancelled) {
        await cancellableSleep(RESULT_DISPLAY_MS);
      }
      try {
        await resetSession();
      } catch (error) {
        console.warn("resetSession failed at flow end:", error);
      }
    }
  })();

  return {
    result,
    cancel: () => {
      cancelled = true;
      if (idleResetTimer) {
        clearTimeout(idleResetTimer);
        idleResetTimer = null;
      }
      if (activeWake) activeWake.cancel();
      releaseStream();
    },
  };
}

async function resolveJob(
  text: string,
  apiKey: string,
  mode: "freeform" | "menu",
): Promise<JobAnalysis> {
  if (mode === "menu") {
    const canonical = matchMenuJob(text);
    if (canonical) {
      return { recommended_nuts: canonical, reasoning_message: "" };
    }
    return { recommended_nuts: [], reasoning_message: "" };
  }
  // Freeform 모드: 항상 AI에게 위임. v1은 키워드 fast-path 없이 LLM 단독 분석.
  return analyzeJob(text, apiKey);
}

async function resolveSatiety(
  text: string,
  apiKey: string,
  mode: "freeform" | "menu",
): Promise<SatietyAnalysis> {
  if (mode === "menu") {
    const canonical = matchMenuSatiety(text);
    if (canonical) {
      return { satiety: canonical, reasoning_message: "" };
    }
    return { satiety: "normal", reasoning_message: "" };
  }
  return analyzeSatiety(text, apiKey);
}
