import type { Intensity, NutClass, NutComboItem } from "../types";

type ComboRules = {
  intensity_counts: Record<Intensity, number>;
  max_total_count: number;
};

const NUT_LABELS_KO: Record<NutClass, string> = {
  almond: "아몬드",
  cashew: "캐슈넛",
  pistachio: "피스타치오",
  walnut: "호두",
};

const COUNT_LABELS_KO: Record<number, string> = {
  1: "한 개",
  2: "두 개",
  3: "세 개",
  4: "네 개",
  5: "다섯 개",
  6: "여섯 개",
};

let cachedRules: ComboRules | null = null;

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function loadComboRules(): Promise<ComboRules> {
  if (!cachedRules) {
    cachedRules = await loadJson<ComboRules>("/config/nut_combo_rules.json");
  }
  return cachedRules;
}

export function buildCombo(
  nuts: readonly NutClass[],
  intensity: Intensity,
  rules: ComboRules,
): NutComboItem[] {
  if (!nuts.length) return [];

  const safeIntensity: Intensity =
    rules.intensity_counts[intensity] !== undefined ? intensity : "normal";
  // intensity_counts는 low=3 / normal=2 / high=1 — 포만감이 낮을수록 더 많이.
  const countPerNut =
    rules.intensity_counts[safeIntensity] ?? rules.intensity_counts.normal ?? 2;

  const counts = new Map<NutClass, number>();
  const ordered: NutClass[] = [];
  for (const nut of nuts) {
    if (!counts.has(nut)) ordered.push(nut);
    counts.set(nut, (counts.get(nut) ?? 0) + countPerNut);
  }

  return ordered
    .map((nut) => ({ nut, count: counts.get(nut) ?? 0 }))
    .filter((item) => item.count > 0);
}

export function formatComboText(combo: readonly NutComboItem[]): string {
  if (!combo.length) return "";
  const parts = combo.map((item) => {
    const label = NUT_LABELS_KO[item.nut] ?? item.nut;
    const count = COUNT_LABELS_KO[item.count] ?? `${item.count}개`;
    return `${label} ${count}`;
  });
  return parts.length === 1 ? parts[0] : parts.join("와 ");
}
