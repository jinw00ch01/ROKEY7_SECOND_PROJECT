# 한국어 요약:
#   너트 detection을 위한 hand-eye 및 base 프레임 변환 유틸.
#   Doosan TCP 컨벤션(위치 mm, 회전 ZYZ Euler degrees)을 패키지 전체에 일관되게
#   적용한다. npy로부터 로드한 hand-eye 매트릭스도 mm 단위라 단위 일관성이 유지된다.
#   base ← gripper ← camera 4x4 동차변환 체인을 구성하고, 카메라 좌표 점을
#   base 프레임으로 매핑하는 함수들을 제공한다.
"""Hand-eye + base-frame transforms for nut detections.

Doosan TCP convention used everywhere in this package:
  - position : millimeters in robot base frame, [x, y, z]
  - rotation : ZYZ Euler in degrees, [rx, ry, rz]   (matches DSR posx)

The hand-eye matrix loaded from the npy is the gripper -> camera transform
expressed in millimeters as well, so the chain stays unit-consistent.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np
from scipy.spatial.transform import Rotation


def load_gripper2camera(npy_path: str) -> np.ndarray:
    T = np.load(npy_path)
    if T.shape != (4, 4):
        raise ValueError(f"gripper2camera npy must be 4x4, got {T.shape}: {npy_path}")
    return T.astype(np.float64)


def tcp_to_base2gripper(tcp_xyz_mm: Sequence[float], tcp_zyz_deg: Sequence[float]) -> np.ndarray:
    if len(tcp_xyz_mm) != 3 or len(tcp_zyz_deg) != 3:
        raise ValueError("TCP needs 3 translation and 3 rotation values")
    # Doosan posx 규약을 그대로 사용하여 ZYZ Euler(degrees)로 회전 행렬을 구성.
    R = Rotation.from_euler("ZYZ", list(tcp_zyz_deg), degrees=True).as_matrix()
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(tcp_xyz_mm, dtype=np.float64)
    return T


def compose_base2camera(base2gripper: np.ndarray, gripper2camera: np.ndarray) -> np.ndarray:
    return base2gripper @ gripper2camera


def transform_camera_to_base(base2cam: np.ndarray, camera_xyz_mm: Sequence[float]) -> Tuple[float, float, float]:
    point = np.array(
        [camera_xyz_mm[0], camera_xyz_mm[1], camera_xyz_mm[2], 1.0],
        dtype=np.float64,
    )
    out = base2cam @ point
    return float(out[0]), float(out[1]), float(out[2])
