from pathlib import Path
import json
import logging


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
SOURCE_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
QUESTION_FLOW_FILENAME = "question_flow.json"


def _get_config_dir():
    if SOURCE_CONFIG_DIR.exists():
        return SOURCE_CONFIG_DIR

    try:
        from ament_index_python.packages import get_package_share_directory

        share_config_dir = Path(get_package_share_directory("cobot_voice")) / "config"
        if share_config_dir.exists():
            return share_config_dir
    except Exception:
        pass

    return SOURCE_CONFIG_DIR


def load_question_flow():
    path = _get_config_dir() / QUESTION_FLOW_FILENAME
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            logger.debug("Loaded question flow config: %s", path)
            return data
    except FileNotFoundError as exc:
        message = f"Required JSON config file not found: {path}"
        logger.error(message)
        raise FileNotFoundError(message) from exc
    except json.JSONDecodeError as exc:
        message = f"Failed to parse JSON config file: {path} ({exc.msg} at line {exc.lineno}, column {exc.colno})"
        logger.error(message)
        raise ValueError(message) from exc


def get_message(key, **kwargs):
    messages = load_question_flow()
    if key not in messages:
        raise KeyError(f"Unknown question flow key: {key}")

    return messages[key].format(**kwargs)
