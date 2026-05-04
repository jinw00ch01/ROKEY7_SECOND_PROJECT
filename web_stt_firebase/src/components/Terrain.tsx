import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { RobotMode } from "../lib/types";
import type { ColorCommand } from "./terrain/colorThemes";
import {
  colorThemes,
  createMutableColorTheme,
  smoothColorTheme,
} from "./terrain/colorThemes";
import {
  createRibbonScratch,
  writeElectricEdge,
} from "./terrain/electricRibbons";
import {
  getModeIntensity,
  getTerrainHeight,
  getVertex,
  getVertexIndex,
  getVoiceWaveScale,
} from "./terrain/terrainHeight";
import {
  RIBBON_VERTEX_COUNT,
  SEGMENTS,
  TERRAIN_SIZE,
  VERTICES_PER_SIDE,
} from "./terrain/terrainConstants";

type TerrainProps = {
  colorCommand: string;
  mode: RobotMode;
};

function isColorCommand(value: string): value is ColorCommand {
  return value === "q" || value === "w" || value === "e" || value === "r";
}

export function Terrain({ colorCommand, mode }: TerrainProps) {
  const terrainMeshRef = useRef<THREE.Mesh>(null);
  const electricMeshRef = useRef<THREE.Mesh>(null);
  const terrainMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const commandWaveScaleRef = useRef(1);
  const modeIntensityRef = useRef(0.65);
  const colorThemeRef = useRef(createMutableColorTheme(colorThemes.q));
  const ribbonBuffers = useMemo(
    () => ({
      positions: new Float32Array(RIBBON_VERTEX_COUNT * 3),
      colors: new Float32Array(RIBBON_VERTEX_COUNT * 3),
    }),
    [],
  );
  const ribbonScratch = useMemo(() => createRibbonScratch(), []);
  // Reuse temporary vectors each frame to avoid allocating thousands of objects.
  const vertexScratch = useMemo(
    () => ({
      startVertex: new THREE.Vector3(),
      endVertex: new THREE.Vector3(),
      diagonalVertex: new THREE.Vector3(),
    }),
    [],
  );

  useFrame(({ clock }, delta) => {
    if (!terrainMeshRef.current || !electricMeshRef.current) return;

    const elapsed = clock.getElapsedTime();
    const terrainScroll = elapsed * 0.42;
    const pulseTime = elapsed * 0.85;
    const targetModeIntensity = getModeIntensity(mode);
    const targetColorTheme =
      colorThemes[isColorCommand(colorCommand) ? colorCommand : "q"];
    const targetCommandWaveScale = getVoiceWaveScale(mode);
    const smoothingAmount = 1 - Math.exp(-delta * 1.45);
    const intensitySmoothingAmount = 1 - Math.exp(-delta * 1.8);
    const colorSmoothingAmount = 1 - Math.exp(-delta * 2.8);
    smoothColorTheme(
      colorThemeRef.current,
      targetColorTheme,
      colorSmoothingAmount,
    );
    if (terrainMaterialRef.current) {
      terrainMaterialRef.current.color.copy(colorThemeRef.current.surfaceColor);
      terrainMaterialRef.current.emissive.copy(
        colorThemeRef.current.surfaceEmissive,
      );
    }
    modeIntensityRef.current = THREE.MathUtils.lerp(
      modeIntensityRef.current,
      targetModeIntensity,
      intensitySmoothingAmount,
    );
    commandWaveScaleRef.current = THREE.MathUtils.lerp(
      commandWaveScaleRef.current,
      targetCommandWaveScale,
      smoothingAmount,
    );
    const modeIntensity = modeIntensityRef.current;
    const commandWaveScale = commandWaveScaleRef.current;
    const terrainGeometry = terrainMeshRef.current.geometry as THREE.PlaneGeometry;
    const positionAttribute = terrainGeometry.attributes
      .position as THREE.BufferAttribute;

    // Two noise layers create the slow rolling surface plus fine detail.
    for (let gridY = 0; gridY < VERTICES_PER_SIDE; gridY++) {
      for (let gridX = 0; gridX < VERTICES_PER_SIDE; gridX++) {
        const currentVertexIndex = getVertexIndex(gridX, gridY);
        const worldX = positionAttribute.getX(currentVertexIndex);
        const worldY = positionAttribute.getY(currentVertexIndex);
        const height = getTerrainHeight(
          gridX,
          gridY,
          terrainScroll,
          modeIntensity,
          commandWaveScale,
        );

        positionAttribute.setXYZ(currentVertexIndex, worldX, worldY, height);
      }
    }

    positionAttribute.needsUpdate = true;
    terrainGeometry.computeVertexNormals();

    const ribbonGeometry = electricMeshRef.current.geometry;
    const ribbonAttributes = {
      position: ribbonGeometry.attributes.position as THREE.BufferAttribute,
      color: ribbonGeometry.attributes.color as THREE.BufferAttribute,
    };
    let ribbonVertex = 0;

    for (let gridY = 0; gridY < SEGMENTS; gridY++) {
      for (let gridX = 0; gridX < SEGMENTS; gridX++) {
        const { startVertex, endVertex, diagonalVertex } = vertexScratch;
        getVertex(positionAttribute, gridX, gridY, startVertex);
        getVertex(positionAttribute, gridX + 1, gridY, endVertex);
        getVertex(positionAttribute, gridX, gridY + 1, diagonalVertex);

        ribbonVertex = writeElectricEdge(
          ribbonAttributes,
          ribbonVertex,
          startVertex,
          endVertex,
          pulseTime,
          modeIntensity,
          colorThemeRef.current,
          ribbonScratch,
        );
        ribbonVertex = writeElectricEdge(
          ribbonAttributes,
          ribbonVertex,
          startVertex,
          diagonalVertex,
          pulseTime,
          modeIntensity,
          colorThemeRef.current,
          ribbonScratch,
        );
        ribbonVertex = writeElectricEdge(
          ribbonAttributes,
          ribbonVertex,
          endVertex,
          diagonalVertex,
          pulseTime,
          modeIntensity,
          colorThemeRef.current,
          ribbonScratch,
        );
      }
    }

    ribbonAttributes.position.needsUpdate = true;
    ribbonAttributes.color.needsUpdate = true;
    ribbonGeometry.setDrawRange(0, ribbonVertex);
  });

  return (
    <group
      rotation={[-Math.PI / 2.7, -Math.PI / 5.5, -Math.PI / 3]}
      position={[-3, .5, 0]}
    >
      <mesh ref={terrainMeshRef}>
        <planeGeometry args={[TERRAIN_SIZE, TERRAIN_SIZE, SEGMENTS, SEGMENTS]} />
        <meshStandardMaterial
          ref={terrainMaterialRef}
          color="#020b18"
          emissive="#041f3a"
          metalness={0}
          roughness={0.85}
          transparent
          opacity={0.32}
          side={THREE.DoubleSide}
        />
      </mesh>
      <mesh ref={electricMeshRef}>
        <bufferGeometry drawRange={{ start: 0, count: RIBBON_VERTEX_COUNT }}>
          <bufferAttribute
            attach="attributes-position"
            args={[ribbonBuffers.positions, 3]}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[ribbonBuffers.colors, 3]}
          />
        </bufferGeometry>
        <meshBasicMaterial
          vertexColors
          transparent
          opacity={0.88}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          side={THREE.DoubleSide}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}
