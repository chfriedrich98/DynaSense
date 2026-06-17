#!/usr/bin/env bash
set -e

source /opt/ros/noetic/setup.bash
source /workspaces/dynasense/ros1_udp_receiver/catkin_ws/devel/setup.bash

exec "$@"
