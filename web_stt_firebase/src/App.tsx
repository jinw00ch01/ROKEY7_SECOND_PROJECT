import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Terrain } from "./components/Terrain";
import type { ColorCommand } from "./components/terrain/colorThemes";
import { useBrowserVoiceCommand } from "./hooks/useBrowserVoiceCommand";
import { useRobotSession } from "./hooks/useRobotSession";
import type {
  CategoryId,
  DisplayState,
  NutComboItem,
  NutClass,
  RobotMode,
  RobotSession,
  RobotSessionTheme,
} from "./lib/types";

const TERRAIN_VIEW_TARGET: [number, number, number] = [-2, 0, 0];
const NUT_COLOR_COMMANDS: Record<string, ColorCommand> = {
  almond: "w",
  pistachio: "e",
  pistachiio: "e",
  cashew: "r",
  walnut: "t",
};
const DEFAULT_SESSION_THEME: RobotSessionTheme = {
  primary_category: "",
  primary_nut: "",
  primary_color: "#031B2D",
  secondary_color: "#0B3552",
  accent_color: "#30C7F2",
};
const THEME_BY_CATEGORY: Record<CategoryId, RobotSessionTheme> = {
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
  almond: "blood_sugar",
  cashew: "fatigue",
  pistachio: "diet",
  walnut: "focus",
};
const DISPLAY_COPY: Record<
  DisplayState,
  {
    headline: string;
    message: string;
  }
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
    message: "직업을 듣고 있어요.",
  },
  asking_satiety: {
    headline: "포만감 확인",
    message: "포만감은 어느 정도인가요?",
  },
  listening_satiety: {
    headline: "듣는 중",
    message: "포만감을 듣고 있어요.",
  },
  asking_state: {
    headline: "컨디션 확인",
    message: "오늘 컨디션은 어떤가요?",
  },
  listening_state: {
    headline: "듣는 중",
    message: "말씀을 듣고 있어요.",
  },
  asking_intensity: {
    headline: "강도 확인",
    message: "그 정도는 어느 정도인가요?",
  },
  listening_intensity: {
    headline: "듣는 중",
    message: "정도를 듣고 있어요.",
  },
  recommending: {
    headline: "분석 중",
    message: "상태에 맞는 견과류 콤보를 고르고 있어요.",
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
const PROGRESS_STEPS: Array<{
  label: string;
  states: DisplayState[];
}> = [
  { label: "호출", states: ["idle", "wake_detected"] },
  { label: "직업 질문", states: ["asking_job", "listening_job", "asking_state", "listening_state"] },
  { label: "포만감 질문", states: ["asking_satiety", "listening_satiety", "asking_intensity", "listening_intensity"] },
  { label: "추천", states: ["recommending", "result_ready"] },
  { label: "로봇 준비", states: ["dispatching"] },
  { label: "완료", states: ["completed"] },
];

function getTerrainColorCommand(activeNut: string): ColorCommand {
  return NUT_COLOR_COMMANDS[activeNut] ?? "q";
}

function showTranscript(transcript: string) {
  return transcript || "";
}

function showError(error: string) {
  return error || "문제가 발생했습니다. 다시 시도해주세요.";
}

function updateComboDisplay(combo: NutComboItem[], comboText: string) {
  if (comboText) return comboText;
  if (!combo.length) return "";

  return combo.map((item) => `${item.nut} ${item.count}`).join(", ");
}

function updateTheme(theme: RobotSessionTheme) {
  try {
    new THREE.Color(theme.primary_color);
    new THREE.Color(theme.secondary_color);
    new THREE.Color(theme.accent_color);
  } catch (error) {
    console.warn("Failed to apply Firebase theme; using default theme.", error);
    theme = DEFAULT_SESSION_THEME;
  }

  const backgroundColor = new THREE.Color(theme.primary_color)
    .lerp(new THREE.Color("#050505"), 0.78)
    .getStyle();

  return {
    accentColor: theme.accent_color,
    backgroundColor,
    borderColor: `${theme.accent_color}88`,
    lightColor: theme.secondary_color,
    panelBackground: `${theme.primary_color}18`,
    primaryColor: theme.primary_color,
    secondaryColor: theme.secondary_color,
    terrainTheme: theme,
  };
}

function getDisplayText(session: RobotSession) {
  const fallback = DISPLAY_COPY[session.display_state] ?? DISPLAY_COPY.idle;
  const comboMessage =
    session.confirm_message ||
    session.combo_text ||
    updateComboDisplay(session.combo, "");

  if (session.display_state === "error") {
    return {
      headline: fallback.headline,
      message: session.error || fallback.message,
    };
  }

  if (session.display_state === "result_ready") {
    return {
      headline: fallback.headline,
      message: comboMessage || session.question || fallback.message,
    };
  }

  return {
    headline: fallback.headline,
    message: session.question || session.transcript || comboMessage || fallback.message,
  };
}

function updateProgressIndicator(displayState: DisplayState) {
  const activeIndex = PROGRESS_STEPS.findIndex((step) =>
    step.states.includes(displayState),
  );
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

function updateDisplayPanel(session: RobotSession) {
  const text = getDisplayText(session);

  return {
    ...text,
    progress: updateProgressIndicator(session.display_state),
    sceneMode: mapDisplayStateToSceneMode(session.display_state),
  };
}

function resolveSessionTheme(session: RobotSession): RobotSessionTheme {
  const firstCategory = session.categories[0];
  const firstNut = session.combo[0]?.nut;
  const secondNut = session.combo[1]?.nut;
  const primaryTheme =
    (firstCategory && THEME_BY_CATEGORY[firstCategory]) ||
    (firstNut && THEME_BY_CATEGORY[CATEGORY_BY_NUT[firstNut]]) ||
    session.theme ||
    DEFAULT_SESSION_THEME;

  if (!secondNut) return primaryTheme;

  const secondTheme = THEME_BY_CATEGORY[CATEGORY_BY_NUT[secondNut]];
  if (!secondTheme) return primaryTheme;

  return {
    ...primaryTheme,
    accent_color: secondTheme.accent_color,
  };
}

function mapDisplayStateToSceneMode(state: DisplayState): RobotMode {
  if (state === "wake_detected") return "wake_detected";
  if (state === "asking_state" || state === "asking_job") return "speaking";
  if (state === "listening_state" || state === "listening_job") return "listening";
  if (state === "asking_intensity" || state === "asking_satiety") return "speaking";
  if (state === "listening_intensity" || state === "listening_satiety") return "listening";
  if (state === "recommending") return "processing";
  if (state === "result_ready") return "processing";
  if (state === "dispatching") return "processing";
  if (state === "completed") return "completed";
  if (state === "error") return "error";
  return "idle";
}

function setDisplayState(state: DisplayState, session: RobotSession) {
  return updateDisplayPanel({
    ...session,
    display_state: state,
  });
}

function FixedCamera() {
  const { camera } = useThree();

  useEffect(() => {
    camera.position.set(0, 6.4, 13.2);
    camera.lookAt(...TERRAIN_VIEW_TARGET);
    camera.updateProjectionMatrix();
  }, [camera]);

  return null;
}

function getLightIntensity(state: DisplayState) {
  if (state === "wake_detected") return 1.25;
  if (state === "listening_state" || state === "listening_intensity" || state === "listening_job" || state === "listening_satiety") return 1.55;
  if (state === "recommending") return 1.7;
  if (state === "result_ready") return 1.45;
  if (state === "dispatching") return 1.6;
  if (state === "completed") return 1.35;
  if (state === "error") return 1.75;
  return 1.0;
}

function ThemedScene({
  displayState,
  themeStyle,
}: {
  displayState: DisplayState;
  themeStyle: ReturnType<typeof updateTheme>;
}) {
  const ambientLightRef = useRef<THREE.AmbientLight>(null);
  const directionalLightRef = useRef<THREE.DirectionalLight>(null);
  const targetLightColor = useMemo(
    () => new THREE.Color(themeStyle.lightColor),
    [themeStyle.lightColor],
  );
  const targetDirectionalColor = useMemo(
    () => new THREE.Color(themeStyle.accentColor),
    [themeStyle.accentColor],
  );
  const targetLightIntensity = getLightIntensity(displayState);

  useFrame((_, delta) => {
    const amount = 1 - Math.exp(-delta * 2.4);

    if (ambientLightRef.current) {
      ambientLightRef.current.color.lerp(targetLightColor, amount);
      ambientLightRef.current.intensity = THREE.MathUtils.lerp(
        ambientLightRef.current.intensity,
        0.42 + targetLightIntensity * 0.18,
        amount,
      );
    }

    if (directionalLightRef.current) {
      directionalLightRef.current.color.lerp(targetDirectionalColor, amount);
      directionalLightRef.current.intensity = THREE.MathUtils.lerp(
        directionalLightRef.current.intensity,
        1.0 + targetLightIntensity * 0.35,
        amount,
      );
    }
  });

  return (
    <>
      <ambientLight ref={ambientLightRef} intensity={0.5} />
      <directionalLight
        ref={directionalLightRef}
        position={[4, 8, 4]}
        intensity={1.4}
      />
    </>
  );
}

export default function App() {
  const {
    connection: sessionConnection,
    errorMessage: sessionErrorMessage,
    robotSession,
  } = useRobotSession();
  const browserVoice = useBrowserVoiceCommand();
  const {
    errorMessage: voiceErrorMessage,
    isActive: isVoiceActive,
    phase: voicePhase,
    start: startVoice,
    stop: stopVoice,
  } = browserVoice;
  const activeNut =
    robotSession.theme.primary_nut || robotSession.combo[0]?.nut || "";
  const terrainColorCommand = getTerrainColorCommand(activeNut);
  const display = setDisplayState(robotSession.display_state, robotSession);
  const resolvedTheme = resolveSessionTheme(robotSession);
  const themeStyle = updateTheme(resolvedTheme);
  const comboDisplay = updateComboDisplay(
    robotSession.combo,
    robotSession.combo_text,
  );
  const transcriptDisplay = showTranscript(robotSession.transcript);
  const isListening =
    robotSession.display_state === "listening_state" ||
    robotSession.display_state === "listening_intensity" ||
    robotSession.display_state === "listening_job" ||
    robotSession.display_state === "listening_satiety";
  const isLoading = robotSession.display_state === "recommending";

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: themeStyle.backgroundColor,
        position: "relative",
        overflow: "hidden",
        transition: "background 600ms ease",
      }}
    >
      <Canvas camera={{ fov: 50 }}>
        <FixedCamera />
        <ThemedScene
          displayState={robotSession.display_state}
          themeStyle={themeStyle}
        />
        <Terrain
          colorCommand={terrainColorCommand}
          mode={display.sceneMode}
          theme={themeStyle.terrainTheme}
        />
        <OrbitControls target={TERRAIN_VIEW_TARGET} />
      </Canvas>

      <div
        style={{
          position: "absolute",
          top: 24,
          left: 24,
          color: "rgba(235, 248, 255, 0.94)",
          fontFamily: "sans-serif",
          textAlign: "left",
          pointerEvents: "none",
          textShadow: "0 2px 12px rgba(0, 0, 0, 0.7)",
        }}
      >
        <h1 style={{ margin: 0, fontSize: 28, color: "inherit" }}>LOKI</h1>
        <p>Session: {sessionConnection}</p>
        {sessionErrorMessage ? <p>Session error: {sessionErrorMessage}</p> : null}
        <div
          style={{
            background: themeStyle.panelBackground,
            border: `1px solid ${themeStyle.borderColor}`,
            borderRadius: 8,
            marginTop: 14,
            maxWidth: 440,
            padding: "14px 16px",
          }}
        >
          <p
            style={{
              color: themeStyle.secondaryColor,
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: 0,
              marginBottom: 6,
              textTransform: "uppercase",
            }}
          >
            {robotSession.display_state}
          </p>
          <h2
            style={{
              color: "inherit",
              fontSize: 24,
              fontWeight: 800,
              letterSpacing: 0,
              lineHeight: 1.15,
              margin: "0 0 8px",
            }}
          >
            {display.headline}
          </h2>
          <p style={{ fontSize: 17, lineHeight: 1.35 }}>{display.message}</p>
          <div
            style={{
              display: "grid",
              gap: 6,
              gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
              marginTop: 14,
            }}
          >
            {display.progress.map((step) => (
              <div
                key={step.label}
                style={{
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    background: step.isActive
                      ? themeStyle.accentColor
                      : step.isComplete
                        ? themeStyle.secondaryColor
                        : "rgba(235, 248, 255, 0.22)",
                    borderRadius: 999,
                    height: 4,
                    marginBottom: 5,
                    transition: "background 300ms ease",
                  }}
                />
                <p
                  style={{
                    color:
                      step.isActive || step.isComplete
                        ? "rgba(255, 255, 255, 0.94)"
                        : "rgba(235, 248, 255, 0.52)",
                    fontSize: 11,
                    lineHeight: 1.15,
                    overflowWrap: "anywhere",
                  }}
                >
                  {step.label}
                </p>
              </div>
            ))}
          </div>
          {isListening ? (
            <p style={{ color: themeStyle.accentColor, marginTop: 10 }}>
              음성 입력 대기 중...
            </p>
          ) : null}
          {isLoading ? (
            <p style={{ color: themeStyle.accentColor, marginTop: 10 }}>
              분석 중...
            </p>
          ) : null}
          {transcriptDisplay ? (
            <p style={{ marginTop: 12 }}>Transcript: {transcriptDisplay}</p>
          ) : null}
          {comboDisplay ? (
            <p style={{ marginTop: 8 }}>Combo: {comboDisplay}</p>
          ) : null}
          {robotSession.error ? (
            <p style={{ color: "#ffb4b4", marginTop: 8 }}>
              {showError(robotSession.error)}
            </p>
          ) : null}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 12,
            pointerEvents: "auto",
          }}
        >
          <button
            disabled={isVoiceActive}
            onClick={startVoice}
            style={{
              background: "rgba(235, 248, 255, 0.92)",
              border: 0,
              borderRadius: 6,
              color: "#050505",
              cursor: isVoiceActive ? "default" : "pointer",
              fontSize: 14,
              fontWeight: 700,
              padding: "8px 12px",
            }}
            type="button"
          >
            Start Python Voice
          </button>
          <button
            disabled={!isVoiceActive}
            onClick={stopVoice}
            style={{
              background: "rgba(5, 5, 5, 0.62)",
              border: "1px solid rgba(235, 248, 255, 0.5)",
              borderRadius: 6,
              color: "rgba(235, 248, 255, 0.92)",
              cursor: isVoiceActive ? "pointer" : "default",
              fontSize: 14,
              fontWeight: 700,
              padding: "8px 12px",
            }}
            type="button"
          >
            Stop
          </button>
        </div>
        <p>Voice bridge: {voicePhase}</p>
        {voiceErrorMessage ? <p>Voice error: {voiceErrorMessage}</p> : null}
        <p>Active Nut: {activeNut || "none"}</p>
        <p>Color: {terrainColorCommand.toUpperCase()}</p>
      </div>
    </div>
  );
}
