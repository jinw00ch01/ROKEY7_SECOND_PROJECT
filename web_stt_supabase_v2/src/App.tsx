import { SceneCanvas } from "./components/SceneCanvas";
import { StatusPanel } from "./components/StatusPanel";
import { VoiceControls } from "./components/VoiceControls";
import { useRobotSession } from "./hooks/useRobotSession";
import { useVoiceOrchestrator } from "./hooks/useVoiceOrchestrator";
import {
  buildProgressIndicator,
  formatCombo,
  getDisplayText,
  mapDisplayStateToSceneMode,
  showError,
  showTranscript,
} from "./lib/display/displayState";
import {
  buildThemeStyle,
  getTerrainColorCommand,
  resolveActiveNut,
  resolveSessionTheme,
} from "./lib/display/themeStyle";

export default function App() {
  const {
    connection: sessionConnection,
    errorMessage: sessionErrorMessage,
    robotSession,
  } = useRobotSession();
  const {
    errorMessage: voiceErrorMessage,
    isActive: isVoiceActive,
    phase: voicePhase,
    start: startVoice,
    stop: stopVoice,
    wakeWordSupported,
  } = useVoiceOrchestrator();

  const activeNut = resolveActiveNut(robotSession);
  const terrainColorCommand = getTerrainColorCommand(activeNut);
  const themeStyle = buildThemeStyle(resolveSessionTheme(robotSession));
  const sceneMode = mapDisplayStateToSceneMode(robotSession.display_state);
  const displayText = getDisplayText(robotSession);
  const progress = buildProgressIndicator(robotSession.display_state);
  const transcriptDisplay = showTranscript(robotSession.transcript);
  const comboDisplay = formatCombo(robotSession.combo, robotSession.combo_text);
  const errorText = robotSession.error ? showError(robotSession.error) : "";
  const isListening =
    robotSession.display_state === "listening_job" ||
    robotSession.display_state === "listening_satiety";
  const isLoading = robotSession.display_state === "recommending";

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: themeStyle.backgroundColor,
        position: "relative",
        overflow: "hidden",
        transition: "background 600ms ease",
      }}
    >
      <SceneCanvas
        displayState={robotSession.display_state}
        sceneMode={sceneMode}
        terrainColorCommand={terrainColorCommand}
        themeStyle={themeStyle}
      />

      <div
        style={{
          position: "absolute",
          top: 24,
          left: 24,
          color: "rgba(235, 248, 255, 0.94)",
          fontFamily: "sans-serif",
          textAlign: "left",
          pointerEvents: "none",
          textShadow: "0 2px 12px rgba(0, 0, 0, 0.7)",
        }}
      >
        <h1 style={{ margin: 0, fontSize: 28, color: "inherit" }}>LOKI</h1>
        <p>Session: {sessionConnection}</p>
        {sessionErrorMessage ? <p>Session error: {sessionErrorMessage}</p> : null}

        <StatusPanel
          displayState={robotSession.display_state}
          headline={displayText.headline}
          message={displayText.message}
          progress={progress}
          isListening={isListening}
          isLoading={isLoading}
          transcript={transcriptDisplay}
          combo={comboDisplay}
          errorText={errorText}
          themeStyle={themeStyle}
        />

        <VoiceControls
          isActive={isVoiceActive}
          onStart={startVoice}
          onStop={stopVoice}
          phase={voicePhase}
          wakeWordSupported={wakeWordSupported}
          errorMessage={voiceErrorMessage}
        />

        <p>Active Nut: {activeNut || "none"}</p>
        <p>Color: {terrainColorCommand.toUpperCase()}</p>
      </div>
    </div>
  );
}
