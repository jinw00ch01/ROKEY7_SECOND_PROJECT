import rclpy
from cobot_msgs.msg import RobotCommand
from rclpy.node import Node
from std_msgs.msg import String

from cobot_voice.firebase_bridge import publish_transcript, update_display_state


STATUS_TO_DISPLAY_STATE = {
    "idle": "idle",
    "wake_detected": "wake_detected",
    "listening": "listening_state",
    "transcribing": "listening_state",
    "processing": "recommending",
    "speaking": "asking_state",
    "error": "error",
}


class FirebaseStateBridge(Node):
    """Mirrors legacy ROS voice topics into /robot_session/current."""

    def __init__(self):
        super().__init__("firebase_state_bridge")

        self.create_subscription(String, "/voice/status", self.status_callback, 10)
        self.create_subscription(String, "/voice/text", self.text_callback, 10)
        self.create_subscription(RobotCommand, "/command/parsed", self.command_callback, 10)

        update_display_state("idle")
        self.get_logger().info("Firebase bridge started for robot_session/current.")

    def status_callback(self, msg):
        status = msg.data.strip() or "idle"
        display_state = STATUS_TO_DISPLAY_STATE.get(status)
        if display_state is None:
            self.get_logger().warning(f"Ignoring unknown voice status: {status}")
            return

        update_display_state(display_state)

    def text_callback(self, msg):
        text = msg.data.strip()
        publish_transcript(text)
        if text:
            update_display_state("recommending")
        self.get_logger().info(f"Updated session transcript: {text}")

    def command_callback(self, msg):
        self.get_logger().info(
            f"Received parsed command: action={msg.action}, targets={list(msg.targets)}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = FirebaseStateBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
