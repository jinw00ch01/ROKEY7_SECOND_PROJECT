# Web STT Supabase v2

React/Vite display for the LOKI robot session backed by **Supabase**
(Postgres + Realtime). The app subscribes to the single `robot_session.current`
row and renders the current session state over a Three.js terrain
visualization. This is the v2 successor to `web_stt_firebase` — same UX,
Postgres backend instead of Firestore.

v2 captures voice commands directly in the browser and writes session
updates to Supabase from the web app — no Python bridge required. The TS
orchestrator mirrors `cobot_voice/voice_order_flow.py`: wake-word → ask
job → STT → resolve job → ask satiety → STT → resolve satiety → build
combo → publish result → dispatch to robot.

## Project Layout

```text
web_stt_supabase_v2/
  public/
    config/                   Voice config JSONs copied from cobot_voice/config
  src/
    App.tsx                   Top-level assembly (~110 lines)
    main.tsx                  React entry point
    components/
      SceneCanvas.tsx         Three.js Canvas + camera + lights
      StatusPanel.tsx         Top-left headline / progress / transcript panel
      VoiceControls.tsx       Start / Stop buttons + voice phase
      Terrain.tsx             Procedural terrain mesh
      terrain/                Terrain helpers (color themes, noise, height)
    hooks/
      useRobotSession.ts      Supabase Realtime subscription
      useVoiceOrchestrator.ts Voice flow lifecycle wrapper
      useKeyboardCommand.ts   Optional keyboard fallback
    lib/
      supabase.ts             Supabase client + SESSION_TABLE/SESSION_ID
      types.ts                Shared session / display types
      display/
        displayState.ts       DISPLAY_COPY, progress steps, getDisplayText
        themeStyle.ts         THEME_BY_CATEGORY, resolveSessionTheme, buildThemeStyle
      voice/                  Browser ports of the cobot_voice flow
        orchestrator.ts         run_recommendation_flow equivalent
        recorder.ts             MediaRecorder-based 5s capture
        whisper.ts              OpenAI Whisper STT
        tts.ts                  ElevenLabs TTS playback
        wakeWord.ts             Web Speech API wake-word listener
        llm.ts                  Job + satiety LLM analysis (gpt-4o)
        recommendation.ts       buildCombo / formatComboText helpers
        session.ts              Supabase writes (display_state, theme, etc.)
        rosbridge.ts            rosbridge /task/start dispatch
        questionFlow.ts         question_flow.json loader
```

## Setup

```sh
cp .env.example .env.local   # then fill in the keys
npm install
npm run dev
```

Required env vars (all `VITE_`-prefixed so Vite exposes them to the browser bundle):

- `VITE_SUPABASE_URL` — Supabase project URL.
- `VITE_SUPABASE_KEY` — Supabase publishable (anon) key.
- `VITE_OPENAI_API_KEY` — Whisper STT + `gpt-4o` job/satiety analysis.
- `VITE_ELEVENLABS_API_KEY` — ElevenLabs TTS. If empty, TTS is silently skipped.
- `VITE_PROMPT_MODE` — `freeform` (default) or `menu`. Menu mode matches numbered answers (1–4) without an LLM call.
- `VITE_TTS_ENABLED` — set to `0` to disable spoken prompts.
- `VITE_ROSBRIDGE_URL` — WebSocket URL of `rosbridge_server` (e.g. `ws://localhost:9090`). When set, a successful recommendation calls `/task/start` (`std_srvs/srv/Trigger`) so the robot actually picks the combo. Leave empty to stop at `result_ready`.

> Bundling API keys in the browser is fine for local/demo use only. For deployment, route OpenAI/ElevenLabs requests through a serverless proxy that holds the keys server-side.

## Robot dispatch

The Python `voice-alias` shell alias runs `voice_to_robot.py`, which after a successful recommendation calls `ros2 service call /task/start std_srvs/srv/Trigger {}`. Browsers cannot shell out, so v2 calls the same service over `rosbridge_websocket`:

```sh
sudo apt install ros-humble-rosbridge-suite
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

With `rosbridge_server` running and `VITE_ROSBRIDGE_URL` set, `useVoiceOrchestrator` registers an `onDispatch` callback that calls `/task/start` exactly like the Python dispatcher.

For the robot to actually pick the browser-published combo, `cobot_task_manager` must be launched with `order_source=supabase`. The `SupabaseOrderProvider` reads the same `robot_session.current` row the browser writes, dedupes by the `request_id` the orchestrator stamps on each session, and ignores rows without `success=true`. With `order_source=file`, the task manager keeps reading the stale `latest_order.json` written by the Python flow and rejects re-fetches with `order_fetch_failed`.

The supabase status bridge (`cobot_voice/supabase_status_bridge.py`) mirrors `/task/status`, `/task/result`, `/conveyor/place_ready` back into the same row so the web UI shows live robot progress. Defaults to `true` in `full_system.launch.py`.

## Wake-word

The Python flow uses an `openwakeword` TFLite model (`hello_rokey`). Porting that requires three TFLite models (mel-spectrogram, embedding, keyword) plus a JS inference runtime. v2 substitutes the Web Speech API and listens for the keyword phrase ("hello rokey", "헬로 로키", "샤갈"). Chrome/Edge only — Firefox/Safari fall back to a no-op until manually cancelled.

## Commands

```sh
npm install
npm run dev
npm run build
npm run lint
```
