// 한국어 요약:
//   robot_session/current 한 row에 대한 read/write/구독 헬퍼.
//   Firestore 시절의 setDoc({merge:true}) → upsert(onConflict:id), serverTimestamp()
//   → DB 트리거 touch_updated_at, onSnapshot → Realtime channel postgres_changes.
//   safeUpdate는 모든 에러를 console.warn으로 흡수한다 (UI 흐름이 단발성 DB
//   문제로 멈추면 안 됨; Firestore safeUpdate와 동일 정책).

import type {
  REALTIME_SUBSCRIBE_STATES,
  RealtimeChannel,
  RealtimePostgresChangesPayload,
} from "@supabase/supabase-js";
import { SESSION_ID, SESSION_TABLE, supabase } from "../supabase";
import type {
  CategoryId,
  DisplayState,
  Intensity,
  NutClass,
  NutComboItem,
  RobotSessionTheme,
} from "../types";

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
  categories: NutClass[];
  intensity: Intensity;
  combo: NutComboItem[];
  combo_text: string;
  confirm_message?: string;
  success: boolean;
};

export function buildTheme(
  nuts: readonly NutClass[],
  combo: readonly NutComboItem[],
): RobotSessionTheme {
  // 추천된 견과류(첫 번째 우선)의 카테고리를 테마 lookup 키로 사용.
  // CategoryId는 사용자에게 노출되지 않지만 색/테마 매핑 인덱스로 남아 있음.
  for (const nut of nuts) {
    const category = CATEGORY_BY_NUT[nut];
    if (category) return THEMES_BY_CATEGORY[category];
  }
  for (const item of combo) {
    const category = CATEGORY_BY_NUT[item.nut];
    if (category) return THEMES_BY_CATEGORY[category];
  }
  return DEFAULT_THEME;
}

async function safeUpdate(fields: Record<string, unknown>): Promise<void> {
  // updated_at은 DB의 touch_updated_at 트리거가 채운다.
  // upsert(onConflict:'id')로 row가 없으면 INSERT, 있으면 UPDATE.
  // 단일 row(id='current') 운영이라 conflict 분기는 항상 update로 흐른다.
  try {
    const { error } = await supabase
      .from(SESSION_TABLE)
      .upsert({ id: SESSION_ID, ...fields }, { onConflict: "id" });
    if (error) throw error;
  } catch (error) {
    console.warn("Supabase session update failed:", error);
  }
}

export async function resetSession(): Promise<void> {
  // robot_state / robot_target_class는 supabase_status_bridge가 채우는 필드라
  // voice flow에서는 한 번도 안 쓴 것처럼 보였지만, 비워두지 않으면 이전 사이클의
  // walnut/task_done 같은 값이 DB에 남아 다음 dispatch 시작 시 App의
  // resolveSessionTheme이 stale 값으로 잘못된 색을 띄운다.
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
    robot_state: null,
    robot_target_class: null,
  });
}

export async function updateDisplayState(
  state: DisplayState,
  extra: Record<string, unknown> = {},
): Promise<void> {
  await safeUpdate({ display_state: state, ...extra });
}

export async function publishQuestion(
  text: string,
  state: DisplayState,
): Promise<void> {
  await updateDisplayState(state, {
    question: String(text ?? ""),
    error: "",
  });
}

export async function publishTranscript(text: string): Promise<void> {
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

export async function publishRecommendationResult(
  order: SessionOrder,
): Promise<void> {
  const confirmMessage =
    order.confirm_message?.trim() ||
    (order.combo_text
      ? `직업과 포만감에 맞춰 ${order.combo_text}를 준비해드릴게요.`
      : "");
  await updateDisplayState("result_ready", orderFields(order, confirmMessage));
}

export async function publishDispatching(order: SessionOrder): Promise<void> {
  // 이전 사이클의 robot_state(task_done 등)가 남아 있으면 곧바로 false-positive로
  // 잡혀버리므로 dispatch 직전에 비워둔다. status bridge가 진행에 따라
  // detecting/picking/placing으로 덮어쓴다. robot_target_class도 같이 비워야
  // resolveSessionTheme이 새 사이클의 첫 detect~select_target 사이에서 stale
  // target nut(walnut 등)의 색을 끌고 가지 않는다 — 그 윈도우 동안에는 session.theme
  // (= buildTheme(new nuts))로 fallback되도록.
  await updateDisplayState("dispatching", {
    ...orderFields(order, order.confirm_message ?? ""),
    robot_state: null,
    robot_target_class: null,
  });
}

export type RobotCompletionResult = "done" | "error" | "timeout";

export function waitForRobotCompletion(
  timeoutMs: number = 180_000,
): Promise<RobotCompletionResult> {
  // Realtime postgres_changes (UPDATE) 구독으로 robot_state=task_done|error
  // 가 들어오면 즉시 resolve. timeoutMs 동안 신호가 없으면 'timeout'.
  // CLOSED 상태는 unsubscribe 정상 종료 신호이므로 에러로 처리하지 않는다.
  return new Promise((resolve) => {
    let settled = false;
    let channel: RealtimeChannel | null = null;

    const finish = (result: RobotCompletionResult) => {
      if (settled) return;
      settled = true;
      if (channel !== null) {
        void supabase.removeChannel(channel);
      }
      clearTimeout(timer);
      resolve(result);
    };

    const timer = setTimeout(() => finish("timeout"), timeoutMs);

    channel = supabase
      .channel(`robot_session:${SESSION_ID}:wait`)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: SESSION_TABLE,
          filter: `id=eq.${SESSION_ID}`,
        },
        (
          payload: RealtimePostgresChangesPayload<{
            robot_state?: string | null;
          }>,
        ) => {
          // payload.new는 UPDATE 이벤트에서는 행 전체, DELETE/INSERT는 다른 shape이
          // 라 union 타입이다. 우리는 event:"UPDATE"로 필터하므로 실제로는 UPDATE
          // 케이스만 도착하지만, 타입 시스템은 그걸 알지 못하니 작은 cast로 좁힌다.
          const next = (payload.new ?? null) as {
            robot_state?: string | null;
          } | null;
          const robotState = next?.robot_state;
          if (robotState === "task_done") finish("done");
          else if (robotState === "error") finish("error");
        },
      )
      .subscribe((status: REALTIME_SUBSCRIBE_STATES) => {
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          console.warn("waitForRobotCompletion subscription:", status);
          finish("error");
        }
      });
  });
}

export async function publishCompleted(order: SessionOrder): Promise<void> {
  await updateDisplayState(
    "completed",
    orderFields(order, order.confirm_message ?? ""),
  );
}

export async function publishError(message: string): Promise<void> {
  await updateDisplayState("error", {
    question: "문제가 발생했습니다. 다시 시도해주세요.",
    error: String(message || "Unknown error"),
    success: false,
    theme: ERROR_THEME,
  });
}
