#!/usr/bin/env bash
set -e

source /opt/ros/humble/setup.bash
source /workspaces/dynasense/ros2_udp_receiver/ros2_ws/install/setup.bash

exec "$@"
