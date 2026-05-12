// 세션 상태 → THREE.js 씬에 적용할 색/조도 스타일로 변환하는 순수 모듈.
// THEME_BY_CATEGORY는 voice/session.ts의 buildTheme이 DB로 쓰는 RobotSessionTheme
// 과 정확히 같은 색을 가진다 (web → DB → web 라운드트립 시 동일한 색이 다시
// 들어오도록). 만약 한쪽만 바꾸면 dispatch 시점에 테마가 깜빡거리니 같이 갱신.

import * as THREE from "three";
import type {
  CategoryId,
  DisplayState,
  NutClass,
  RobotSession,
  RobotSessionTheme,
} from "../types";
import type { ColorCommand } from "../../components/terrain/colorThemes";

export const NUT_COLOR_COMMANDS: Record<string, ColorCommand> = {
  almond: "w",
  pistachio: "e",
  // STT가 자주 만들어내는 오인식 철자도 같은 색으로 매핑 — 다음 사이클에서
  // walnut/cashew와 겹치지 않게 일부러 별칭으로 둔다.
  pistachiio: "e",
  cashew: "r",
  walnut: "t",
};

export const DEFAULT_SESSION_THEME: RobotSessionTheme = {
  primary_category: "",
  primary_nut: "",
  primary_color: "#031B2D",
  secondary_color: "#0B3552",
  accent_color: "#30C7F2",
};

export const THEME_BY_CATEGORY: Record<CategoryId, RobotSessionTheme> = {
  fatigue: {
    primary_category: "fatigue",
    primary_nut: "cashew",
    primary_color: "#F2C879",
    secondary_color: "#FFF3D6",
    accent_color: "#D99A36",
  },
  blood_sugar: {
    primary_category: "blood_sugar",
    primary_nut: "almond",
    primary_color: "#B9855A",
    secondary_color: "#F3E1D0",
    accent_color: "#7A4E2D",
  },
  diet: {
    primary_category: "diet",
    primary_nut: "pistachio",
    primary_color: "#8BC34A",
    secondary_color: "#E8F5D2",
    accent_color: "#4F8A10",
  },
  focus: {
    primary_category: "focus",
    primary_nut: "walnut",
    primary_color: "#6D4C41",
    secondary_color: "#D7CCC8",
    accent_color: "#3E2723",
  },
};

export const CATEGORY_BY_NUT: Record<NutClass, CategoryId> = {
  almond: "blood_sugar",
  cashew: "fatigue",
  pistachio: "diet",
  walnut: "focus",
};

export type ThemeStyle = {
  accentColor: string;
  backgroundColor: string;
  borderColor: string;
  lightColor: string;
  panelBackground: string;
  primaryColor: string;
  secondaryColor: string;
  terrainTheme: RobotSessionTheme;
};

export function buildThemeStyle(theme: RobotSessionTheme): ThemeStyle {
  // 세 색이 다 유효한지 확인 — 하나라도 깨졌으면 default로 안전하게 후퇴.
  let safeTheme = theme;
  try {
    new THREE.Color(theme.primary_color);
    new THREE.Color(theme.secondary_color);
    new THREE.Color(theme.accent_color);
  } catch (error) {
    console.warn("Failed to apply session theme; using default theme.", error);
    safeTheme = DEFAULT_SESSION_THEME;
  }

  const backgroundColor = new THREE.Color(safeTheme.primary_color)
    .lerp(new THREE.Color("#050505"), 0.78)
    .getStyle();

  return {
    accentColor: safeTheme.accent_color,
    backgroundColor,
    borderColor: `${safeTheme.accent_color}88`,
    lightColor: safeTheme.secondary_color,
    panelBackground: `${safeTheme.primary_color}18`,
    primaryColor: safeTheme.primary_color,
    secondaryColor: safeTheme.secondary_color,
    terrainTheme: safeTheme,
  };
}

export function resolveSessionTheme(session: RobotSession): RobotSessionTheme {
  // dispatch 진행 중에는 status bridge가 채운 robot_target_class가 가장
  // 권위 있다 (현재 픽 중인 너트). publishDispatching에서 stale 값을 비워두기
  // 때문에 status bridge가 새 값을 쓸 때까지는 아래 fallback으로 자연스럽게
  // 흘러간다 — session.ts publishDispatching 주석 참고.
  if (session.display_state === "dispatching" && session.robot_target_class) {
    const targetTheme =
      THEME_BY_CATEGORY[CATEGORY_BY_NUT[session.robot_target_class]];
    if (targetTheme) return targetTheme;
  }

  // session.categories는 추천된 견과류 이름(NutClass[]). 첫 번째 너트의
  // 카테고리를 거쳐 테마를 조회한다. combo는 보조 fallback.
  const firstCategoryNut = session.categories[0];
  const firstNut = session.combo[0]?.nut;
  return (
    (firstCategoryNut && THEME_BY_CATEGORY[CATEGORY_BY_NUT[firstCategoryNut]]) ||
    (firstNut && THEME_BY_CATEGORY[CATEGORY_BY_NUT[firstNut]]) ||
    session.theme ||
    DEFAULT_SESSION_THEME
  );
}

export function resolveActiveNut(session: RobotSession): string {
  return (
    (session.display_state === "dispatching" && session.robot_target_class) ||
    session.theme.primary_nut ||
    session.combo[0]?.nut ||
    ""
  );
}

export function getTerrainColorCommand(activeNut: string): ColorCommand {
  return NUT_COLOR_COMMANDS[activeNut] ?? "q";
}

export function getLightIntensity(state: DisplayState): number {
  if (state === "wake_detected") return 1.25;
  if (state === "listening_job" || state === "listening_satiety") return 1.55;
  if (state === "transcribing_job" || state === "transcribing_satiety")
    return 1.65;
  if (state === "recommending") return 1.7;
  if (state === "result_ready") return 1.45;
  if (state === "dispatching") return 1.6;
  if (state === "completed") return 1.35;
  if (state === "error") return 1.75;
  return 1.0;
}
