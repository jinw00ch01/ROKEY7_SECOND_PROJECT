import type * as THREE from "three";
import type { RobotMode } from "../../lib/types";
import { perlinNoise } from "./perlinNoise";
import { VERTICES_PER_SIDE } from "./terrainConstants";

export function getModeIntensity(robotMode: RobotMode) {
  if (robotMode === "wake_detected") return 1.05;
  if (robotMode === "listening") return 1.45;
  if (robotMode === "transcribing") return 1.95;
  if (robotMode === "processing") return 2.00;
  if (robotMode === "completed") return 1.15;
  if (robotMode === "error") return 2.1;
  return 0.65;
}

export function getVoiceWaveScale(robotMode: RobotMode) {
  if (robotMode === "wake_detected") return 1.1;
  if (robotMode === "listening") return 1.85;
  if (robotMode === "transcribing") return 2.7;
  if (robotMode === "processing") return 3.45;
  if (robotMode === "completed") return 1.35;
  if (robotMode === "error") return 3.1;
  return 0.75;
}

export function getVertexIndex(gridX: number, gridY: number) {
  return gridY * VERTICES_PER_SIDE + gridX;
}

export function getVertex(
  positionAttribute: THREE.BufferAttribute,
  gridX: number,
  gridY: number,
  target: THREE.Vector3,
) {
  const vertexIndex = getVertexIndex(gridX, gridY);
  return target.set(
    positionAttribute.getX(vertexIndex),
    positionAttribute.getY(vertexIndex),
    positionAttribute.getZ(vertexIndex),
  );
}

export function getTerrainHeight(
  gridX: number,
  gridY: number,
  terrainScroll: number,
  modeIntensity: number,
  commandWaveScale: number,
) {
  const baseNoise = perlinNoise(gridX * 0.1, gridY * 0.1 + terrainScroll, 0);
  const detailNoise = perlinNoise(
    gridX * 0.24,
    gridY * 0.24 + terrainScroll * 1.35,
    8.5,
  );

  return (
    ((baseNoise * 0.72 + detailNoise * 0.28) * 2 - 1) *
    modeIntensity *
    commandWaveScale
  );
}
