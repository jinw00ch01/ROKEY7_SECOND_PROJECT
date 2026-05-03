import os
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from ament_index_python.packages import get_package_share_directory
from dotenv import load_dotenv

from cobot_voice.stt import STT
from cobot_voice.wakeup_word import WakeupWord
from cobot_voice.mic_controller import MicController


class VoiceProcessingNode(Node):
    """Wake word detection + STT → publishes /voice/text."""

    def __init__(self):
        super().__init__('voice_processing_node')

        # Load environment
        package_path = get_package_share_directory("cobot_voice")
        load_dotenv(dotenv_path=os.path.join(package_path, "resource", ".env"))
        openai_api_key = os.getenv("OPENAI_API_KEY")

        # Initialize components
        self.stt = STT(openai_api_key=openai_api_key)
        self.mic = MicController()
        self.wakeup = WakeupWord(buffer_size=self.mic.config.buffer_size)

        # Publisher
        self.text_pub = self.create_publisher(String, '/voice/text', 10)

        # Start listening thread
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        self.get_logger().info("Voice processing node started. Listening for wake word '안녕 로키'...")

    def _listen_loop(self):
        self.mic.open_stream()
        self.wakeup.set_stream(self.mic.stream)

        while self._running:
            try:
                if self.wakeup.is_wakeup():
                    self.get_logger().info("Wake word detected! Recording...")
                    self.mic.close_stream()

                    text = self.stt.speech2text()
                    self.get_logger().info(f"STT result: {text}")

                    msg = String()
                    msg.data = text
                    self.text_pub.publish(msg)

                    self.mic.open_stream()
                    self.wakeup.set_stream(self.mic.stream)
                    self.get_logger().info("Listening for wake word...")
            except Exception as e:
                self.get_logger().error(f"Error in listen loop: {e}")
                break

    def destroy_node(self):
        self._running = False
        self.mic.close_stream()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceProcessingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
