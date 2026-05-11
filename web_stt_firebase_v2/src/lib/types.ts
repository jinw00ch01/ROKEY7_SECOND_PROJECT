import type { Timestamp } from "firebase/firestore";

export type RobotMode =
  | "idle"
  | "wake_detected"
  | "listening"
  | "transcribing"
  | "processing"
  | "speaking"
  | "completed"
  | "error";

export type FirestoreConnection = "connecting" | "live" | "missing" | "error";

export type DisplayState =
  | "idle"
  | "wake_detected"
  | "asking_job"
  | "listening_job"
  | "transcribing_job"
  | "asking_satiety"
  | "listening_satiety"
  | "transcribing_satiety"
  | "recommending"
  | "result_ready"
  | "dispatching"
  | "completed"
  | "error";

// CategoryId는 내부 lookup(테마/색 매핑)용으로만 유지. 사용자 추천 모델에서는
// 더 이상 카테고리 개념이 노출되지 않으며, RobotSession.categories는 추천된
// 견과류(NutClass)의 배열을 담는다.
export type CategoryId = "fatigue" | "blood_sugar" | "diet" | "focus";

export type Intensity = "low" | "normal" | "high";

export type NutClass = "almond" | "cashew" | "pistachio" | "walnut";

export type NutComboItem = {
  nut: NutClass;
  count: number;
};

export type RobotSessionTheme = {
  primary_category: CategoryId | "";
  primary_nut: NutClass | "";
  primary_color: string;
  secondary_color: string;
  accent_color: string;
};

export type RobotSession = {
  display_state: DisplayState;
  question: string;
  transcript: string;
  categories: NutClass[];
  intensity: Intensity;
  combo: NutComboItem[];
  combo_text: string;
  confirm_message: string;
  success: boolean;
  theme: RobotSessionTheme;
  error: string;
  robot_state?: string;
  robot_target_class?: NutClass;
  updated_at?: string | Timestamp;
};
