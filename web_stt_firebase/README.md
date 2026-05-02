# Web STT Firebase

React/Vite display for the LOKI robot state stored in Firebase Firestore. The app listens to `robot_state/loki` and renders the current mode and command over a Three.js terrain visualization.

## Project Layout

```text
web_stt_firebase/
  src/
    components/      React and Three.js UI components
    hooks/           Firestore subscription hooks
    lib/             Firebase setup and shared types
    main.tsx         App entry point
  scripts/firebase/  Python helpers for publishing mock robot state
  dataconnect/       Firebase Data Connect schema/config
  public/            Static web assets
```

## Commands

```sh
npm install
npm run dev
npm run build
npm run lint
```

The Python helper in `scripts/firebase/update_robot_state.py` expects a Firebase service account JSON path to be configured before use.
