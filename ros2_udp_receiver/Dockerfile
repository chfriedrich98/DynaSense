FROM ros:humble-ros-base

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-numpy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspaces/dynasense/ros2_udp_receiver/ros2_ws

COPY ros2_ws/src ./src

RUN source /opt/ros/humble/setup.bash \
    && colcon build --symlink-install

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "dynasense_udp_receiver", "udp_sensor_node.launch.py"]
