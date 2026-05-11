import { useEffect, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { SESSION_ID, SESSION_TABLE, supabase } from "../lib/supabase";
import type {
  CategoryId,
  DisplayState,
  Intensity,
  NutClass,
  NutComboItem,
  SessionConnection,
  RobotSession,
  RobotSessionTheme,
} from "../lib/types";

const displayStates = new Set<DisplayState>([
  "idle",
  "wake_detected",
  "asking_job",
  "listening_job",
  "transcribing_job",
  "asking_satiety",
  "listening_satiety",
  "transcribing_satiety",
  "recommending",
  "result_ready",
  "dispatching",
  "completed",
  "error",
]);

// 테마 lookup 인덱스로만 남은 카테고리 키. 사용자 추천 모델은 직업/포만감 기반이며
// session.categories에는 추천된 견과류 이름(NutClass)이 들어간다.
const categoryIds = new Set<CategoryId>([
  "fatigue",
  "blood_sugar",
  "diet",
  "focus",
]);

const intensities = new Set<Intensity>(["low", "normal", "high"]);

const nutClasses = new Set<NutClass>([
  "almond",
  "cashew",
  "pistachio",
  "walnut",
]);

const defaultTheme: RobotSessionTheme = {
  primary_category: "",
  primary_nut: "",
  primary_color: "#031B2D",
  secondary_color: "#0B3552",
  accent_color: "#30C7F2",
};

export const defaultRobotSession: RobotSession = {
  display_state: "idle",
  question: "호출어를 말해주세요",
  transcript: "",
  categories: [],
  intensity: "normal",
  combo: [],
  combo_text: "",
  confirm_message: "",
  success: false,
  theme: defaultTheme,
  error: "",
};

function normalizeDisplayState(value: unknown): DisplayState {
  return typeof value === "string" && displayStates.has(value as DisplayState)
    ? (value as DisplayState)
    : "idle";
}

function normalizeCategories(value: unknown): NutClass[] {
  // 신규 모델: session.categories는 NutClass[] (추천된 견과류 이름 목록).
  // 구버전 문서가 fatigue 같은 CategoryId 문자열을 들고 있어도 NutClass로
  // 인정되지 않으므로 자연스럽게 걸러진다.
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is NutClass =>
    nutClasses.has(item as NutClass),
  );
}

function normalizeIntensity(value: unknown): Intensity {
  return typeof value === "string" && intensities.has(value as Intensity)
    ? (value as Intensity)
    : "normal";
}

function normalizeCombo(value: unknown): NutComboItem[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;

      const candidate = item as Partial<NutComboItem>;
      if (!nutClasses.has(candidate.nut as NutClass)) return null;

      const count = Number(candidate.count);
      if (!Number.isFinite(count) || count <= 0) return null;

      return {
        nut: candidate.nut as NutClass,
        count: Math.trunc(count),
      };
    })
    .filter((item): item is NutComboItem => item !== null);
}

function normalizeTheme(value: unknown): RobotSessionTheme {
  if (!value || typeof value !== "object") return defaultTheme;
  const theme = value as Partial<RobotSessionTheme>;

  return {
    primary_category: categoryIds.has(theme.primary_category as CategoryId)
      ? (theme.primary_category as CategoryId)
      : "",
    primary_nut: nutClasses.has(theme.primary_nut as NutClass)
      ? (theme.primary_nut as NutClass)
      : "",
    primary_color: theme.primary_color || defaultTheme.primary_color,
    secondary_color: theme.secondary_color || defaultTheme.secondary_color,
    accent_color: theme.accent_color || defaultTheme.accent_color,
  };
}

export function handleRobotSessionUpdate(
  session: Partial<RobotSession> | null | undefined,
): RobotSession {
  if (!session) return defaultRobotSession;

  return {
    ...defaultRobotSession,
    display_state: normalizeDisplayState(session.display_state),
    question:
      typeof session.question === "string"
        ? session.question
        : defaultRobotSession.question,
    transcript: typeof session.transcript === "string" ? session.transcript : "",
    categories: normalizeCategories(session.categories),
    intensity: normalizeIntensity(session.intensity),
    combo: normalizeCombo(session.combo),
    combo_text: typeof session.combo_text === "string" ? session.combo_text : "",
    confirm_message:
      typeof session.confirm_message === "string" ? session.confirm_message : "",
    success: Boolean(session.success),
    theme: normalizeTheme(session.theme),
    error: typeof session.error === "string" ? session.error : "",
    // robot_state / robot_target_class은 supabase_status_bridge가 픽 단계별로
    // 갱신한다. 여기서 빠뜨리면 resolveSessionTheme이 robot_target_class를
    // 항상 undefined로 보고 첫 견과류 색에 묶여버린다 (회귀 방지).
    robot_state:
      typeof session.robot_state === "string" ? session.robot_state : undefined,
    robot_target_class: nutClasses.has(session.robot_target_class as NutClass)
      ? (session.robot_target_class as NutClass)
      : undefined,
    updated_at: session.updated_at,
  };
}

export function subscribeRobotSession(
  onUpdate: (session: RobotSession) => void,
  onError?: (error: Error) => void,
): () => void {
  // Initial fetch: Realtime channel only delivers changes, not the
  // current state. Without this the UI would show defaults until the
  // first server-side write.
  void supabase
    .from(SESSION_TABLE)
    .select("*")
    .eq("id", SESSION_ID)
    .maybeSingle()
    .then(({ data, error }) => {
      if (error) {
        onError?.(new Error(error.message));
        return;
      }
      onUpdate(handleRobotSessionUpdate(data as Partial<RobotSession> | null));
    });

  const channel: RealtimeChannel = supabase
    .channel(`robot_session:${SESSION_ID}`)
    .on(
      "postgres_changes",
      {
        event: "*",
        schema: "public",
        table: SESSION_TABLE,
        filter: `id=eq.${SESSION_ID}`,
      },
      (payload) => {
        const next = (payload.new ?? null) as Partial<RobotSession> | null;
        onUpdate(handleRobotSessionUpdate(next));
      },
    )
    .subscribe((status) => {
      if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
        onError?.(new Error(`subscription ${status.toLowerCase()}`));
      }
    });

  return () => {
    void supabase.removeChannel(channel);
  };
}

export function useRobotSession() {
  const [robotSession, setRobotSession] =
    useState<RobotSession>(defaultRobotSession);
  const [connection, setConnection] =
    useState<SessionConnection>("connecting");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const unsubscribe = subscribeRobotSession(
      (session) => {
        setRobotSession(session);
        setConnection("live");
        setErrorMessage("");
      },
      (error) => {
        setRobotSession(defaultRobotSession);
        setConnection("error");
        setErrorMessage(error.message);
      },
    );

    return () => unsubscribe();
  }, []);

  return { robotSession, connection, errorMessage };
}
