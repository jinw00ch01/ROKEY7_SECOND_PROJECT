from cobot_voice import web_voice_bridge_server


class _FakeDemo:
    def __init__(self):
        self.calls = []

    def set_state(self, **fields):
        self.calls.append(fields)


def test_map_mode_to_display_state():
    assert web_voice_bridge_server.map_mode_to_display_state("idle") == "idle"
    assert (
        web_voice_bridge_server.map_mode_to_display_state("wake_detected")
        == "wake_detected"
    )
    assert (
        web_voice_bridge_server.map_mode_to_display_state("listening")
        == "listening_state"
    )
    assert (
        web_voice_bridge_server.map_mode_to_display_state("transcribing")
        == "listening_state"
    )
    assert (
        web_voice_bridge_server.map_mode_to_display_state("processing")
        == "recommending"
    )
    assert (
        web_voice_bridge_server.map_mode_to_display_state("speaking")
        == "asking_state"
    )
    assert web_voice_bridge_server.map_mode_to_display_state("error") == "error"
    assert web_voice_bridge_server.map_mode_to_display_state("unknown") is None


def test_set_state_delegates_to_session_state():
    bridge = object.__new__(web_voice_bridge_server.WebVoiceBridge)
    bridge.demo = _FakeDemo()

    response = bridge.set_state(
        {
            "mode": "listening",
            "wakeWordDetected": True,
            "commandText": "hello",
            "parsedAction": "sort",
            "targets": ["almond"],
        }
    )

    assert response == {"ok": True}
    assert bridge.demo.calls == [
        {
            "mode": "listening",
            "wakeWordDetected": True,
            "commandText": "hello",
            "parsedAction": "sort",
            "targets": ["almond"],
        }
    ]


def main():
    test_map_mode_to_display_state()
    test_set_state_delegates_to_session_state()
    print("All web voice bridge server tests passed.")


if __name__ == "__main__":
    main()
