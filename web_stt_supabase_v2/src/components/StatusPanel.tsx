import type { ProgressStep } from "../lib/display/displayState";
import type { ThemeStyle } from "../lib/display/themeStyle";

export type StatusPanelProps = {
  displayState: string;
  headline: string;
  message: string;
  progress: ProgressStep[];
  isListening: boolean;
  isLoading: boolean;
  transcript: string;
  combo: string;
  errorText: string;
  themeStyle: ThemeStyle;
};

export function StatusPanel({
  displayState,
  headline,
  message,
  progress,
  isListening,
  isLoading,
  transcript,
  combo,
  errorText,
  themeStyle,
}: StatusPanelProps) {
  return (
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
        {displayState}
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
        {headline}
      </h2>
      <p style={{ fontSize: 17, lineHeight: 1.35 }}>{message}</p>
      <div
        style={{
          display: "grid",
          gap: 6,
          gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
          marginTop: 14,
        }}
      >
        {progress.map((step) => (
          <div key={step.label} style={{ minWidth: 0 }}>
            <div
              style={{
                // complete = accent의 40% alpha. 모든 테마에서 active(가득찬 accent)
                // 보다 한 단계 흐리지만 dim보다는 밝아서 "한 칸씩 차오르는" 시각을
                // 일관되게 유지한다. (default 테마의 secondary가 primary와 너무
                // 가까워서 complete 칸이 꺼진 듯 보이던 이슈 해결.)
                background: step.isActive
                  ? themeStyle.accentColor
                  : step.isComplete
                    ? `${themeStyle.accentColor}66`
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
        <p style={{ color: themeStyle.accentColor, marginTop: 10 }}>분석 중...</p>
      ) : null}
      {transcript ? (
        <p style={{ marginTop: 12 }}>Transcript: {transcript}</p>
      ) : null}
      {combo ? <p style={{ marginTop: 8 }}>Combo: {combo}</p> : null}
      {errorText ? (
        <p style={{ color: "#ffb4b4", marginTop: 8 }}>{errorText}</p>
      ) : null}
    </div>
  );
}
