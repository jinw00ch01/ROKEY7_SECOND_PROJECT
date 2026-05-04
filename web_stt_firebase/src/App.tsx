import { OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { Terrain } from "./components/Terrain";
import type { ColorCommand } from "./components/terrain/colorThemes";
import { useBrowserVoiceCommand } from "./hooks/useBrowserVoiceCommand";
import { useKeyboardCommand } from "./hooks/useKeyboardCommand";
import { useRobotState } from "./hooks/useRobotState";

const TERRAIN_VIEW_TARGET: [number, number, number] = [-2, 0, 0];
const NUT_COLOR_COMMANDS: Record<string, ColorCommand> = {
  almond: "w",
  pistachio: "e",
  pistachiio: "e",
  cashew: "r",
  walnut: "t",
};
const NUT_ALIASES: Array<[string, string]> = [
  ["almonds", "almond"],
  ["almond", "almond"],
  ["아몬드", "almond"],
  ["pistachios", "pistachio"],
  ["pistachio", "pistachio"],
  ["pistachiio", "pistachio"],
  ["피스타치오", "pistachio"],
  ["cashews", "cashew"],
  ["cashew", "cashew"],
  ["캐슈", "cashew"],
  ["walnuts", "walnut"],
  ["walnut", "walnut"],
  ["호두", "walnut"],
];

function getDetectedNut(
  targets: string[] | undefined,
  commandText: string,
): string {
  const targetNut = targets
    ?.map((target) => target.toLowerCase())
    .find((target) => NUT_COLOR_COMMANDS[target]);

  if (targetNut) {
    return targetNut;
  }

  const normalizedCommand = commandText.toLowerCase();
  const aliasMatch = NUT_ALIASES.find(([alias]) =>
    normalizedCommand.includes(alias),
  );

  return aliasMatch?.[1] ?? "";
}

function getTerrainColorCommand(activeNut: string): ColorCommand {
  return NUT_COLOR_COMMANDS[activeNut] ?? "q";
}

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
  const { keyboardCommand } = useKeyboardCommand();
  const browserVoice = useBrowserVoiceCommand();
  const {
    errorMessage: voiceErrorMessage,
    isActive: isVoiceActive,
    phase: voicePhase,
    start: startVoice,
    stop: stopVoice,
  } = browserVoice;
  const activeCommand = robotState.commandText || keyboardCommand;
  const detectedNut = getDetectedNut(
    robotState.targets,
    robotState.commandText,
  );
  const activeNut = robotState.mode === "processing" ? detectedNut : "";
  const terrainColorCommand = getTerrainColorCommand(activeNut);

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
          colorCommand={terrainColorCommand}
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
        <p>Active Nut: {activeNut || "none"}</p>
        {errorMessage ? <p>Error: {errorMessage}</p> : null}
        <p>Color: {terrainColorCommand.toUpperCase()}</p>
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
            disabled={isVoiceActive}
            onClick={startVoice}
            style={{
              background: "rgba(235, 248, 255, 0.92)",
              border: 0,
              borderRadius: 6,
              color: "#050505",
              cursor: isVoiceActive ? "default" : "pointer",
              fontSize: 14,
              fontWeight: 700,
              padding: "8px 12px",
            }}
            type="button"
          >
            Start Python Voice
          </button>
          <button
            disabled={!isVoiceActive}
            onClick={stopVoice}
            style={{
              background: "rgba(5, 5, 5, 0.62)",
              border: "1px solid rgba(235, 248, 255, 0.5)",
              borderRadius: 6,
              color: "rgba(235, 248, 255, 0.92)",
              cursor: isVoiceActive ? "pointer" : "default",
              fontSize: 14,
              fontWeight: 700,
              padding: "8px 12px",
            }}
            type="button"
          >
            Stop
          </button>
        </div>
        <p>Voice bridge: {voicePhase}</p>
        {voiceErrorMessage ? <p>Voice error: {voiceErrorMessage}</p> : null}
      </div>
    </div>
  );
}
