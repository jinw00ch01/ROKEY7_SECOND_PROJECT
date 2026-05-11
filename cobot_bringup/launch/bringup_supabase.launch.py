"""Supabase E2E bringup — wraps full_system.launch.py with Supabase defaults.

Differences from full_system.launch.py:
  - order_source defaults to "supabase" (uses SupabaseOrderProvider)
  - enable_firebase_status_bridge defaults to false
  - enable_supabase_status_bridge defaults to true
  - SUPABASE_URL / SUPABASE_KEY are loaded from .env *into the launch process
    environment* via SetEnvironmentVariable, so every spawned node (task_manager,
    supabase_status_bridge, ...) inherits them without needing parameter
    plumbing or a per-node yaml.

Override the .env source path with db_env_path:=/absolute/path/to/.env

  ros2 launch cobot_bringup bringup_supabase.launch.py
  ros2 launch cobot_bringup bringup_supabase.launch.py \\
      db_env_path:=/some/other/.env order_source:=mock
"""

from __future__ import annotations

import os
from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


# Default .env path — assumes the standard cobot_ws layout. Override with
# the `db_env_path` launch arg per-host if your checkout lives elsewhere.
_DEFAULT_ENV_PATH = str(
    Path.home() / "cobot_ws" / "src" / "cobot2" / "cobot_db" / ".env"
)


def _parse_dotenv(path: str) -> dict[str, str]:
    """Tiny .env parser — no quoting/expansion, good enough for our two keys.

    Returns an empty dict if the file is missing so the launch still proceeds
    (the nodes log a warning and no-op on writes, but the robot pipeline
    keeps running — same policy as the rest of the Supabase code).
    """
    out: dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def generate_launch_description() -> LaunchDescription:
    db_env_path_arg = DeclareLaunchArgument(
        "db_env_path",
        default_value=_DEFAULT_ENV_PATH,
        description=(
            "Absolute path to the .env file with SUPABASE_URL and SUPABASE_KEY. "
            "Loaded into the launch process environment before any node spawns."
        ),
    )

    # LaunchConfiguration("db_env_path")는 substitution이라 launch description
    # 평가 시점에 풀리지만, _parse_dotenv는 launch description 생성 시점에
    # 동기로 실행돼야 한다(파일을 읽어 SetEnvironmentVariable 인자를 만들어야
    # 하므로). 사용자가 `ros2 launch ... db_env_path:=...`로 넘긴 값은
    # 그 시점에는 sys.argv로만 보이므로 argv를 직접 본다.
    import sys

    env_path = _DEFAULT_ENV_PATH
    for arg in sys.argv:
        if arg.startswith("db_env_path:="):
            env_path = arg.split(":=", 1)[1]
            break

    env_vars = _parse_dotenv(env_path)

    set_env_actions = []
    for key in ("SUPABASE_URL", "SUPABASE_KEY"):
        value = env_vars.get(key, "")
        # 빈 문자열도 SetEnvironmentVariable로 설정한다. 그래야 셸에 우연히
        # 남아 있던 stale 값이 위로 새지 않는다. CobotDbManager는 빈 url/key
        # 를 lazy init 시 거부하므로 노드는 경고만 남기고 no-op.
        set_env_actions.append(SetEnvironmentVariable(key, value))

    # full_system.launch.py 를 포함시키면서 supabase 기본값으로 덮어쓴다.
    # 사용자가 명시적으로 다른 값을 넘기면 그쪽이 우선 (launch arg는 처음
    # 평가될 때 결정되며, IncludeLaunchDescription의 launch_arguments는 이를
    # 자식 launch에 그대로 전달).
    full_system = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("cobot_bringup"), "launch", "full_system.launch.py"]
            )
        ),
        launch_arguments=[
            ("order_source", LaunchConfiguration("order_source")),
            ("enable_firebase_status_bridge",
                LaunchConfiguration("enable_firebase_status_bridge")),
            ("enable_supabase_status_bridge",
                LaunchConfiguration("enable_supabase_status_bridge")),
        ],
    )

    return LaunchDescription([
        db_env_path_arg,
        DeclareLaunchArgument("order_source", default_value="supabase"),
        DeclareLaunchArgument(
            "enable_firebase_status_bridge", default_value="false",
        ),
        DeclareLaunchArgument(
            "enable_supabase_status_bridge", default_value="true",
        ),
        *set_env_actions,
        full_system,
    ])
