import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Terrain } from "./Terrain";
import type { ColorCommand } from "./terrain/colorThemes";
import {
  getLightIntensity,
  type ThemeStyle,
} from "../lib/display/themeStyle";
import type { DisplayState, RobotMode } from "../lib/types";

const TERRAIN_VIEW_TARGET: [number, number, number] = [-2, 0, 0];

function FixedCamera() {
  // 카메라는 사용자가 OrbitControls로 잠깐 둘러봐도 마운트 직후에 한 번 고정
  // 위치/시점으로 돌려놓는다 — 새로고침해도 같은 화면에서 시작하도록.
  const { camera } = useThree();

  useEffect(() => {
    camera.position.set(0, 6.4, 13.2);
    camera.lookAt(...TERRAIN_VIEW_TARGET);
    camera.updateProjectionMatrix();
  }, [camera]);

  return null;
}

function ThemedScene({
  displayState,
  themeStyle,
}: {
  displayState: DisplayState;
  themeStyle: ThemeStyle;
}) {
  // ambient + directional 조명 두 개를 매 프레임 lerp로 부드럽게 보간한다.
  // delta 기반 감쇠라 프레임레이트가 흔들려도 같은 속도로 수렴.
  const ambientLightRef = useRef<THREE.AmbientLight>(null);
  const directionalLightRef = useRef<THREE.DirectionalLight>(null);
  const targetLightColor = useMemo(
    () => new THREE.Color(themeStyle.lightColor),
    [themeStyle.lightColor],
  );
  const targetDirectionalColor = useMemo(
    () => new THREE.Color(themeStyle.accentColor),
    [themeStyle.accentColor],
  );
  const targetLightIntensity = getLightIntensity(displayState);

  useFrame((_, delta) => {
    const amount = 1 - Math.exp(-delta * 2.4);

    if (ambientLightRef.current) {
      ambientLightRef.current.color.lerp(targetLightColor, amount);
      ambientLightRef.current.intensity = THREE.MathUtils.lerp(
        ambientLightRef.current.intensity,
        0.42 + targetLightIntensity * 0.18,
        amount,
      );
    }

    if (directionalLightRef.current) {
      directionalLightRef.current.color.lerp(targetDirectionalColor, amount);
      directionalLightRef.current.intensity = THREE.MathUtils.lerp(
        directionalLightRef.current.intensity,
        1.0 + targetLightIntensity * 0.35,
        amount,
      );
    }
  });

  return (
    <>
      <ambientLight ref={ambientLightRef} intensity={0.5} />
      <directionalLight
        ref={directionalLightRef}
        position={[4, 8, 4]}
        intensity={1.4}
      />
    </>
  );
}

export function SceneCanvas({
  displayState,
  sceneMode,
  terrainColorCommand,
  themeStyle,
}: {
  displayState: DisplayState;
  sceneMode: RobotMode;
  terrainColorCommand: ColorCommand;
  themeStyle: ThemeStyle;
}) {
  return (
    <Canvas camera={{ fov: 50 }}>
      <FixedCamera />
      <ThemedScene displayState={displayState} themeStyle={themeStyle} />
      <Terrain
        colorCommand={terrainColorCommand}
        mode={sceneMode}
        theme={themeStyle.terrainTheme}
      />
      <OrbitControls target={TERRAIN_VIEW_TARGET} />
    </Canvas>
  );
}
