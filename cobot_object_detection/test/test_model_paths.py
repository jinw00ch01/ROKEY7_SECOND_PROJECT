from pathlib import Path

try:
    from cobot_object_detection.model_paths import resolve_model_path
except ModuleNotFoundError:
    from cobot_object_detection.cobot_object_detection.model_paths import (
        resolve_model_path,
    )


def test_empty_model_path_resolves_to_workspace_weight():
    path = Path(resolve_model_path(""))

    assert path.name == "best.pt"
    assert path.is_file()
    assert "cobot_OD_obb_nano" in path.parts


def test_absolute_model_path_is_preserved(tmp_path):
    model = tmp_path / "custom.pt"
    model.write_bytes(b"model")

    assert resolve_model_path(str(model)) == str(model)


def test_existing_relative_model_path_resolves_from_cwd(tmp_path, monkeypatch):
    model = tmp_path / "relative.pt"
    model.write_bytes(b"model")
    monkeypatch.chdir(tmp_path)

    assert resolve_model_path("relative.pt") == str(model)
