import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";
import type { RobotState } from "./types";

const defaultState: RobotState = {
  mode: "idle",
  wakeWordDetected: false,
  commandText: "",
};

export function useRobotState() {
  const [robotState, setRobotState] = useState<RobotState>(defaultState);

  useEffect(() => {
    const ref = doc(db, "robot_state", "loki");

    const unsubscribe = onSnapshot(ref, (snapshot) => {
      if (!snapshot.exists()) {
        setRobotState(defaultState);
        return;
      }

      setRobotState(snapshot.data() as RobotState);
    });

    return () => unsubscribe();
  }, []);

  return robotState;
}