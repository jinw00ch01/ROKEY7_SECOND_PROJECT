import type {
  CategoryId,
  Intensity,
  NutClass,
  NutComboItem,
} from "../types";

type CategoriesConfig = {
  categories: Record<
    CategoryId,
    { label_ko: string; keywords: string[]; nut: NutClass }
  >;
};

type ComboRules = {
  intensity_counts: Record<Intensity, number>;
  max_total_count: number;
};

const VALID_INTENSITIES: Intensity[] = ["low", "normal", "high"];

const INTENSITY_KEYWORDS: Record<Intensity, string[]> = {
  low: ["조금", "약간", "살짝"],
  normal: ["보통", "그냥", "어느 정도"],
  high: ["많이", "너무", "매우", "완전", "진짜"],
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

let cachedCategories: CategoriesConfig | null = null;
let cachedRules: ComboRules | null = null;

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function loadCategoriesConfig(): Promise<CategoriesConfig> {
  if (!cachedCategories) {
    cachedCategories = await loadJson<CategoriesConfig>(
      "/config/keyword_categories.json",
    );
  }
  return cachedCategories;
}

export async function loadComboRules(): Promise<ComboRules> {
  if (!cachedRules) {
    cachedRules = await loadJson<ComboRules>("/config/nut_combo_rules.json");
  }
  return cachedRules;
}

export function extractCategories(
  text: string,
  config: CategoriesConfig,
): CategoryId[] {
  const sample = (text ?? "").trim().toLowerCase();
  if (!sample) return [];

  const matches: Array<{ index: number; category: CategoryId }> = [];
  for (const [category, info] of Object.entries(config.categories) as Array<
    [CategoryId, CategoriesConfig["categories"][CategoryId]]
  >) {
    let earliest = -1;
    for (const keyword of info.keywords) {
      const index = sample.indexOf(keyword.toLowerCase());
      if (index >= 0 && (earliest === -1 || index < earliest)) {
        earliest = index;
      }
    }
    if (earliest >= 0) matches.push({ index: earliest, category });
  }

  return matches.sort((a, b) => a.index - b.index).map((m) => m.category);
}

export function extractIntensity(text: string): Intensity {
  const sample = (text ?? "").trim().toLowerCase();
  if (!sample) return "normal";

  const matches: Array<{ index: number; intensity: Intensity }> = [];
  for (const intensity of VALID_INTENSITIES) {
    for (const keyword of INTENSITY_KEYWORDS[intensity]) {
      const index = sample.indexOf(keyword.toLowerCase());
      if (index >= 0) matches.push({ index, intensity });
    }
  }

  if (!matches.length) return "normal";
  matches.sort((a, b) => a.index - b.index);
  return matches[0].intensity;
}

export function buildCombo(
  categories: readonly CategoryId[],
  intensity: Intensity,
  rules: ComboRules,
  config: CategoriesConfig,
): NutComboItem[] {
  if (!categories.length) return [];

  const safeIntensity: Intensity =
    rules.intensity_counts[intensity] !== undefined ? intensity : "normal";
  const countPerCategory =
    rules.intensity_counts[safeIntensity] ?? rules.intensity_counts.normal ?? 2;
  const maxTotal = rules.max_total_count ?? 6;

  const counts = new Map<NutClass, number>();
  const ordered: NutClass[] = [];
  for (const category of categories) {
    const nut = config.categories[category]?.nut;
    if (!nut) continue;
    if (!counts.has(nut)) ordered.push(nut);
    counts.set(nut, (counts.get(nut) ?? 0) + countPerCategory);
  }

  let total = 0;
  for (const value of counts.values()) total += value;
  if (total > maxTotal) {
    for (let i = ordered.length - 1; i >= 0; i--) {
      const nut = ordered[i];
      while (total > maxTotal && (counts.get(nut) ?? 0) > 0) {
        counts.set(nut, (counts.get(nut) ?? 0) - 1);
        total -= 1;
      }
      if (total <= maxTotal) break;
    }
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
