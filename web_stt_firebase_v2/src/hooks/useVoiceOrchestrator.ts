import { useCallback, useEffect, useRef, useState } from "react";
import {
  runRecommendationFlow,
  type OrchestratorHandle,
} from "../lib/voice/orchestrator";
import { dispatchToTaskManager } from "../lib/voice/rosbridge";
import { isWakeWordSupported } from "../lib/voice/wakeWord";

type VoicePhase = "idle" | "running" | "error";

type EnvShape = {
  VITE_OPENAI_API_KEY?: string;
  VITE_ELEVENLABS_API_KEY?: string;
  VITE_PROMPT_MODE?: string;
  VITE_TTS_ENABLED?: string;
  VITE_ROSBRIDGE_URL?: string;
};

const DISABLED_VALUES = new Set(["0", "false", "no", "off"]);

function readEnv(): {
  openaiApiKey: string;
  elevenLabsApiKey: string;
  promptMode: "freeform" | "menu";
  ttsEnabled: boolean;
  rosbridgeUrl: string;
} {
  const env = (import.meta as unknown as { env: EnvShape }).env;
  const promptMode =
    (env.VITE_PROMPT_MODE ?? "").trim().toLowerCase() === "menu"
      ? "menu"
      : "freeform";
  const ttsValue = (env.VITE_TTS_ENABLED ?? "1").trim().toLowerCase();
  return {
    openaiApiKey: (env.VITE_OPENAI_API_KEY ?? "").trim(),
    elevenLabsApiKey: (env.VITE_ELEVENLABS_API_KEY ?? "").trim(),
    promptMode,
    ttsEnabled: !DISABLED_VALUES.has(ttsValue),
    rosbridgeUrl: (env.VITE_ROSBRIDGE_URL ?? "").trim(),
  };
}

export function useVoiceOrchestrator() {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const handleRef = useRef<OrchestratorHandle | null>(null);

  useEffect(() => {
    return () => {
      handleRef.current?.cancel();
    };
  }, []);

  const start = useCallback(async () => {
    if (handleRef.current) return;
    const env = readEnv();

    if (!env.openaiApiKey) {
      setErrorMessage("VITE_OPENAI_API_KEY is not set.");
      setPhase("error");
      return;
    }

    setErrorMessage("");
    setPhase("running");

    const handle = runRecommendationFlow({
      openaiApiKey: env.openaiApiKey,
      elevenLabsApiKey: env.elevenLabsApiKey,
      promptMode: env.promptMode,
      ttsEnabled: env.ttsEnabled,
      waitForWake: true,
      onDispatch: env.rosbridgeUrl
        ? async (order) => {
            const result = await dispatchToTaskManager(order, env.rosbridgeUrl);
            if (!result.ok) {
              console.warn("Robot dispatch failed:", result.message);
            } else {
              console.info("Robot dispatch accepted:", result.message);
            }
          }
        : undefined,
    });
    handleRef.current = handle;

    try {
      await handle.result;
      setPhase("idle");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setPhase("error");
    } finally {
      handleRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    handleRef.current?.cancel();
    handleRef.current = null;
    setPhase("idle");
  }, []);

  return {
    errorMessage,
    isActive: phase === "running",
    phase,
    start,
    stop,
    wakeWordSupported: isWakeWordSupported(),
  };
}
