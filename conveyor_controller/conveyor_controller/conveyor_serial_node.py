import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from std_msgs.msg import String

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - handled at runtime on robot
    serial = None
    SerialException = Exception


class ConveyorSerialNode(Node):
    """Forward conveyor string commands from ROS 2 to an Arduino serial port."""

    MIN_SPEED_PERCENT = 1
    MAX_SPEED_PERCENT = 100

    def __init__(self):
        super().__init__('conveyor_serial_node')

        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('serial_timeout', 1.0)
        self.declare_parameter('arduino_reset_delay', 2.0)
        self.declare_parameter('command_topic', '/conveyor_cmd')
        self.declare_parameter('place_ready_topic', '/conveyor/place_ready')
        self.declare_parameter('auto_command', 'R80')
        self.declare_parameter('auto_run_duration_sec', 5.0)

        self.port = self.get_parameter('port').get_parameter_value().string_value
        self.baudrate = self.get_parameter('baudrate').get_parameter_value().integer_value
        self.serial_timeout = (
            self.get_parameter('serial_timeout').get_parameter_value().double_value
        )
        self.arduino_reset_delay = (
            self.get_parameter('arduino_reset_delay').get_parameter_value().double_value
        )
        self.command_topic = (
            self.get_parameter('command_topic').get_parameter_value().string_value
        )
        self.place_ready_topic = (
            self.get_parameter('place_ready_topic').get_parameter_value().string_value
        )
        self.auto_command = (
            self.get_parameter('auto_command').get_parameter_value().string_value.strip().upper()
        )
        self.auto_run_duration_sec = (
            self.get_parameter('auto_run_duration_sec').get_parameter_value().double_value
        )

        self.serial_port = None
        self._last_place_ready = False
        self._auto_stop_timer = None
        self._connect_serial()

        self.command_subscription = self.create_subscription(
            String,
            self.command_topic,
            self._command_callback,
            10,
        )
        self.place_ready_subscription = self.create_subscription(
            Bool,
            self.place_ready_topic,
            self._place_ready_callback,
            10,
        )

        self.get_logger().info(
            f'Listening on {self.command_topic} for commands: '
            'F<1-100>, R<1-100>, STOP'
        )
        self.get_logger().info(
            f'Place-ready trigger: one False->True edge on '
            f'{self.place_ready_topic} = one movement '
            f'(command={self.auto_command}, '
            f'duration={self.auto_run_duration_sec:.2f}s, then STOP). '
            f'Distance is approximate; exact distance requires firmware '
            f'step mode.'
        )

    def _connect_serial(self):
        if serial is None:
            self.get_logger().error(
                'pyserial is not installed. Install it with: sudo apt install python3-serial'
            )
            return

        try:
            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.serial_timeout,
                write_timeout=self.serial_timeout,
            )
            if self.arduino_reset_delay > 0.0:
                time.sleep(self.arduino_reset_delay)
            self.get_logger().info(
                f'Connected to Arduino serial port {self.port} at {self.baudrate} baud'
            )
        except SerialException as exc:
            self.serial_port = None
            self.get_logger().error(
                f'Failed to open serial port {self.port} at {self.baudrate} baud: {exc}'
            )

    def _command_callback(self, msg):
        command = msg.data.strip().upper()
        self._send_command(command, source='manual')

    def _place_ready_callback(self, msg):
        place_ready = bool(msg.data)
        should_trigger = place_ready and not self._last_place_ready
        self._last_place_ready = place_ready

        if not should_trigger:
            return

        if self._auto_stop_timer is not None:
            self.get_logger().warn('Ignoring place_ready trigger while conveyor auto-run is active')
            return

        if not self._is_valid_command(self.auto_command) or self.auto_command == 'STOP':
            self.get_logger().error(
                f'Invalid auto_command "{self.auto_command}". Expected F<1-100> or R<1-100>'
            )
            return

        if self.auto_run_duration_sec <= 0.0:
            self.get_logger().error('auto_run_duration_sec must be greater than 0')
            return

        if self._send_command(self.auto_command, source='place_ready'):
            self.get_logger().info(
                f'[conveyor_start] command={self.auto_command} '
                f'duration={self.auto_run_duration_sec:.2f}s (place_ready edge)'
            )
            self._auto_stop_timer = self.create_timer(
                self.auto_run_duration_sec,
                self._auto_stop_callback,
            )

    def _auto_stop_callback(self):
        if self._auto_stop_timer is not None:
            self._auto_stop_timer.cancel()
            self._auto_stop_timer = None
        self._send_command('STOP', source='place_ready')
        self.get_logger().info(
            f'[conveyor_stop] command was {self.auto_command}, '
            f'duration={self.auto_run_duration_sec:.2f}s elapsed'
        )

    def _send_command(self, command, source):
        if not self._is_valid_command(command):
            self.get_logger().warn(
                f'Ignoring invalid conveyor command "{command}" from {source}. '
                'Expected F<1-100>, R<1-100>, or STOP'
            )
            return False

        if self.serial_port is None or not self.serial_port.is_open:
            self.get_logger().warn('Serial port is not open; attempting reconnect')
            self._connect_serial()

        if self.serial_port is None or not self.serial_port.is_open:
            self.get_logger().error(f'Could not send "{command}" because serial is closed')
            return False

        try:
            self.serial_port.write(f'{command}\n'.encode('utf-8'))
            self.serial_port.flush()
            self.get_logger().info(f'Sent conveyor command from {source}: {command}')
            return True
        except SerialException as exc:
            self.get_logger().error(f'Failed to write "{command}" to serial: {exc}')
            self._close_serial()
            return False

    def _is_valid_command(self, command):
        if command == 'STOP':
            return True

        if len(command) < 2 or command[0] not in {'F', 'R'}:
            return False

        speed_text = command[1:]
        if not speed_text.isdigit():
            return False

        speed = int(speed_text)
        return self.MIN_SPEED_PERCENT <= speed <= self.MAX_SPEED_PERCENT

    def _close_serial(self):
        if self.serial_port is not None:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
            except SerialException as exc:
                self.get_logger().warn(f'Error while closing serial port: {exc}')
            finally:
                self.serial_port = None

    def destroy_node(self):
        if self._auto_stop_timer is not None:
            self._auto_stop_timer.cancel()
            self._auto_stop_timer = None
        self._close_serial()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ConveyorSerialNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
