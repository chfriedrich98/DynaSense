from __future__ import annotations

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray


class DynasenseUdpSubscriberNode(Node):
    def __init__(self) -> None:
        super().__init__("dynasense_udp_subscriber")

        self.declare_parameter("topic", "dynasense/magnitudes")
        self.declare_parameter("num_sensors", 8)
        self.declare_parameter("axes_per_sensor", 3)

        self.topic = str(self.get_parameter("topic").value)
        self.num_sensors = int(self.get_parameter("num_sensors").value)
        self.axes_per_sensor = int(self.get_parameter("axes_per_sensor").value)

        self.subscription = self.create_subscription(
            Float32MultiArray,
            self.topic,
            self._on_message,
            10,
        )

        self.get_logger().info(f"Subscribed to {self.topic}")

    def _on_message(self, msg: Float32MultiArray) -> None:
        data = np.array(msg.data, dtype=np.float32)

        if self.topic.endswith("/ordered_vectors"):
            expected = self.num_sensors * self.axes_per_sensor
            if data.size != expected:
                self.get_logger().warning(
                    f"ordered_vectors size mismatch: got {data.size}, expected {expected}"
                )
                return

            vectors = data.reshape(self.num_sensors, self.axes_per_sensor)
            first = ", ".join(f"{v:.2f}" for v in vectors[0])
            self.get_logger().info(
                f"ordered_vectors: shape={vectors.shape}, sensor1=[{first}]"
            )
            return

        if self.topic.endswith("/magnitudes"):
            if data.size != self.num_sensors:
                self.get_logger().warning(
                    f"magnitudes size mismatch: got {data.size}, expected {self.num_sensors}"
                )
                return

            self.get_logger().info(
                "magnitudes: " + ", ".join(f"{value:.2f}" for value in data)
            )
            return

        # Default handler for dynasense/raw_flat or any custom topic with same type.
        preview = ", ".join(f"{value:.2f}" for value in data[: min(6, data.size)])
        self.get_logger().info(f"{self.topic}: len={data.size}, head=[{preview}]")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DynasenseUdpSubscriberNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
