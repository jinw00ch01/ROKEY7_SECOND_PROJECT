import * as THREE from "three";

export type ColorCommand = "q" | "w" | "e" | "r";

export type TerrainColorTheme = {
  surfaceColor: THREE.Color;
  surfaceEmissive: THREE.Color;
  ribbonHueLow: number;
  ribbonHueHigh: number;
  ribbonSaturationLow: number;
  ribbonSaturationHigh: number;
  ribbonLightnessLow: number;
  ribbonLightnessHigh: number;
};

export type MutableTerrainColorTheme = {
  surfaceColor: THREE.Color;
  surfaceEmissive: THREE.Color;
  ribbonHueLow: number;
  ribbonHueHigh: number;
  ribbonSaturationLow: number;
  ribbonSaturationHigh: number;
  ribbonLightnessLow: number;
  ribbonLightnessHigh: number;
};

export const colorThemes: Record<ColorCommand, TerrainColorTheme> = {
  q: {
    surfaceColor: new THREE.Color("#031b2d"),
    surfaceEmissive: new THREE.Color("#064f7d"),
    ribbonHueLow: 0.56,
    ribbonHueHigh: 0.5,
    ribbonSaturationLow: 0.74,
    ribbonSaturationHigh: 1,
    ribbonLightnessLow: 0.24,
    ribbonLightnessHigh: 0.76,
  },
  w: {
    surfaceColor: new THREE.Color("#1b0500"),
    surfaceEmissive: new THREE.Color("#681100"),
    ribbonHueLow: 0.06,
    ribbonHueHigh: 0.01,
    ribbonSaturationLow: 0.86,
    ribbonSaturationHigh: 1,
    ribbonLightnessLow: 0.18,
    ribbonLightnessHigh: 0.68,
  },
  e: {
    surfaceColor: new THREE.Color("#001509"),
    surfaceEmissive: new THREE.Color("#003b18"),
    ribbonHueLow: 0.36,
    ribbonHueHigh: 0.31,
    ribbonSaturationLow: 0.84,
    ribbonSaturationHigh: 1,
    ribbonLightnessLow: 0.2,
    ribbonLightnessHigh: 0.66,
  },
  r: {
    surfaceColor: new THREE.Color("#1d1204"),
    surfaceEmissive: new THREE.Color("#5a3508"),
    ribbonHueLow: 0.13,
    ribbonHueHigh: 0.1,
    ribbonSaturationLow: 0.68,
    ribbonSaturationHigh: 0.95,
    ribbonLightnessLow: 0.2,
    ribbonLightnessHigh: 0.62,
  },
};

export function createMutableColorTheme(
  source: TerrainColorTheme,
): MutableTerrainColorTheme {
  return {
    surfaceColor: source.surfaceColor.clone(),
    surfaceEmissive: source.surfaceEmissive.clone(),
    ribbonHueLow: source.ribbonHueLow,
    ribbonHueHigh: source.ribbonHueHigh,
    ribbonSaturationLow: source.ribbonSaturationLow,
    ribbonSaturationHigh: source.ribbonSaturationHigh,
    ribbonLightnessLow: source.ribbonLightnessLow,
    ribbonLightnessHigh: source.ribbonLightnessHigh,
  };
}

export function smoothColorTheme(
  current: MutableTerrainColorTheme,
  target: TerrainColorTheme,
  amount: number,
) {
  current.surfaceColor.lerp(target.surfaceColor, amount);
  current.surfaceEmissive.lerp(target.surfaceEmissive, amount);
  current.ribbonHueLow = THREE.MathUtils.lerp(
    current.ribbonHueLow,
    target.ribbonHueLow,
    amount,
  );
  current.ribbonHueHigh = THREE.MathUtils.lerp(
    current.ribbonHueHigh,
    target.ribbonHueHigh,
    amount,
  );
  current.ribbonSaturationLow = THREE.MathUtils.lerp(
    current.ribbonSaturationLow,
    target.ribbonSaturationLow,
    amount,
  );
  current.ribbonSaturationHigh = THREE.MathUtils.lerp(
    current.ribbonSaturationHigh,
    target.ribbonSaturationHigh,
    amount,
  );
  current.ribbonLightnessLow = THREE.MathUtils.lerp(
    current.ribbonLightnessLow,
    target.ribbonLightnessLow,
    amount,
  );
  current.ribbonLightnessHigh = THREE.MathUtils.lerp(
    current.ribbonLightnessHigh,
    target.ribbonLightnessHigh,
    amount,
  );
}
