# DynaSense ROS 1 Noetic UDP Receiver (Docker)

This mirrors the ROS 2 receiver setup with ROS 1 Noetic.

## Topics published

- `/dynasense/raw_flat` (`std_msgs/Float32MultiArray`)
- `/dynasense/ordered_vectors` (`std_msgs/Float32MultiArray`)
- `/dynasense/magnitudes` (`std_msgs/Float32MultiArray`)
- `/dynasense/knee_vis` (`dynasense_udp_receiver_ros1/KneeVisMsg`)

## Run in Docker

From `ros1_udp_receiver/`:

```bash
docker compose build
```

Attach a shell:

```bash
docker compose up -d dynasense-ros1-udp
docker compose exec dynasense-ros1-udp bash
```

```bash
source /opt/ros/noetic/setup.bash
source /workspaces/dynasense/ros1_udp_receiver/catkin_ws/devel/setup.bash
rostopic echo /dynasense/knee_vis
```

Stop when done:

```bash
docker compose down
```

## Parameters

Default parameters are in:

- `catkin_ws/src/dynasense_udp_receiver_ros1/config/udp_sensor_params.yaml`

## Message definition

`KneeVisMsg.msg`:

```text
string leg_id
float64 angle
float64 magnitude
```
