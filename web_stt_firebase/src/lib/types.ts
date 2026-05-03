import type { Timestamp } from "firebase/firestore";

export type RobotMode =
  | "idle"
  | "wake_detected"
  | "listening"
  | "transcribing"
  | "processing"
  | "speaking"
  | "error";

export type RobotState = {
  mode: RobotMode;
  wakeWordDetected: boolean;
  commandText: string;
  parsedAction?: string;
  targets?: string[];
  updatedAt?: Timestamp;
};

export type RobotStateConnection = "connecting" | "live" | "missing" | "error";
