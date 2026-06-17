from setuptools import find_packages, setup

package_name = "dynasense_udp_receiver"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/udp_sensor_node.launch.py"]),
        ("share/" + package_name + "/config", ["config/udp_sensor_params.yaml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="DynaSense User",
    maintainer_email="user@example.com",
    description="ROS 2 UDP receiver for DynaSense sensor packets.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "udp_sensor_node = dynasense_udp_receiver.udp_sensor_node:main",
            "udp_sensor_subscriber = dynasense_udp_receiver.udp_sensor_subscriber:main",
        ],
    },
)
