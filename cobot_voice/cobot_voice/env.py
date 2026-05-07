# 한국어 요약:
#   패키지의 .env 파일을 dotenv로 1회만 로딩하고 필수 env 변수를 조회하는
#   유틸. COBOT_VOICE_ENV_PATH로 경로 override가 가능하여 배포 환경마다
#   다른 .env(예: 시크릿 분리)를 사용할 수 있다.
import os
from pathlib import Path

from dotenv import load_dotenv


# 모듈 레벨 가드: 동일 프로세스 내에서 dotenv를 중복 로딩하지 않도록 한다.
_ENV_LOADED = False


def get_package_path():
    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("cobot_voice"))
    except Exception:
        return Path(__file__).resolve().parents[1]


def get_source_env_path():
    return Path(__file__).resolve().parents[1] / "resource" / ".env"


def get_env_path():
    # 환경변수 override가 있으면 우선 사용 (배포/시크릿 분리 시나리오 지원).
    override_path = os.getenv("COBOT_VOICE_ENV_PATH")
    if override_path:
        return Path(override_path).expanduser()

    return get_source_env_path()


def load_package_env():
    global _ENV_LOADED
    # 이미 로딩되었다면 중복 호출을 빠르게 단락(short-circuit) 처리.
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
