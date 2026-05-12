// display_state → 사용자에게 보여줄 헤드라인/메시지/progress 단계로 매핑하는
// 순수 유틸 모듈. App.tsx에서 빼낸 것 — 렌더링 컴포넌트와 분리해 두면
// 카피라이팅 변경/스텝 재정렬을 컴포넌트 건드리지 않고 할 수 있다.

import type { DisplayState, NutComboItem, RobotMode, RobotSession } from "../types";

export const DISPLAY_COPY: Record<
  DisplayState,
  { headline: string; message: string }
> = {
  idle: {
    headline: "대기 중",
    message: "호출어를 말해주세요.",
  },
  wake_detected: {
    headline: "응답 중",
    message: "맞춤 견과류 콤보를 준비합니다.",
  },
  asking_job: {
    headline: "직업 확인",
    message: "당신의 직업은 무엇인가요?",
  },
  listening_job: {
    headline: "듣는 중",
    message: "말씀을 듣고 있어요.",
  },
  transcribing_job: {
    headline: "변환 중",
    message: "들은 내용을 분석하고 있어요.",
  },
  asking_satiety: {
    headline: "포만감 확인",
    message: "현재 포만감은 어느 정도인가요?",
  },
  listening_satiety: {
    headline: "듣는 중",
    message: "포만감을 듣고 있어요.",
  },
  transcribing_satiety: {
    headline: "변환 중",
    message: "들은 내용을 분석하고 있어요.",
  },
  recommending: {
    headline: "분석 중",
    message: "직업과 포만감에 맞는 견과류 콤보를 고르고 있어요.",
  },
  result_ready: {
    headline: "추천 완료",
    message: "맞춤 견과류 콤보가 준비되었습니다.",
  },
  dispatching: {
    headline: "로봇 동작 중",
    message: "로봇이 견과류를 준비하고 있어요.",
  },
  completed: {
    headline: "완료",
    message: "준비가 완료되었습니다.",
  },
  error: {
    headline: "오류",
    message: "문제가 발생했습니다.",
  },
};

export const PROGRESS_STEPS: Array<{
  label: string;
  states: DisplayState[];
}> = [
  { label: "호출", states: ["idle", "wake_detected"] },
  {
    label: "직업 질문",
    states: ["asking_job", "listening_job", "transcribing_job"],
  },
  {
    label: "포만감 질문",
    states: ["asking_satiety", "listening_satiety", "transcribing_satiety"],
  },
  { label: "추천", states: ["recommending", "result_ready"] },
  { label: "로봇 동작 중", states: ["dispatching"] },
  { label: "완료", states: ["completed"] },
];

export function showTranscript(transcript: string): string {
  return transcript || "";
}

export function showError(error: string): string {
  return error || "문제가 발생했습니다. 다시 시도해주세요.";
}

export function formatCombo(
  combo: readonly NutComboItem[],
  comboText: string,
): string {
  if (comboText) return comboText;
  if (!combo.length) return "";
  return combo.map((item) => `${item.nut} ${item.count}`).join(", ");
}

// 각 display_state에서 부제(message)로 노출할 source를 명시. session.question /
// session.transcript는 asking/listening/transcribing 사이클에서만 의미가 있고,
// 그 뒤(recommending/dispatching/completed)에도 row에 남아 있어서 — 가드 없이
// fallback 체인에 넣으면 "로봇 동작 중" 상태에서도 "포만감이 어떠신가요?"가
// 그대로 보이는 회귀가 발생한다. 그래서 상태별로 허용 source를 강하게 좁힌다.
const QUESTION_STATES: ReadonlySet<DisplayState> = new Set([
  "wake_detected",
  "asking_job",
  "listening_job",
  "asking_satiety",
  "listening_satiety",
]);

const TRANSCRIPT_STATES: ReadonlySet<DisplayState> = new Set([
  "transcribing_job",
  "transcribing_satiety",
]);

// completed는 의도적으로 빼둔다 — 빼지 않으면 부제가 result_ready의 confirm_message
// ("직업과 포만감에 맞춰 ...를 준비해드릴게요")로 남아 headline만 "완료"로 바뀌어도
// 부제는 그대로라 완료 신호가 시각적으로 안 뜬다. fallback DISPLAY_COPY.completed
// ("준비가 완료되었습니다.")로 떨어지게 두면 headline + 메시지가 둘 다 바뀐다.
// combo 정보는 StatusPanel 하단의 별도 `Combo:` 라인이 계속 보여주므로 손실 없음.
const COMBO_STATES: ReadonlySet<DisplayState> = new Set(["result_ready"]);

export function getDisplayText(session: RobotSession): {
  headline: string;
  message: string;
} {
  const fallback = DISPLAY_COPY[session.display_state] ?? DISPLAY_COPY.idle;

  if (session.display_state === "error") {
    return {
      headline: fallback.headline,
      message: session.error || fallback.message,
    };
  }

  const sources: string[] = [];
  if (QUESTION_STATES.has(session.display_state) && session.question) {
    sources.push(session.question);
  }
  if (TRANSCRIPT_STATES.has(session.display_state) && session.transcript) {
    sources.push(session.transcript);
  }
  if (COMBO_STATES.has(session.display_state)) {
    const comboMessage =
      session.confirm_message ||
      session.combo_text ||
      formatCombo(session.combo, "");
    if (comboMessage) sources.push(comboMessage);
  }

  return {
    headline: fallback.headline,
    message: sources[0] || fallback.message,
  };
}

export type ProgressStep = {
  label: string;
  states: DisplayState[];
  isActive: boolean;
  isComplete: boolean;
};

// floorIndex: 같은 사이클 안에서 이미 도달한 최고 step. progress bar는 단조
// 증가해야 사용자가 "차례대로 채워진다"는 느낌을 받는다. 그런데 display_state
// 만으로 매 렌더링마다 새로 계산하면, 일시적으로 인덱스가 낮은 상태로 떨어질
// 때(예: "error"는 어느 step에도 속하지 않아 activeIndex=-1이 되어 모든 바가
// 꺼진다) 누적된 바들이 일제히 사라진다. App.tsx에서 useState/useEffect로
// 도달한 최고 step을 기억해 이 인자로 넘기면, 일시 회귀에도 바가 유지된다.
// idle로 돌아갈 때 외부에서 floorIndex=-1로 리셋한다.
export function buildProgressIndicator(
  displayState: DisplayState,
  floorIndex: number = -1,
): ProgressStep[] {
  const currentIndex = PROGRESS_STEPS.findIndex((step) =>
    step.states.includes(displayState),
  );
  const activeIndex = Math.max(currentIndex, floorIndex);
  const completedIndex =
    displayState === "completed"
      ? PROGRESS_STEPS.length - 1
      : Math.max(activeIndex - 1, -1);

  return PROGRESS_STEPS.map((step, index) => ({
    ...step,
    isActive: index === activeIndex,
    isComplete: index <= completedIndex,
  }));
}

export function findProgressIndex(displayState: DisplayState): number {
  return PROGRESS_STEPS.findIndex((step) =>
    step.states.includes(displayState),
  );
}

export function mapDisplayStateToSceneMode(state: DisplayState): RobotMode {
  if (state === "wake_detected") return "wake_detected";
  if (state === "asking_job") return "speaking";
  if (state === "listening_job") return "listening";
  if (state === "transcribing_job") return "transcribing";
  if (state === "asking_satiety") return "speaking";
  if (state === "listening_satiety") return "listening";
  if (state === "transcribing_satiety") return "transcribing";
  if (state === "recommending") return "processing";
  if (state === "result_ready") return "processing";
  if (state === "dispatching") return "processing";
  if (state === "completed") return "completed";
  if (state === "error") return "error";
  return "idle";
}
