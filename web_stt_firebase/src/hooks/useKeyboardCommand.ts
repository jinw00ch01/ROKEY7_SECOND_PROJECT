import { useEffect, useState } from "react";

const COMMAND_KEYS = new Set(["1", "2", "3", "4", "5"]);
const COLOR_KEYS = new Set(["q", "w", "e", "r"]);

export function useKeyboardCommand() {
  const [keyboardCommand, setKeyboardCommand] = useState("");
  const [colorCommand, setColorCommand] = useState("q");

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();

      if (COMMAND_KEYS.has(key)) {
        setKeyboardCommand(key);
        return;
      }

      if (COLOR_KEYS.has(key)) {
        setColorCommand(key);
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return { colorCommand, keyboardCommand };
}
