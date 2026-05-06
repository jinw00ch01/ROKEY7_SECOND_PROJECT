import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from cobot_msgs.msg import RobotCommand
from cobot_voice.env import get_required_env
from cobot_voice.keyword_extractor import KeywordExtractor


class CommandParserNode(Node):
    """Subscribes /voice/text → extracts action & keywords → publishes /command/parsed."""

    def __init__(self):
        super().__init__('command_parser_node')

        # Load environment
        openai_api_key = get_required_env("OPENAI_API_KEY")

        # Initialize keyword extractor
        self.extractor = KeywordExtractor(openai_api_key=openai_api_key)

        # Subscriber & Publisher
        self.text_sub = self.create_subscription(
            String, '/voice/text', self.text_callback, 10
        )
        self.command_pub = self.create_publisher(RobotCommand, '/command/parsed', 10)

        self.get_logger().info("Command parser node started. Waiting for /voice/text...")

    def text_callback(self, msg):
        text = msg.data
        self.get_logger().info(f"Received text: '{text}'")

        action, targets = self.extractor.extract(text)
        self.get_logger().info(f"Parsed → action: {action}, targets: {targets}")

        cmd = RobotCommand()
        cmd.action = action
        cmd.targets = targets
        cmd.slots = []
        self.command_pub.publish(cmd)

        self.get_logger().info(f"Published /command/parsed: action={action}, targets={targets}")


def main(args=None):
    rclpy.init(args=args)
    node = CommandParserNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
