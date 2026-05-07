import time

import rclpy
from rclpy.node import Node
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

        self.serial_port = None
        self._connect_serial()

        self.subscription = self.create_subscription(
            String,
            self.command_topic,
            self._command_callback,
            10,
        )

        self.get_logger().info(
            f'Listening on {self.command_topic} for commands: '
            'F<1-100>, R<1-100>, STOP'
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

        if not self._is_valid_command(command):
            self.get_logger().warn(
                f'Ignoring invalid conveyor command "{msg.data}". '
                'Expected F<1-100>, R<1-100>, or STOP'
            )
            return

        if self.serial_port is None or not self.serial_port.is_open:
            self.get_logger().warn('Serial port is not open; attempting reconnect')
            self._connect_serial()

        if self.serial_port is None or not self.serial_port.is_open:
            self.get_logger().error(f'Could not send "{command}" because serial is closed')
            return

        try:
            self.serial_port.write(f'{command}\n'.encode('utf-8'))
            self.serial_port.flush()
            self.get_logger().info(f'Sent conveyor command: {command}')
        except SerialException as exc:
            self.get_logger().error(f'Failed to write "{command}" to serial: {exc}')
            self._close_serial()

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
