import os
from datetime import datetime, timezone

import firebase_admin
from ament_index_python.packages import get_package_share_directory
from cobot_msgs.msg import RobotCommand
from dotenv import load_dotenv
from firebase_admin import credentials, firestore
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class FirebaseStateBridge(Node):
    """Mirrors ROS voice topics into the web app's Firestore robot_state/loki doc."""

    def __init__(self):
        super().__init__("firebase_state_bridge")

        package_path = get_package_share_directory("cobot_voice")
        load_dotenv(dotenv_path=os.path.join(package_path, "resource", ".env"))

        self.db = self._init_firestore()
        self.doc_ref = self.db.collection("robot_state").document("loki")

        self.create_subscription(String, "/voice/status", self.status_callback, 10)
        self.create_subscription(String, "/voice/text", self.text_callback, 10)
        self.create_subscription(RobotCommand, "/command/parsed", self.command_callback, 10)

        self._update_state(
            {
                "mode": "idle",
                "wakeWordDetected": False,
                "commandText": "",
                "parsedAction": "",
                "targets": [],
            }
        )
        self.get_logger().info("Firebase state bridge started for robot_state/loki.")

    def _init_firestore(self):
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT")

        if not firebase_admin._apps:
            if service_account_path:
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()

        return firestore.client()

    def _update_state(self, fields):
        payload = {
            **fields,
            "updatedAt": datetime.now(timezone.utc),
        }
        self.doc_ref.set(payload, merge=True)

    def status_callback(self, msg):
        status = msg.data.strip() or "idle"
        self._update_state(
            {
                "mode": status,
                "wakeWordDetected": status in {"wake_detected", "listening", "processing"},
            }
        )

    def text_callback(self, msg):
        text = msg.data.strip()
        self._update_state(
            {
                "mode": "processing",
                "wakeWordDetected": True,
                "commandText": text,
            }
        )
        self.get_logger().info(f"Updated commandText: {text}")

    def command_callback(self, msg):
        self._update_state(
            {
                "mode": "idle",
                "wakeWordDetected": False,
                "parsedAction": msg.action,
                "targets": list(msg.targets),
            }
        )
        self.get_logger().info(
            f"Updated parsed command: action={msg.action}, targets={list(msg.targets)}"
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
