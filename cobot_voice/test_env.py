from pathlib import Path

from cobot_voice import env


def test_get_env_path_uses_override(monkeypatch, tmp_path):
    override = tmp_path / "voice.env"
    monkeypatch.setenv("COBOT_VOICE_ENV_PATH", str(override))

    assert env.get_env_path() == override


def test_get_env_path_falls_back_to_source_resource(monkeypatch):
    monkeypatch.delenv("COBOT_VOICE_ENV_PATH", raising=False)

    path = env.get_env_path()

    assert path == Path(env.__file__).resolve().parents[1] / "resource" / ".env"


def test_load_package_env_reads_override(monkeypatch, tmp_path):
    env_file = tmp_path / "voice.env"
    env_file.write_text("COBOT_TEST_ENV_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.setenv("COBOT_VOICE_ENV_PATH", str(env_file))
    monkeypatch.delenv("COBOT_TEST_ENV_VALUE", raising=False)
    monkeypatch.setattr(env, "_ENV_LOADED", False)

    assert env.load_package_env() == env_file
    assert env.os.getenv("COBOT_TEST_ENV_VALUE") == "loaded"
