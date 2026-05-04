import { OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { Terrain } from "./components/Terrain";
import { useBrowserVoiceCommand } from "./hooks/useBrowserVoiceCommand";
import { useKeyboardCommand } from "./hooks/useKeyboardCommand";
import { useRobotState } from "./hooks/useRobotState";

const TERRAIN_VIEW_TARGET: [number, number, number] = [-2, 0, 0];

function FixedCamera() {
  const { camera } = useThree();

  useEffect(() => {
    camera.position.set(0, 6.4, 13.2);
    camera.lookAt(...TERRAIN_VIEW_TARGET);
    camera.updateProjectionMatrix();
  }, [camera]);

  return null;
}

export default function App() {
  const { robotState, connection, errorMessage } = useRobotState();
  const { colorCommand, keyboardCommand } = useKeyboardCommand();
  const browserVoice = useBrowserVoiceCommand();
  const activeCommand = robotState.commandText || keyboardCommand;

  useEffect(() => {
    const hasCompletedCommand =
      robotState.mode === "idle" &&
      (robotState.commandText || robotState.parsedAction || robotState.targets?.length);

    if (browserVoice.isActive && hasCompletedCommand) {
      browserVoice.stop();
    }
  }, [
    browserVoice.isActive,
    browserVoice.stop,
    robotState.commandText,
    robotState.mode,
    robotState.parsedAction,
    robotState.targets?.length,
  ]);

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "#050505",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Canvas camera={{ fov: 50 }}>
        <FixedCamera />
        <ambientLight intensity={0.5} />
        <directionalLight position={[4, 8, 4]} intensity={1.4} />
        <Terrain
          colorCommand={colorCommand}
          mode={robotState.mode}
        />
        <OrbitControls target={TERRAIN_VIEW_TARGET} />
      </Canvas>

      <div
        style={{
          position: "absolute",
          top: 24,
          left: 24,
          color: "rgba(235, 248, 255, 0.92)",
          fontFamily: "sans-serif",
          textAlign: "left",
          pointerEvents: "none",
          textShadow: "0 2px 12px rgba(0, 0, 0, 0.7)",
        }}
      >
        <h1 style={{ margin: 0, fontSize: 28, color: "inherit" }}>LOKI</h1>
        <p>Firebase: {connection}</p>
        <p>Status: {robotState.mode}</p>
        <p>Command: {activeCommand || "-"}</p>
        <p>Action: {robotState.parsedAction || "-"}</p>
        <p>Targets: {robotState.targets?.join(", ") || "-"}</p>
        {errorMessage ? <p>Error: {errorMessage}</p> : null}
        <p>Color: {colorCommand.toUpperCase()}</p>
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
            disabled={browserVoice.isActive}
            onClick={browserVoice.start}
            style={{
              background: "rgba(235, 248, 255, 0.92)",
              border: 0,
              borderRadius: 6,
              color: "#050505",
              cursor: browserVoice.isActive ? "default" : "pointer",
              fontSize: 14,
              fontWeight: 700,
              padding: "8px 12px",
            }}
            type="button"
          >
            Start Python Voice
          </button>
          <button
            disabled={!browserVoice.isActive}
            onClick={browserVoice.stop}
            style={{
              background: "rgba(5, 5, 5, 0.62)",
              border: "1px solid rgba(235, 248, 255, 0.5)",
              borderRadius: 6,
              color: "rgba(235, 248, 255, 0.92)",
              cursor: browserVoice.isActive ? "pointer" : "default",
              fontSize: 14,
              fontWeight: 700,
              padding: "8px 12px",
            }}
            type="button"
          >
            Stop
          </button>
        </div>
        <p>Voice bridge: {browserVoice.phase}</p>
        {browserVoice.errorMessage ? <p>Voice error: {browserVoice.errorMessage}</p> : null}
      </div>
    </div>
  );
}
