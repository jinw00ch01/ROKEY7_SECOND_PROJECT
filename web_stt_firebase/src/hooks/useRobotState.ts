import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "../lib/firebase";
import type { RobotState, RobotStateConnection } from "../lib/types";

const defaultState: RobotState = {
  mode: "idle",
  wakeWordDetected: false,
  commandText: "",
  parsedAction: "",
  targets: [],
};

export function useRobotState() {
  const [robotState, setRobotState] = useState<RobotState>(defaultState);
  const [connection, setConnection] =
    useState<RobotStateConnection>("connecting");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const ref = doc(db, "robot_state", "loki");

    const unsubscribe = onSnapshot(
      ref,
      (snapshot) => {
        if (!snapshot.exists()) {
          setRobotState(defaultState);
          setConnection("missing");
          setErrorMessage("");
          return;
        }

        setRobotState({ ...defaultState, ...(snapshot.data() as RobotState) });
        setConnection("live");
        setErrorMessage("");
      },
      (error) => {
        setConnection("error");
        setErrorMessage(error.message);
      },
    );

    return () => unsubscribe();
  }, []);

  return { robotState, connection, errorMessage };
}
