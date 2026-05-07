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

## Parameters

| Name | Default | Description |
| --- | --- | --- |
| `port` | `/dev/ttyACM0` | Arduino UNO USB serial device |
| `baudrate` | `115200` | Serial baudrate |
| `serial_timeout` | `1.0` | Read/write timeout in seconds |
| `arduino_reset_delay` | `2.0` | Delay after opening serial so the UNO can reset |
| `command_topic` | `/conveyor_cmd` | ROS topic used for conveyor commands |

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
