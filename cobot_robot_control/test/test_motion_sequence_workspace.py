try:
    from cobot_robot_control.doosan_motion_client import MockMotionClient
    from cobot_robot_control.gripper_controller import MockGripperBackend
    from cobot_robot_control.motion_sequence import (
        MotionConfig,
        WorkspaceBounds,
        execute_pick_and_place,
    )
except ModuleNotFoundError:
    from cobot_robot_control.cobot_robot_control.doosan_motion_client import (
        MockMotionClient,
    )
    from cobot_robot_control.cobot_robot_control.gripper_controller import (
        MockGripperBackend,
    )
    from cobot_robot_control.cobot_robot_control.motion_sequence import (
        MotionConfig,
        WorkspaceBounds,
        execute_pick_and_place,
    )


def _config():
    return MotionConfig(
        home_joints_deg=[0.0, 0.0, 90.0, 0.0, 90.0, 0.0],
        approach_offset_z_mm=80.0,
        workspace_bounds=WorkspaceBounds(
            xmin_mm=200.0,
            xmax_mm=700.0,
            ymin_mm=-300.0,
            ymax_mm=300.0,
            zmin_mm=0.0,
            zmax_mm=500.0,
        ),
    )


def _run(cfg, grasp_xyz, return_xyz):
    motion = MockMotionClient()
    gripper = MockGripperBackend(simulate_grip=True)
    result = execute_pick_and_place(
        motion=motion,
        gripper=gripper,
        cfg=cfg,
        grasp_xyz_mm=grasp_xyz,
        grasp_yaw_rad=0.0,
        return_xyz_mm=return_xyz,
        return_zyz_deg=[168.0, 179.0, 168.0],
    )
    return result, motion


def test_execute_rejects_grasp_outside_workspace_before_motion():
    result, motion = _run(
        _config(),
        grasp_xyz=[750.0, 0.0, 120.0],
        return_xyz=[367.0, -150.0, 340.0],
    )

    assert result[0] is False
    assert result[1] == 5
    assert "grasp_xyz outside workspace" in result[2]
    assert motion.history == []


def test_execute_rejects_computed_waypoint_outside_workspace_before_motion():
    result, motion = _run(
        _config(),
        grasp_xyz=[367.0, 0.0, 120.0],
        return_xyz=[367.0, -150.0, 460.0],
    )

    assert result[0] is False
    assert result[1] == 5
    assert "above_return_xyz outside workspace" in result[2]
    assert motion.history == []


def test_execute_allows_workspace_when_disabled():
    cfg = _config()
    cfg.workspace_enabled = False

    result, motion = _run(
        cfg,
        grasp_xyz=[750.0, 0.0, 120.0],
        return_xyz=[367.0, -150.0, 340.0],
    )

    assert result == (True, 0, "ok")
    assert motion.history
