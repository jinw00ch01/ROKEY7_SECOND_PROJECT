export type VoiceControlsProps = {
  isActive: boolean;
  onStart: () => void;
  onStop: () => void;
  phase: string;
  wakeWordSupported: boolean;
  errorMessage: string;
};

export function VoiceControls({
  isActive,
  onStart,
  onStop,
  phase,
  wakeWordSupported,
  errorMessage,
}: VoiceControlsProps) {
  return (
    <>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 12,
          pointerEvents: "auto",
        }}
      >
        <button
          disabled={isActive}
          onClick={onStart}
          style={{
            background: "rgba(235, 248, 255, 0.92)",
            border: 0,
            borderRadius: 6,
            color: "#050505",
            cursor: isActive ? "default" : "pointer",
            fontSize: 14,
            fontWeight: 700,
            padding: "8px 12px",
          }}
          type="button"
        >
          Start Voice
        </button>
        <button
          disabled={!isActive}
          onClick={onStop}
          style={{
            background: "rgba(5, 5, 5, 0.62)",
            border: "1px solid rgba(235, 248, 255, 0.5)",
            borderRadius: 6,
            color: "rgba(235, 248, 255, 0.92)",
            cursor: isActive ? "pointer" : "default",
            fontSize: 14,
            fontWeight: 700,
            padding: "8px 12px",
          }}
          type="button"
        >
          Stop
        </button>
      </div>
      <p>Voice: {phase}</p>
      {!wakeWordSupported ? (
        <p style={{ color: "#ffd479" }}>
          Wake-word listening unsupported in this browser — use Chrome/Edge.
        </p>
      ) : null}
      {errorMessage ? <p>Voice error: {errorMessage}</p> : null}
    </>
  );
}
