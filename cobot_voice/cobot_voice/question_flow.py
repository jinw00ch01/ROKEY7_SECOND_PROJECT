# 한국어 요약:
#   question_flow.json에 정의된 TTS/UI 메시지 템플릿을 로드하고 키별로
#   조회하는 헬퍼. config 디렉터리 위치는 source-tree → ament share 순으로
#   fallback 탐색한다. format 치환 키({combo_text} 등)는 호출부에서 kwargs로
#   주입한다.
from pathlib import Path
import json
import logging


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
SOURCE_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
QUESTION_FLOW_FILENAME = "question_flow.json"


def _get_config_dir():
    # 1단계: 개발 시 source tree의 config 디렉터리를 우선.
    if SOURCE_CONFIG_DIR.exists():
        return SOURCE_CONFIG_DIR

    # 2단계: 설치된 ROS 환경에서는 ament share 디렉터리에서 탐색.
    try:
        from ament_index_python.packages import get_package_share_directory

        share_config_dir = Path(get_package_share_directory("cobot_voice")) / "config"
        # 3단계: share dir이 실제로 존재할 때만 반환.
        if share_config_dir.exists():
            return share_config_dir
    except Exception:
        pass

    # 4단계: 모두 실패 시 source 경로를 그대로 반환 (load 시 명확한 에러 발생).
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

    # kwargs는 메시지 내 {combo_text} 등 placeholder 치환용으로 사용된다.
    return messages[key].format(**kwargs)
