import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Terrain } from "./Terrain";
import { useRobotState } from "./useRobotState";

export default function App() {
  const robotState = useRobotState();

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#050505" }}>
      <Canvas camera={{ position: [0, 6, 8], fov: 50 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[4, 8, 4]} intensity={1.4} />
        <Terrain mode={robotState.mode} />
        <OrbitControls />
      </Canvas>

      <div
        style={{
          position: "absolute",
          top: 24,
          left: 24,
          color: "white",
          fontFamily: "sans-serif",
        }}
      >
        <h1>LOKI</h1>
        <p>Status: {robotState.mode}</p>
        <p>Command: {robotState.commandText || "-"}</p>
      </div>
    </div>
  );
}