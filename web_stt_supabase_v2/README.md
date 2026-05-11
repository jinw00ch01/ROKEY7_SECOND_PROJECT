# Web STT Firebase v2

React/Vite display for the LOKI robot session stored in Firebase Firestore. The app listens to `robot_session/current` and renders the current session state over a Three.js terrain visualization.

Unlike v1, v2 captures voice commands directly in the browser and writes session updates to Firestore from the web app — no Python bridge required. The TS orchestrator mirrors `cobot_voice/voice_order_flow.py`: wake-word → ask state → STT → resolve category → ask intensity → STT → resolve intensity → build combo → publish result.

## Project Layout

```text
web_stt_firebase_v2/
  public/
    config/          Voice config JSONs copied from cobot_voice/config
  src/
    components/      React and Three.js UI components
    hooks/           Firestore subscription + voice orchestrator hooks
    lib/
      voice/         Browser ports of the cobot_voice flow
        orchestrator.ts   run_recommendation_flow equivalent
        recorder.ts       MediaRecorder-based 5s capture
        whisper.ts        OpenAI Whisper STT
        tts.ts            ElevenLabs TTS playback
        wakeWord.ts       Web Speech API wake-word listener
        llm.ts            StateAnalyzer + IntensityAnalyzer + menu match
        recommendation.ts extract/build_combo helpers
        session.ts        Firestore writes (display_state, theme, etc.)
        questionFlow.ts   question_flow.json loader
    main.tsx         App entry point
```

## Setup

```sh
cp .env.local.example .env.local   # then fill in the keys
npm install
npm run dev
```

Required env vars (all `VITE_`-prefixed so Vite exposes them to the browser bundle):

- `VITE_OPENAI_API_KEY` — used for Whisper STT and `gpt-4o` state/intensity analysis.
- `VITE_ELEVENLABS_API_KEY` — used for TTS playback. If empty, TTS is silently skipped.
- `VITE_PROMPT_MODE` — `freeform` (default) or `menu`. Menu mode matches numbered answers (1–4) without an LLM call.
- `VITE_TTS_ENABLED` — set to `0` to disable spoken prompts.
- `VITE_ROSBRIDGE_URL` — WebSocket URL of `rosbridge_server` (e.g. `ws://localhost:9090`). When set, a successful recommendation calls `/task/start` (`std_srvs/srv/Trigger`) so the robot actually picks the combo, matching the Python `voice-alias` flow. Leave empty to stop at `result_ready`.

> Bundling API keys in the browser is fine for local/demo use only. For deployment, route OpenAI/ElevenLabs requests through a serverless proxy that holds the keys server-side.

## Robot dispatch

The Python `voice-alias` shell alias runs `voice_to_robot.py`, which after a successful recommendation calls `ros2 service call /task/start std_srvs/srv/Trigger {}`. Browsers cannot shell out, so v2 calls the same service over `rosbridge_websocket`:

```sh
sudo apt install ros-humble-rosbridge-suite
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

With `rosbridge_server` running and `VITE_ROSBRIDGE_URL` set, `useVoiceOrchestrator` registers an `onDispatch` callback that calls `/task/start` exactly like the Python dispatcher.

For the robot to actually pick the browser-published combo, `cobot_task_manager` must be launched with `order_source=firestore` (not `file`). The new `FirestoreOrderProvider` reads `robot_session/current` directly — same doc the browser writes — and dedupes by the `request_id` the orchestrator stamps on each session. With `order_source=file`, the task manager keeps reading the stale `latest_order.json` written by the Python flow and rejects re-fetches with `order_fetch_failed`.

## Wake-word

The Python flow uses an `openwakeword` TFLite model (`hello_rokey`). Porting that requires three TFLite models (mel-spectrogram, embedding, keyword) plus a JS inference runtime. v2 substitutes the Web Speech API and listens for the keyword phrase ("hello rokey", "헬로 로키", "샤갈"). Chrome/Edge only — Firefox/Safari fall back to a no-op until manually cancelled.

## Commands

```sh
npm install
npm run dev
npm run build
npm run lint
```
