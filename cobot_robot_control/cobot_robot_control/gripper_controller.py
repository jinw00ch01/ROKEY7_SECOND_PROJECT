"""Gripper backend abstraction for the OnRobot RG2 + room for Tool DIO.

Phase A uses the Modbus TCP backend (matches lecture/onrobot.py path).
A Mock backend is provided so the rest of the stack can be exercised in
virtual mode without a physical gripper. The Tool DIO backend is left as a
TODO; the abstract Protocol below pins the interface so we can drop a new
implementation in once the wiring story is finalized.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol


_log = logging.getLogger(__name__)


class GripperBackend(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def move_to(self, width_mm: float) -> None: ...
    def is_busy(self) -> bool: ...
    def is_grip_detected(self) -> bool: ...
    def shutdown(self) -> None: ...


class MockGripperBackend:
    """No hardware - logs intent and reports immediate completion."""

    def __init__(self, simulate_grip: bool = True) -> None:
        self._simulate_grip = simulate_grip
        self._closed = False
        self._target_width_mm = 110.0

    def open(self) -> None:
        self._closed = False
        self._target_width_mm = 110.0

    def close(self) -> None:
        self._closed = True
        self._target_width_mm = 0.0

    def move_to(self, width_mm: float) -> None:
        self._target_width_mm = float(width_mm)
        self._closed = width_mm < 30.0  # heuristic for the mock

    def is_busy(self) -> bool:
        return False

    def is_grip_detected(self) -> bool:
        return self._closed and self._simulate_grip

    def shutdown(self) -> None:
        return None


class ModbusRG2Backend:
    """OnRobot RG2 over Modbus TCP.

    Matches the register map used in
    `[lecture]pick_and_place_voice/robot_control/onrobot.py`:
      - register 0   target_force (0.1 N)
      - register 1   target_width (0.1 mm)
      - register 2   control mode (0x10 = grip_w_offset)
      - register 268 status word (bit 0 = busy, bit 1 = grip_detected)
    """

    _CTRL_GRIP_W_OFFSET = 16

    def __init__(
        self,
        ip: str,
        port: int,
        unit: int = 65,
        max_width_x10: int = 1100,   # 110.0 mm for RG2
        force_x10: int = 400,        # 40.0 N
        timeout_sec: float = 1.0,
    ) -> None:
        from pymodbus.client.sync import ModbusTcpClient  # type: ignore

        self._client = ModbusTcpClient(
            ip,
            port=port,
            stopbits=1,
            bytesize=8,
            parity="E",
            baudrate=115200,
            timeout=timeout_sec,
        )
        self._unit = unit
        self._max_width_x10 = max_width_x10
        self._force_x10 = force_x10
        self._client.connect()

    def open(self) -> None:
        self._client.write_registers(
            address=0,
            values=[self._force_x10, self._max_width_x10, self._CTRL_GRIP_W_OFFSET],
            unit=self._unit,
        )

    def close(self) -> None:
        self._client.write_registers(
            address=0,
            values=[self._force_x10, 0, self._CTRL_GRIP_W_OFFSET],
            unit=self._unit,
        )

    def move_to(self, width_mm: float) -> None:
        target_x10 = int(round(float(width_mm) * 10.0))
        target_x10 = max(0, min(self._max_width_x10, target_x10))
        self._client.write_registers(
            address=0,
            values=[self._force_x10, target_x10, self._CTRL_GRIP_W_OFFSET],
            unit=self._unit,
        )

    def _read_status(self) -> int:
        rr = self._client.read_holding_registers(
            address=268, count=1, unit=self._unit
        )
        if rr is None or not getattr(rr, "registers", None):
            raise IOError("RG2 status read failed")
        return int(rr.registers[0])

    def is_busy(self) -> bool:
        status = self._read_status()
        return bool(status & 0x0001)

    def is_grip_detected(self) -> bool:
        status = self._read_status()
        return bool(status & 0x0002)

    def shutdown(self) -> None:
        try:
            self._client.close()
        except Exception as exc:
            _log.debug("RG2 modbus close failed: %s", exc)


def make_gripper(backend: str, **kwargs) -> GripperBackend:
    backend = backend.lower()
    if backend == "mock":
        return MockGripperBackend(**kwargs)
    if backend == "modbus":
        return ModbusRG2Backend(**kwargs)
    if backend == "tool_dio":
        raise NotImplementedError("Tool DIO gripper backend is not implemented yet.")
    raise ValueError(f"unknown gripper backend: {backend!r}")


def wait_until_idle(gripper: GripperBackend, poll_sec: float = 0.05, timeout_sec: float = 5.0) -> bool:
    """Wait for gripper motion to complete.

    RG2 over Modbus has a small latency between a write_registers command
    and the busy bit going high. If we just polled is_busy() right after
    a close()/move_to(), we'd see busy=False (stale) and return True
    immediately, before the motion even started. That made verify_grip
    transition in ~7 ms and read a stale grip_detected bit.

    Two-phase wait: first wait briefly for busy to go True (motion
    started), then wait for busy to go back to False (motion ended).
    If busy never goes True within `start_window`, assume the command
    was a no-op and return True.
    """
    start_window = 0.4  # how long to wait for busy=True before assuming no-op
    deadline = time.time() + timeout_sec

    start_deadline = min(time.time() + start_window, deadline)
    started = False
    while time.time() < start_deadline:
        if gripper.is_busy():
            started = True
            break
        time.sleep(poll_sec)

    if not started:
        return True

    while time.time() < deadline:
        if not gripper.is_busy():
            # One more poll to debounce against momentary idle reads.
            time.sleep(poll_sec)
            if not gripper.is_busy():
                return True
        time.sleep(poll_sec)
    return False
