import { doc, onSnapshot, serverTimestamp, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import type {
  CategoryId,
  DisplayState,
  Intensity,
  NutClass,
  NutComboItem,
  RobotSessionTheme,
} from "../types";

const SESSION_COLLECTION = "robot_session";
const SESSION_DOCUMENT = "current";

const DEFAULT_THEME: RobotSessionTheme = {
  primary_category: "",
  primary_nut: "",
  primary_color: "#031B2D",
  secondary_color: "#0B3552",
  accent_color: "#30C7F2",
};

const ERROR_THEME: RobotSessionTheme = {
  primary_category: "",
  primary_nut: "",
  primary_color: "#3A1010",
  secondary_color: "#F5C7C7",
  accent_color: "#E54848",
};

const THEMES_BY_CATEGORY: Record<CategoryId, RobotSessionTheme> = {
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

const CATEGORY_BY_NUT: Record<NutClass, CategoryId> = {
  cashew: "fatigue",
  almond: "blood_sugar",
  pistachio: "diet",
  walnut: "focus",
};

export type SessionOrder = {
  request_id: string;
  recognized_text: string;
  categories: CategoryId[];
  intensity: Intensity;
  combo: NutComboItem[];
  combo_text: string;
  confirm_message?: string;
  success: boolean;
};

export function buildTheme(
  categories: readonly CategoryId[],
  combo: readonly NutComboItem[],
): RobotSessionTheme {
  for (const category of categories) {
    if (THEMES_BY_CATEGORY[category]) return THEMES_BY_CATEGORY[category];
  }
  for (const item of combo) {
    const category = CATEGORY_BY_NUT[item.nut];
    if (category) return THEMES_BY_CATEGORY[category];
  }
  return DEFAULT_THEME;
}

function sessionRef() {
  return doc(db, SESSION_COLLECTION, SESSION_DOCUMENT);
}

async function safeUpdate(fields: Record<string, unknown>) {
  try {
    await setDoc(
      sessionRef(),
      { ...fields, updated_at: serverTimestamp() },
      { merge: true },
    );
  } catch (error) {
    console.warn("Firestore session update failed:", error);
  }
}

export async function resetSession() {
  await safeUpdate({
    display_state: "idle",
    question: "",
    transcript: "",
    categories: [],
    intensity: "normal",
    combo: [],
    combo_text: "",
    confirm_message: "",
    success: false,
    theme: DEFAULT_THEME,
    error: "",
  });
}

export async function updateDisplayState(
  state: DisplayState,
  extra: Record<string, unknown> = {},
) {
  await safeUpdate({ display_state: state, ...extra });
}

export async function publishQuestion(text: string, state: DisplayState) {
  await updateDisplayState(state, {
    question: String(text ?? ""),
    error: "",
  });
}

export async function publishTranscript(text: string) {
  await safeUpdate({ transcript: String(text ?? ""), error: "" });
}

function orderFields(order: SessionOrder, confirmMessage: string) {
  return {
    request_id: order.request_id,
    transcript: order.recognized_text,
    categories: order.categories,
    intensity: order.intensity,
    combo: order.combo,
    combo_text: order.combo_text,
    confirm_message: confirmMessage,
    success: order.success,
    theme: buildTheme(order.categories, order.combo),
    error: "",
  };
}

export async function publishRecommendationResult(order: SessionOrder) {
  const confirmMessage =
    order.confirm_message?.trim() ||
    (order.combo_text
      ? `말씀하신 상태에 맞춰 ${order.combo_text}를 준비해드릴게요.`
      : "");
  await updateDisplayState("result_ready", orderFields(order, confirmMessage));
}

export async function publishDispatching(order: SessionOrder) {
  // 이전 사이클의 robot_state(task_done 등)가 남아 있으면 곧바로 false-positive로
  // 잡혀버리므로 dispatch 직전에 비워둔다. firebase_status_bridge가 진행에 따라
  // detecting/picking/placing으로 덮어쓴다.
  await updateDisplayState("dispatching", {
    ...orderFields(order, order.confirm_message ?? ""),
    robot_state: "",
  });
}

export type RobotCompletionResult = "done" | "error" | "timeout";

export function waitForRobotCompletion(
  timeoutMs: number = 180_000,
): Promise<RobotCompletionResult> {
  return new Promise((resolve) => {
    let settled = false;
    let unsub: (() => void) | null = null;
    const finish = (result: RobotCompletionResult) => {
      if (settled) return;
      settled = true;
      try {
        unsub?.();
      } catch {
        /* noop */
      }
      clearTimeout(timer);
      resolve(result);
    };
    const timer = setTimeout(() => finish("timeout"), timeoutMs);

    unsub = onSnapshot(
      sessionRef(),
      (snapshot) => {
        const data = snapshot.data() ?? {};
        const robotState = data.robot_state;
        if (robotState === "task_done") finish("done");
        else if (robotState === "error") finish("error");
      },
      (error) => {
        console.warn("waitForRobotCompletion subscription error:", error);
        finish("error");
      },
    );
  });
}

export async function publishCompleted(order: SessionOrder) {
  await updateDisplayState(
    "completed",
    orderFields(order, order.confirm_message ?? ""),
  );
}

export async function publishError(message: string) {
  await updateDisplayState("error", {
    question: "문제가 발생했습니다. 다시 시도해주세요.",
    error: String(message || "Unknown error"),
    success: false,
    theme: ERROR_THEME,
  });
}
