export type RobotMode =
  | "idle"
  | "wake_detected"
  | "listening"
  | "processing"
  | "speaking"
  | "error";

export type RobotState = {
  mode: RobotMode;
  wakeWordDetected: boolean;
  commandText: string;
};