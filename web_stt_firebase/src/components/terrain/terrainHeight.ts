import * as THREE from "three";
import type { RobotMode } from "../../lib/types";
import { perlinNoise } from "./perlinNoise";
import { VERTICES_PER_SIDE } from "./terrainConstants";

export function getModeIntensity(robotMode: RobotMode) {
  if (robotMode === "wake_detected" || robotMode === "listening") return 1.25;
  if (robotMode === "processing") return 1.55;
  return 0.75;
}

export function getCommandWaveScale(commandText: string) {
  const commandLevel = Number.parseInt(commandText.trim(), 10);

  if (!Number.isInteger(commandLevel) || commandLevel < 1 || commandLevel > 5) {
    return 1;
  }

  // Prototype command levels: 1 is calm, 5 is the largest wave response.
  return THREE.MathUtils.mapLinear(commandLevel, 1, 5, 0.55, 5.55);
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
