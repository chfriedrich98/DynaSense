## Starting udp sensor node
### Docker setup
If ros2 is installed locally, this step can be skipped (untested).
Navigate to ros2_udp_receiver and run
```bash
docker compose build
```
This must be done on first use and whenever the code was changed.

Then start the container in the background:
```bash
docker compose up -d dynasense-ros2-udp
```

To open a shell in the running container:
```bash
docker compose exec dynasense-ros2-udp bash
```

After testing shut down the docker container:
```bash
docker compose down
```

### Run sensor node
If needed, run
```bash
source /opt/ros/humble/setup.bash
source /workspaces/dynasense/ros2_udp_receiver/ros2_ws/install/setup.bash
```

The service is configured to launch the udp sensor node automatically.
If you want to launch it manually, run:
```bash
ros2 launch dynasense_udp_receiver udp_sensor_node.launch.py
```

## Testing with subscriber node

### Docker setup
You can additionally attach a second terminal to the container:
```bash
docker compose exec dynasense-ros2-udp bash
```
then run
```bash
source /opt/ros/humble/setup.bash
source /workspaces/dynasense/ros2_udp_receiver/ros2_ws/install/setup.bash
```

### Starting subscriber node
You can then start the subscriber node with
```bash
ros2 run dynasense_udp_receiver udp_sensor_subscriber
```
