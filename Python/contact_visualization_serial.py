import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import time

# 🔌 change this
ser = serial.Serial('/dev/ttyACM0', 921600, timeout=0.02)

# Sensor geometry (must match physical sensor order in incoming serial data).
# Angles are in degrees around the circle, 0 deg = +X direction.
CENTER_X = 0
CENTER_Y = 0
SENSOR_RADIUS = 70.0
SENSOR_ANGLES_DEG = np.array([0.0, 25.0, 50.0, 75.0])

# Local sensor-axis mapping.
# Assumes incoming components are [tangential, radial, normal].
TANGENTIAL_AXIS_INDEX = 0
RADIAL_AXIS_INDEX = 1
NORMAL_AXIS_INDEX = 2

# Use -1.0 here if a local axis points opposite to the assumed direction.
TANGENTIAL_AXIS_SIGN = 1.0
RADIAL_AXIS_SIGN = 1.0
NORMAL_AXIS_SIGN = 1.0

sensor_pos = np.column_stack(
    (
        CENTER_X + SENSOR_RADIUS * np.cos(np.deg2rad(SENSOR_ANGLES_DEG)),
        CENTER_Y + SENSOR_RADIUS * np.sin(np.deg2rad(SENSOR_ANGLES_DEG)),
        np.zeros(len(SENSOR_ANGLES_DEG))
    )
)

MAG_MIN = 0.0
MAG_MAX = 300.0
HIGHLIGHT_THRESHOLD = 150.0
PLOT_MARGIN = 15.0
RING_SAMPLE_COUNT = 360
ARC_START_DEG = float(SENSOR_ANGLES_DEG[0])
ARC_END_DEG = float(SENSOR_ANGLES_DEG[-1])

plt.ion()
fig, ax = plt.subplots()
ring_angles_deg = np.linspace(ARC_START_DEG, ARC_END_DEG, RING_SAMPLE_COUNT + 1)
ring_angles_rad = np.deg2rad(ring_angles_deg)
ring_points = np.column_stack(
    (
        CENTER_X + SENSOR_RADIUS * np.cos(ring_angles_rad),
        CENTER_Y + SENSOR_RADIUS * np.sin(ring_angles_rad)
    )
)
ring_segments = np.stack((ring_points[:-1], ring_points[1:]), axis=1)
ring_collection = LineCollection(
    ring_segments,
    cmap='viridis',
    linewidths=6,
)
ring_collection.set_clim(MAG_MIN, MAG_MAX)
ring_collection.set_array(np.zeros(len(ring_segments)))
ax.add_collection(ring_collection)

sensor_scatter = ax.scatter(
    sensor_pos[:, 0],
    sensor_pos[:, 1],
    c=np.zeros(len(sensor_pos)),
    cmap='viridis',
    s=140,
    vmin=MAG_MIN,
    vmax=MAG_MAX,
    edgecolors='black',
    zorder=3
)
highlight_scatter = ax.scatter(
    [],
    [],
    s=320,
    facecolors='none',
    edgecolors='red',
    linewidths=2.5,
    zorder=4
)
colorbar = fig.colorbar(ring_collection, ax=ax)
colorbar.set_label("Measured field magnitude")
ax.set_title("Live Circular Sensor Field View")
ax.set_xlabel("X position")
ax.set_ylabel("Y position")
ax.set_aspect('equal', adjustable='box')
ax.set_xlim(CENTER_X - SENSOR_RADIUS - PLOT_MARGIN, CENTER_X + SENSOR_RADIUS + PLOT_MARGIN)
ax.set_ylim(CENTER_Y - SENSOR_RADIUS - PLOT_MARGIN, CENTER_Y + SENSOR_RADIUS + PLOT_MARGIN)

circle_outline = plt.Circle((CENTER_X, CENTER_Y), SENSOR_RADIUS, color='black', fill=False, linewidth=1.0, alpha=0.35)
ax.add_patch(circle_outline)
for index, (x_pos, y_pos, _) in enumerate(sensor_pos):
    ax.text(x_pos, y_pos, str(index + 1), ha='center', va='center', color='black', fontsize=8, zorder=5)


def interpolate_ring_magnitude(sensor_magnitude):
    return np.interp(ring_angles_deg[:-1], SENSOR_ANGLES_DEG, sensor_magnitude)

def parse_line(line):
    tokens = [token.strip() for token in line.split(',') if token.strip()]
    expected_values = len(sensor_pos) * 3
    if len(tokens) != expected_values:
        raise ValueError(f"Expected {expected_values} numeric values, got {len(tokens)}")

    vals = [float(token) for token in tokens]
    return np.array(vals).reshape(len(sensor_pos), 3)


def rotate_sensor_vectors(sensor_vectors):
    angles_rad = np.deg2rad(SENSOR_ANGLES_DEG)
    tangential = TANGENTIAL_AXIS_SIGN * sensor_vectors[:, TANGENTIAL_AXIS_INDEX]
    radial = RADIAL_AXIS_SIGN * sensor_vectors[:, RADIAL_AXIS_INDEX]
    normal = NORMAL_AXIS_SIGN * sensor_vectors[:, NORMAL_AXIS_INDEX]

    tangent_x = -np.sin(angles_rad)
    tangent_y = np.cos(angles_rad)
    radial_x = np.cos(angles_rad)
    radial_y = np.sin(angles_rad)

    global_x = tangential * tangent_x + radial * radial_x
    global_y = tangential * tangent_y + radial * radial_y

    return np.column_stack((global_x, global_y, normal))


def read_latest_line(serial_port, max_drain_lines=200):
    latest_bytes = serial_port.readline()
    if not latest_bytes:
        return ""

    drained = 0
    while serial_port.in_waiting > 0 and drained < max_drain_lines:
        newer_bytes = serial_port.readline()
        if newer_bytes:
            latest_bytes = newer_bytes
        drained += 1

    return latest_bytes.decode(errors='ignore').strip('\r\n')

# Reset the Arduino
ser.setDTR(False)
time.sleep(1)
ser.reset_input_buffer()
ser.setDTR(True)

try:
    while True:
        line = read_latest_line(ser)
        # print(line)  # Debug: print the raw line received
        if not line:
            continue

        try:
            B = parse_line(line)
        except ValueError as exc:
            print(f"Skipping malformed data: {exc}. Raw line: {line}")
            continue

        field_magnitude = np.linalg.norm(B, axis=1)
        ring_magnitude = interpolate_ring_magnitude(field_magnitude)
        highlight_mask = field_magnitude >= HIGHLIGHT_THRESHOLD

        ring_collection.set_array(ring_magnitude)
        sensor_scatter.set_array(field_magnitude)
        if np.any(highlight_mask):
            highlight_scatter.set_offsets(sensor_pos[highlight_mask, :2])
        else:
            highlight_scatter.set_offsets(np.empty((0, 2)))

        plt.pause(0.0001)

except KeyboardInterrupt:
    print("Stopping sensor view...")
finally:
    if ser.is_open:
        ser.close()
    plt.close(fig)