import { OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { Terrain } from "./components/Terrain";
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
  const robotState = useRobotState();
  const { colorCommand, keyboardCommand } = useKeyboardCommand();
  const activeCommand = keyboardCommand || robotState.commandText;

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
          commandText={activeCommand}
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
        <p>Status: {robotState.mode}</p>
        <p>Command: {activeCommand || "-"}</p>
        <p>Color: {colorCommand.toUpperCase()}</p>
      </div>
    </div>
  );
}
