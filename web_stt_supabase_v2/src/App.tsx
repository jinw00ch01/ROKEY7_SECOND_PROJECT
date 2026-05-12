import { useState } from "react";
import { SceneCanvas } from "./components/SceneCanvas";
import { StatusPanel } from "./components/StatusPanel";
import { VoiceControls } from "./components/VoiceControls";
import { useRobotSession } from "./hooks/useRobotSession";
import { useVoiceOrchestrator } from "./hooks/useVoiceOrchestrator";
import {
  buildProgressIndicator,
  findProgressIndex,
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

  // progress bar 단조 증가용 floor. display_state가 일시적으로 어떤 step에도
  // 속하지 않는 값(예: "error", activeIndex=-1)으로 떨어져도 누적된 바가
  // 시각적으로 꺼지지 않도록, 사이클 안에서 도달한 최고 step을 기억한다.
  // idle로 돌아가면 -1로 리셋해서 새 사이클의 진행이 step 0부터 다시 차오른다.
  //
  // useEffect로 setState하는 패턴은 effect 안의 setState 안티패턴이라 React가
  // 경고한다. 대신 React가 권장하는 "prop 변화에 맞춰 render 중에 state 조정"
  // 패턴: prevDisplayState를 같이 들고 다니며 변화를 감지해 setState 호출.
  // 같은 render에서 setState한 값은 React가 즉시 다시 render할 때 반영된다.
  const [progressFloor, setProgressFloor] = useState(-1);
  const [trackedDisplayState, setTrackedDisplayState] = useState(
    robotSession.display_state,
  );
  if (robotSession.display_state !== trackedDisplayState) {
    setTrackedDisplayState(robotSession.display_state);
    if (robotSession.display_state === "idle") {
      setProgressFloor(-1);
    } else {
      const idx = findProgressIndex(robotSession.display_state);
      if (idx > progressFloor) setProgressFloor(idx);
    }
  }

  const activeNut = resolveActiveNut(robotSession);
  const terrainColorCommand = getTerrainColorCommand(activeNut);
  const themeStyle = buildThemeStyle(resolveSessionTheme(robotSession));
  const sceneMode = mapDisplayStateToSceneMode(robotSession.display_state);
  const displayText = getDisplayText(robotSession);
  const progress = buildProgressIndicator(
    robotSession.display_state,
    progressFloor,
  );
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
