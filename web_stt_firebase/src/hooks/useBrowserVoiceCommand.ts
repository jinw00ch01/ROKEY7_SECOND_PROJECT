import { useCallback, useState } from "react";

type VoicePhase = "idle" | "running" | "error";

const BRIDGE_URL = "http://127.0.0.1:8765";

async function postJson(path: string) {
  const response = await fetch(`${BRIDGE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Bridge request failed: ${response.status}`);
  }

  return response.json();
}

export function useBrowserVoiceCommand() {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  const start = useCallback(async () => {
    setErrorMessage("");
    setPhase("running");

    try {
      await postJson("/voice-audio/start");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setPhase("error");
    }
  }, []);

  const stop = useCallback(async () => {
    setErrorMessage("");

    try {
      await postJson("/voice-audio/stop");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setPhase("error");
      return;
    }

    setPhase("idle");
  }, []);

  return {
    errorMessage,
    isActive: phase === "running",
    lastHeard: "",
    phase,
    start,
    stop,
  };
}
