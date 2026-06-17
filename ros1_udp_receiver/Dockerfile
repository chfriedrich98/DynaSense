FROM ros:noetic-ros-base

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-numpy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspaces/dynasense/ros1_udp_receiver/catkin_ws

COPY catkin_ws/src ./src

RUN source /opt/ros/noetic/setup.bash \
    && catkin_make

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["roslaunch", "dynasense_udp_receiver_ros1", "udp_sensor_node.launch"]
