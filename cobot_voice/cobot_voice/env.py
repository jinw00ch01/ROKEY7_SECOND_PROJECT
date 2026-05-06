import os
from pathlib import Path

from dotenv import load_dotenv


_ENV_LOADED = False


def get_package_path():
    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("cobot_voice"))
    except Exception:
        return Path(__file__).resolve().parents[1]


def get_env_path():
    override_path = os.getenv("COBOT_VOICE_ENV_PATH")
    if override_path:
        return Path(override_path).expanduser()

    package_path = get_package_path()
    installed_env_path = package_path / "resource" / ".env"
    for parent in package_path.parents:
        source_env_path = parent / "cobot_voice" / "resource" / ".env"
        if source_env_path.exists() and source_env_path != installed_env_path:
            return source_env_path

    return installed_env_path


def load_package_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return get_env_path()

    env_path = get_env_path()
    load_dotenv(dotenv_path=env_path)
    _ENV_LOADED = True
    return env_path


def get_required_env(name):
    load_package_env()
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set in {get_env_path()}")
    return value
