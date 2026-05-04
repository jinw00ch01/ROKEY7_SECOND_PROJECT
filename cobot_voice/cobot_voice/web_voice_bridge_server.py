import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cobot_voice.voice_web_demo import VoiceWebDemo


class WebVoiceBridge:
    def __init__(self):
        self.demo = VoiceWebDemo(enable_audio=False)
        self.audio_demo = None
        self.audio_thread = None
        self.audio_lock = threading.Lock()

    def set_state(self, payload):
        self.demo.set_state(
            mode=payload.get("mode", "idle"),
            wakeWordDetected=bool(payload.get("wakeWordDetected", False)),
            commandText=payload.get("commandText", ""),
            parsedAction=payload.get("parsedAction", ""),
            targets=payload.get("targets", []),
        )
        return {"ok": True}

    def process_command(self, payload):
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")

        action, targets = self.demo.process_text(text)
        return {
            "ok": True,
            "text": text,
            "action": action,
            "targets": targets,
        }

    def start_audio_workflow(self):
        with self.audio_lock:
            if self.audio_thread and self.audio_thread.is_alive():
                return {"ok": True, "running": True}

            self.audio_thread = threading.Thread(target=self._run_audio_workflow, daemon=True)
            self.audio_thread.start()
            return {"ok": True, "running": True}

    def _run_audio_workflow(self):
        try:
            if self.audio_demo is None:
                self.audio_demo = VoiceWebDemo(enable_audio=True)
            self.audio_demo.run_once()
        except Exception as exc:
            print(f"Audio workflow failed: {exc}")
            self.demo.set_state(
                mode="error",
                wakeWordDetected=False,
                commandText="",
                parsedAction="",
                targets=[],
            )


def make_handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body or "{}")

        def do_OPTIONS(self):
            self._send_json(200, {"ok": True})

        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            try:
                payload = self._read_json()
                if self.path == "/voice-state":
                    response = bridge.set_state(payload)
                elif self.path == "/voice-command":
                    response = bridge.process_command(payload)
                elif self.path == "/voice-audio/start":
                    response = bridge.start_audio_workflow()
                else:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self._send_json(200, response)
            except Exception as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})

        def log_message(self, fmt, *args):
            print(f"{self.address_string()} - {fmt % args}")

    return Handler


def main():
    parser = argparse.ArgumentParser(
        description="Local HTTP bridge from the website voice UI to Firebase/OpenAI."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    bridge = WebVoiceBridge()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(bridge))
    print(f"Web voice bridge listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
