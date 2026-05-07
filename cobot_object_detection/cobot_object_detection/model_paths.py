"""Model path resolution for the object detection node."""

from __future__ import annotations

from pathlib import Path


def resolve_model_path(model_path: str) -> str:
    configured = str(model_path or "").strip()
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
