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
  | "asking_state"
  | "listening_state"
  | "asking_job"
  | "listening_job"
  | "asking_intensity"
  | "listening_intensity"
  | "asking_satiety"
  | "listening_satiety"
  | "recommending"
  | "result_ready"
  | "dispatching"
  | "completed"
  | "error";

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
  job?: string;
  satiety?: string;
  categories: CategoryId[];
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
