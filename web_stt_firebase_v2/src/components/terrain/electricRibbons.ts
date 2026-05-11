import * as THREE from "three";
import type { MutableTerrainColorTheme } from "./colorThemes";
import { perlinNoise } from "./perlinNoise";
import {
  CURVE_STEPS,
  MAX_RIBBON_WIDTH,
  MIN_RIBBON_WIDTH,
} from "./terrainConstants";

export type RibbonAttributes = {
  position: THREE.BufferAttribute;
  color: THREE.BufferAttribute;
};

export type RibbonScratch = {
  midpoint: THREE.Vector3;
  edgeDirection: THREE.Vector3;
  edgeNormal: THREE.Vector3;
  firstControlPoint: THREE.Vector3;
  secondControlPoint: THREE.Vector3;
  previousCurvePoint: THREE.Vector3;
  nextCurvePoint: THREE.Vector3;
  color: THREE.Color;
};

export function createRibbonScratch(): RibbonScratch {
  return {
    midpoint: new THREE.Vector3(),
    edgeDirection: new THREE.Vector3(),
    edgeNormal: new THREE.Vector3(),
    firstControlPoint: new THREE.Vector3(),
    secondControlPoint: new THREE.Vector3(),
    previousCurvePoint: new THREE.Vector3(),
    nextCurvePoint: new THREE.Vector3(),
    color: new THREE.Color(),
  };
}

function writeRibbonVertex(
  ribbonAttributes: RibbonAttributes,
  ribbonVertex: number,
  point: THREE.Vector3,
  offsetX: number,
  offsetY: number,
  color: THREE.Color,
) {
  ribbonAttributes.position.setXYZ(
    ribbonVertex,
    point.x + offsetX,
    point.y + offsetY,
    point.z + 0.04,
  );
  ribbonAttributes.color.setXYZ(ribbonVertex, color.r, color.g, color.b);
}

function writeRibbonSegment(
  ribbonAttributes: RibbonAttributes,
  ribbonVertex: number,
  from: THREE.Vector3,
  to: THREE.Vector3,
  pulseTime: number,
  basePulse: number,
  colorTheme: MutableTerrainColorTheme,
  color: THREE.Color,
) {
  const segmentX = to.x - from.x;
  const segmentY = to.y - from.y;
  const segmentLength = Math.hypot(segmentX, segmentY);

  if (segmentLength === 0) return ribbonVertex;

  const segmentMidpointX = (from.x + to.x) * 0.5;
  const segmentMidpointY = (from.y + to.y) * 0.5;
  const segmentMidpointZ = (from.z + to.z) * 0.5;
  const heightFactor = THREE.MathUtils.clamp(
    THREE.MathUtils.mapLinear(segmentMidpointZ, -1.35, 1.75, 0, 1),
    0,
    1,
  );
  const liftedHeightFactor = heightFactor ** 1.7;
  const thicknessNoise = perlinNoise(
    segmentMidpointX * 1.45 + 42,
    segmentMidpointY * 1.45 + 42,
    pulseTime * 1.15,
  );
  const thickness = THREE.MathUtils.clamp(
    THREE.MathUtils.lerp(
      MIN_RIBBON_WIDTH,
      MAX_RIBBON_WIDTH,
      liftedHeightFactor,
    ) * THREE.MathUtils.lerp(0.55, 1.55, thicknessNoise),
    MIN_RIBBON_WIDTH,
    MAX_RIBBON_WIDTH,
  );
  const thicknessFactor =
    (thickness - MIN_RIBBON_WIDTH) / (MAX_RIBBON_WIDTH - MIN_RIBBON_WIDTH);
  const hue = THREE.MathUtils.lerp(
    colorTheme.ribbonHueLow,
    colorTheme.ribbonHueHigh,
    thicknessFactor,
  );
  const saturation = THREE.MathUtils.lerp(
    colorTheme.ribbonSaturationLow,
    colorTheme.ribbonSaturationHigh,
    thicknessFactor,
  );
  const lightness =
    THREE.MathUtils.lerp(
      colorTheme.ribbonLightnessLow,
      colorTheme.ribbonLightnessHigh,
      thicknessFactor,
    ) *
    THREE.MathUtils.lerp(0.78, 1.22, basePulse);
  const halfWidth = thickness * 0.5;
  const offsetX = (-segmentY / segmentLength) * halfWidth;
  const offsetY = (segmentX / segmentLength) * halfWidth;

  color.setHSL(hue, saturation, THREE.MathUtils.clamp(lightness, 0.18, 0.72));

  // Higher curve segments become wider and brighter, with noise preventing uniform bands.
  writeRibbonVertex(ribbonAttributes, ribbonVertex, from, offsetX, offsetY, color);
  writeRibbonVertex(
    ribbonAttributes,
    ribbonVertex + 1,
    from,
    -offsetX,
    -offsetY,
    color,
  );
  writeRibbonVertex(ribbonAttributes, ribbonVertex + 2, to, offsetX, offsetY, color);
  writeRibbonVertex(
    ribbonAttributes,
    ribbonVertex + 3,
    from,
    -offsetX,
    -offsetY,
    color,
  );
  writeRibbonVertex(
    ribbonAttributes,
    ribbonVertex + 4,
    to,
    -offsetX,
    -offsetY,
    color,
  );
  writeRibbonVertex(ribbonAttributes, ribbonVertex + 5, to, offsetX, offsetY, color);

  return ribbonVertex + 6;
}

export function writeElectricEdge(
  ribbonAttributes: RibbonAttributes,
  ribbonVertex: number,
  from: THREE.Vector3,
  to: THREE.Vector3,
  pulseTime: number,
  modeIntensity: number,
  colorTheme: MutableTerrainColorTheme,
  scratch: RibbonScratch,
) {
  const {
    midpoint,
    edgeDirection,
    edgeNormal,
    firstControlPoint,
    secondControlPoint,
    previousCurvePoint,
    nextCurvePoint,
    color,
  } = scratch;

  edgeDirection.subVectors(to, from);
  midpoint.addVectors(from, to).multiplyScalar(0.5);
  edgeNormal.set(-edgeDirection.y, edgeDirection.x, 0).normalize();

  const pulse = perlinNoise(
    midpoint.x * 0.82 + 20,
    midpoint.y * 0.82 + 20,
    pulseTime,
  );
  const curl = THREE.MathUtils.lerp(-0.15, 0.45, pulse) * modeIntensity;

  // Draw each grid edge as a short bezier curve so the lines feel energized.
  firstControlPoint
    .copy(midpoint)
    .addScaledVector(edgeNormal, curl)
    .setZ(midpoint.z + curl);
  secondControlPoint
    .copy(midpoint)
    .addScaledVector(edgeNormal, -curl)
    .setZ(midpoint.z + curl);

  previousCurvePoint.copy(from);
  for (let step = 1; step <= CURVE_STEPS; step++) {
    const curveProgress = step / CURVE_STEPS;
    nextCurvePoint
      .copy(from)
      .multiplyScalar((1 - curveProgress) ** 3)
      .addScaledVector(
        firstControlPoint,
        3 * (1 - curveProgress) ** 2 * curveProgress,
      )
      .addScaledVector(
        secondControlPoint,
        3 * (1 - curveProgress) * curveProgress * curveProgress,
      )
      .addScaledVector(to, curveProgress ** 3);

    ribbonVertex = writeRibbonSegment(
      ribbonAttributes,
      ribbonVertex,
      previousCurvePoint,
      nextCurvePoint,
      pulseTime,
      pulse,
      colorTheme,
      color,
    );
    previousCurvePoint.copy(nextCurvePoint);
  }

  return ribbonVertex;
}
