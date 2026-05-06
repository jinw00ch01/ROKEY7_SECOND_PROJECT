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
