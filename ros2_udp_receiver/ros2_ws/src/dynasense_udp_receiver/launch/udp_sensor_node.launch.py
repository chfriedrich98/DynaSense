from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    params_file = PathJoinSubstitution(
        [FindPackageShare("dynasense_udp_receiver"), "config", "udp_sensor_params.yaml"]
    )

    return LaunchDescription(
        [
            Node(
                package="dynasense_udp_receiver",
                executable="udp_sensor_node",
                name="dynasense_udp_receiver",
                output="screen",
                parameters=[params_file],
            )
        ]
    )
