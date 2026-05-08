# 한국어 요약:
#   object detection 노드용 YOLO 모델 경로 resolver.
#   4단계 fallback 순서로 모델 위치를 찾아 배포/개발 환경 모두에서 동작하도록 한다:
#     (1) configured 절대경로, (2) cwd 기준 상대경로,
#     (3) ament-share 패키지 install 경로, (4) 소스 트리 experiments/ 산출물.
#   파라미터 미지정 시에도 ament-share → source-tree 순으로 best.pt를 탐색한다.
"""Model path resolution for the object detection node."""

from __future__ import annotations

from pathlib import Path


def resolve_model_path(model_path: str) -> str:
    configured = str(model_path or "").strip()
    # 파라미터로 명시된 경로가 있으면 cwd → ament-share 순서로 탐색.
    if configured:
        path = Path(configured).expanduser()
        if path.is_absolute():
            return str(path)
        cwd_path = Path.cwd() / path
        if cwd_path.is_file():
            return str(cwd_path)
        try:
            from ament_index_python.packages import get_package_share_directory

            share_path = Path(get_package_share_directory("cobot_object_detection"))
            package_path = share_path / path
            if package_path.is_file():
                return str(package_path)
        except Exception:
            pass
        return str(path)

    try:
        from ament_index_python.packages import get_package_share_directory

        installed_model = (
            Path(get_package_share_directory("cobot_object_detection"))
            / "models"
            / "best.pt"
        )
        if installed_model.is_file():
            return str(installed_model)
    except Exception:
        pass

    # 마지막 fallback: 개발 환경에서 install 없이 소스 트리의 학습 산출물을 사용.
    source_model = (
        Path(__file__).resolve().parents[2]
        / "experiments"
        / "cobot_OD_obb_nano"
        / "train_phase2_20260504_173049"
        / "weights"
        / "best.pt"
    )
    if source_model.is_file():
        return str(source_model)

    raise FileNotFoundError(
        "YOLO model not found. Install cobot_object_detection with its "
        "models/best.pt resource, or set the model_path ROS parameter."
    )
