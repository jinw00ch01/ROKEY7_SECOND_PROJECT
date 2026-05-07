# conveyor_controller

ROS 2 Humble `ament_python` package that forwards conveyor commands from
`/conveyor_cmd` to an Arduino UNO over USB serial.

## Interface

- Topic: `/conveyor_cmd`
- Type: `std_msgs/msg/String`
- Commands:
  - `F30`: run forward at 30 percent speed
  - `R30`: run reverse at 30 percent speed
  - `F1` through `F100`: run forward from 1 to 100 percent speed
  - `R1` through `R100`: run reverse from 1 to 100 percent speed
  - `STOP`: stop the conveyor

The node sends each command to the Arduino as an uppercase line terminated by
`\n`, for example `F30\n`.

## Place-ready trigger (one edge = one movement)

In addition to `/conveyor_cmd`, the node subscribes to a `Bool` topic
(`place_ready_topic`, default `/conveyor/place_ready`) used by the robot
controller to signal "TCP at place point and gripper has opened — advance
the belt for the next nut."

Semantic:

- A **False → True edge** on `place_ready_topic` triggers exactly one
  conveyor movement.
- The node sends `auto_command` (default `R80`) immediately, starts a
  one-shot timer for `auto_run_duration_sec` (default `5.0`), then sends
  `STOP` when the timer fires.
- Held-high or repeated `True` publishes do not re-trigger; the next
  movement requires the topic to drop to `False` and rise again.
- A second edge that arrives while a previous run is still active is
  logged and ignored.

This is **duration-based, not step-based.** Tuning `auto_command` (speed)
and `auto_run_duration_sec` (time) controls the *approximate* per-nut
advance distance:

```
distance ≈ (belt_speed_at_command) × auto_run_duration_sec
```

Belt speed at a given command depends on `MAX_STEP_RATE_HZ` in the
Arduino sketch and the belt mechanics. **Exact, repeatable distance per
trigger requires firmware step mode** (e.g., a new `S<steps>` command in
the sketch that runs a fixed step count and acknowledges back). That
firmware change is intentionally out of scope for this package — see the
"Future work" section below.

Operational logs:

```
[conveyor_start] command=R80 duration=5.00s (place_ready edge)
[conveyor_stop]  command was R80, duration=5.00s elapsed
```

Grep these in the launch terminal to verify each pick produced exactly
one belt advance.

## Parameters

| Name | Default | Description |
| --- | --- | --- |
| `port` | `/dev/ttyACM0` | Arduino UNO USB serial device |
| `baudrate` | `115200` | Serial baudrate |
| `serial_timeout` | `1.0` | Read/write timeout in seconds |
| `arduino_reset_delay` | `2.0` | Delay after opening serial so the UNO can reset |
| `command_topic` | `/conveyor_cmd` | ROS topic used for manual conveyor commands |
| `place_ready_topic` | `/conveyor/place_ready` | Bool topic; False→True edge triggers one movement |
| `auto_command` | `R80` | Command sent on edge. `F<1-100>` or `R<1-100>`; `STOP` rejected |
| `auto_run_duration_sec` | `5.0` | Seconds to run before sending `STOP`. Tune for per-nut distance |

## Build

From the workspace root:

```bash
colcon build --packages-select conveyor_controller
source install/setup.bash
```

`pyserial` is required at runtime:

```bash
sudo apt install python3-serial
```

## Run

Using the launch file:

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py
```

Override the serial port or baudrate:

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py port:=/dev/ttyACM0 baudrate:=115200
```

Tune the per-nut advance without editing YAML or rebuilding:

```bash
ros2 launch conveyor_controller conveyor_controller.launch.py \
    auto_command:=R30 auto_run_duration_sec:=2.0
```

Run the node directly:

```bash
ros2 run conveyor_controller conveyor_serial_node --ros-args -p port:=/dev/ttyACM0 -p baudrate:=115200
```

Send commands:

```bash
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'F30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'R30'}"
ros2 topic pub --once /conveyor_cmd std_msgs/msg/String "{data: 'STOP'}"
```

## Arduino Sketch Contract

Upload `arduino/ConveyorControl_Program/ConveyorControl_Program.ino` to the
Arduino UNO. It reads newline-terminated serial commands and handles
`F<1-100>`, `R<1-100>`, and `STOP`. Keep the sketch baudrate matched to the ROS
parameter, which defaults to `115200`.

Default UNO wiring for a STEP/DIR driver:

| Arduino pin | Driver signal |
| --- | --- |
| D2 | STEP |
| D3 | DIR |
| D4 | ENABLE |
| GND | Driver signal ground |

Tune these constants in the sketch for your hardware:

- `MAX_STEP_RATE_HZ`: conveyor speed at `F100` or `R100`
- `FORWARD_DIR_LEVEL`: flip if forward/reverse are swapped
- `ENABLE_ACTIVE_LOW`: flip if your driver enable pin uses active-high logic
- `COMMAND_TIMEOUT_MS`: optional automatic stop if serial commands stop arriving

## Future work: exact per-trigger distance (firmware step mode)

Today's place-ready trigger advances the belt for `auto_run_duration_sec`
at a velocity-control command. Distance is therefore proportional to
duration × belt speed, but not deterministic across hardware variation
(driver microstepping changes, motor torque drop-off, belt slack).

A stricter "move exactly N steps and ack" mode would require:

1. **Firmware:** parse a new `S<N>` (or `D<mm>`) command, drive the
   step pin for exactly `N` step pulses, then idle. Optionally reply
   `OK\n` on completion.
2. **ROS node:** swap the duration-based timer for a wait-for-ack
   round-trip on the `S<N>` write, or keep the timer as a watchdog.
3. **Calibration:** measure mm per step for the deployed belt/pulley
   (`mm_per_step = belt_pitch / pulley_teeth × microstep_factor`).

Until that lands, treat `auto_command` and `auto_run_duration_sec` as
the tuning knobs for approximate per-nut advance, and verify the actual
per-trigger distance with a tape measure when the belt is first set up.
