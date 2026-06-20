import socket
import struct
import time
import csv
from datetime import datetime
from pathlib import Path
import serial
import numpy as np

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
except ImportError as exc:
    raise SystemExit(
        "Missing GUI dependencies. Install with: pip install pyqtgraph PyQt5"
    ) from exc

PORT = 4210

# Serial is only used to reset the device before listening.
SERIAL_PORT = "/dev/ttyACM0"
SERIAL_BAUD = 921600
SERIAL_TIMEOUT_S = 0.02
STARTUP_DELAY_S = 5.0

CENTER_X = 0.0
CENTER_Y = 0.0
SENSOR_RADIUS = 70.0
ANGLE_STEP = 30.0
NUM_SENSORS = 8
SENSOR_START_ANGLE_DEG = -90
SENSOR_ANGLES_DEG = SENSOR_START_ANGLE_DEG + np.arange(NUM_SENSORS) * ANGLE_STEP
PLOT_ROTATION_DEG = 180.0

AXES_PER_SENSOR = 3
FLOAT_SIZE_BYTES = 4
SENSOR_COUNT = len(SENSOR_ANGLES_DEG)
PACKET_FLOAT_COUNT = SENSOR_COUNT * AXES_PER_SENSOR
PACKET_SIZE = PACKET_FLOAT_COUNT * FLOAT_SIZE_BYTES

MAG_MIN = 0.0
MAG_MAX = 1000.0
HIGHLIGHT_THRESHOLD = 300.0
HIGHLIGHT_SLIDER_MIN = int(MAG_MIN)
HIGHLIGHT_SLIDER_MAX = int(MAG_MAX)
RING_SIZE_MIN = 15
RING_SIZE_MAX = 50
PLOT_MARGIN = 15.0
RING_SAMPLE_COUNT = 360
ARROW_COLOR = (70, 200, 90, 220)
ARROW_LINE_WIDTH = 2
ARROW_HEAD_LEN = 14
ARROW_HEAD_WIDTH = 10
ARROW_LENGTH_SCALE = 0.5
SUM_ARROW_COLOR = (255, 120, 40, 235)
SUM_ARROW_LINE_WIDTH = 4
SUM_ARROW_HEAD_LEN = 18
SUM_ARROW_HEAD_WIDTH = 14
ARC_START_DEG = float(SENSOR_ANGLES_DEG[0])
ARC_END_DEG = float(SENSOR_ANGLES_DEG[-1])
PLOT_X_MIN = CENTER_X - SENSOR_RADIUS - PLOT_MARGIN
PLOT_X_MAX = CENTER_X + SENSOR_RADIUS + PLOT_MARGIN
PLOT_Y_MIN = CENTER_Y - SENSOR_RADIUS - PLOT_MARGIN
PLOT_Y_MAX = CENTER_Y + SENSOR_RADIUS + PLOT_MARGIN

BACKGROUND_IMAGE_PATH = Path(__file__).with_name("eFlesh_background.png")
BACKGROUND_IMAGE_OPACITY = 0.35
BACKGROUND_DISPLAY_SHIFT_X = -20.0
BACKGROUND_DISPLAY_SHIFT_Y = -15.0
SETTINGS_YAML_PATH = Path(__file__).with_name("udp_viewer_settings.yaml")
COLLECTED_DATA_DIR = Path(__file__).with_name("collected_data")

# Render and IO cadence are independent to minimize perceived latency.
PLOT_FPS = 100.0
RECV_POLL_INTERVAL_MS = 0
MAX_DRAIN_PACKETS = 800
RATE_REPORT_INTERVAL_S = 1.0

CONTROL_FONT_PT = 30
ORDER_CONTROL_FONT_PT = 14
SENSOR_INDEX_FONT_PT = 13
SENSOR_VALUE_FONT_PT = 30
HUD_FONT_PT = 30


def rotate_xy(x, y, angle_deg, center_x=CENTER_X, center_y=CENTER_Y):
    angle_rad = np.deg2rad(angle_deg)
    cos_theta = np.cos(angle_rad)
    sin_theta = np.sin(angle_rad)
    dx = x - center_x
    dy = y - center_y
    return (
        center_x + dx * cos_theta - dy * sin_theta,
        center_y + dx * sin_theta + dy * cos_theta,
    )


sensor_base_x = CENTER_X + SENSOR_RADIUS * np.cos(np.deg2rad(SENSOR_ANGLES_DEG))
sensor_base_y = CENTER_Y + SENSOR_RADIUS * np.sin(np.deg2rad(SENSOR_ANGLES_DEG))
sensor_x, sensor_y = rotate_xy(sensor_base_x, sensor_base_y, PLOT_ROTATION_DEG)

sensor_pos = np.column_stack(
    (
        sensor_x,
        sensor_y,
        np.zeros(len(SENSOR_ANGLES_DEG)),
    )
)
label_base_x = CENTER_X + (SENSOR_RADIUS + 20.0) * np.cos(np.deg2rad(SENSOR_ANGLES_DEG))
label_base_y = CENTER_Y + (SENSOR_RADIUS + 20.0) * np.sin(np.deg2rad(SENSOR_ANGLES_DEG))
label_x, label_y = rotate_xy(label_base_x, label_base_y, PLOT_ROTATION_DEG)
sensor_label_pos = np.column_stack(
    (
        label_x,
        label_y,
    )
)

ring_angles_deg = np.linspace(ARC_START_DEG, ARC_END_DEG, RING_SAMPLE_COUNT, endpoint=False)
ring_angles_rad = np.deg2rad(ring_angles_deg)
ring_base_x = CENTER_X + SENSOR_RADIUS * np.cos(ring_angles_rad)
ring_base_y = CENTER_Y + SENSOR_RADIUS * np.sin(ring_angles_rad)
ring_x, ring_y = rotate_xy(ring_base_x, ring_base_y, PLOT_ROTATION_DEG)


class UdpLatestPacketReceiver:
    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("", port))
        self.sock.setblocking(False)

    def send_discovery(self):
        self.sock.sendto(b"DISCOVER", ("255.255.255.255", PORT))

    def poll_latest(self, packet_size=PACKET_SIZE, max_drain_packets=MAX_DRAIN_PACKETS):
        latest_data = None
        packets = 0

        for _ in range(max_drain_packets):
            try:
                data, _ = self.sock.recvfrom(1024)
            except BlockingIOError:
                break

            if len(data) == packet_size:
                latest_data = data
                packets += 1

        return latest_data, packets


class LiveUdpPlot:
    def __init__(self):
        self.receiver = UdpLatestPacketReceiver(PORT)
        self.receiver.send_discovery()
        print("Sent discovery... waiting for data")
        self._init_csv_logger()

        self.latest_packet = None
        self.latest_packet_recv_time = None
        self.packets_since_report = 0
        self.last_rate_report_time = time.perf_counter()
        self.last_draw_time = None
        self.render_fps = 0.0
        self.latency_sum_ms = 0.0
        self.latency_count = 0
        self.latency_min_ms = None
        self.latency_max_ms = None
        self.highlight_threshold = float(HIGHLIGHT_THRESHOLD)
        self.stream_order = np.arange(SENSOR_COUNT, dtype=np.int32)
        self._load_settings_yaml()
        self.b_offset = np.zeros((SENSOR_COUNT, AXES_PER_SENSOR))

        self.app = pg.mkQApp("UDP Sensor Low-Latency Viewer")
        self.win = QtWidgets.QWidget()
        self.win.setWindowTitle("Live Circular Sensor Field View (Low Latency)")
        self.main_layout = QtWidgets.QVBoxLayout(self.win)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(6)

        self.threshold_layout = QtWidgets.QHBoxLayout()
        self.threshold_label = QtWidgets.QLabel("Highlight threshold")
        self.threshold_value_label = QtWidgets.QLabel(f"{self.highlight_threshold:.0f}")
        self.threshold_label.setStyleSheet(f"font-size: {CONTROL_FONT_PT}pt;")
        self.threshold_value_label.setStyleSheet(f"font-size: {CONTROL_FONT_PT}pt;")
        self.threshold_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(HIGHLIGHT_SLIDER_MIN, HIGHLIGHT_SLIDER_MAX)
        self.threshold_slider.setValue(int(self.highlight_threshold))
        self.threshold_slider.setTickInterval(25)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)

        self.threshold_layout.addWidget(self.threshold_label)
        self.threshold_layout.addWidget(self.threshold_slider, 1)
        self.threshold_layout.addWidget(self.threshold_value_label)

        self.tare_button = QtWidgets.QPushButton("Tare")
        self.tare_button.setStyleSheet(f"font-size: {CONTROL_FONT_PT}pt;")
        self.tare_button.clicked.connect(self._on_tare_clicked)
        self.threshold_layout.addWidget(self.tare_button)

        self.main_layout.addLayout(self.threshold_layout)

        self.reorder_layout = QtWidgets.QHBoxLayout()
        self.reorder_label = QtWidgets.QLabel("Stream order (display->stream)")
        self.reorder_label.setStyleSheet(f"font-size: {ORDER_CONTROL_FONT_PT}pt;")
        self.reorder_input = QtWidgets.QLineEdit(self._order_to_text(self.stream_order))
        self.reorder_input.setPlaceholderText("e.g. 1,2,3,4,5,6,7,8")
        self.reorder_input.returnPressed.connect(self._on_apply_reorder_clicked)

        self.reorder_apply_button = QtWidgets.QPushButton("Apply order")
        self.reorder_apply_button.clicked.connect(self._on_apply_reorder_clicked)
        self.reorder_reset_button = QtWidgets.QPushButton("Reset")
        self.reorder_reset_button.clicked.connect(self._on_reset_reorder_clicked)
        self.reorder_status_label = QtWidgets.QLabel("")
        self.reorder_status_label.setStyleSheet(f"font-size: {ORDER_CONTROL_FONT_PT}pt;")

        self.reorder_layout.addWidget(self.reorder_label)
        self.reorder_layout.addWidget(self.reorder_input, 1)
        self.reorder_layout.addWidget(self.reorder_apply_button)
        self.reorder_layout.addWidget(self.reorder_reset_button)
        self.reorder_layout.addWidget(self.reorder_status_label)
        self.main_layout.addLayout(self.reorder_layout)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground("w")
        self.main_layout.addWidget(self.plot_widget)

        self.footer_layout = QtWidgets.QHBoxLayout()
        self.footer_layout.addStretch(1)
        self.hud_label = QtWidgets.QLabel("latency avg: -- ms | render: -- fps")
        self.hud_label.setStyleSheet(
            f"font-size: {HUD_FONT_PT}pt; color: white;"
            "background-color: rgba(0, 0, 0, 220); padding: 4px 8px; border-radius: 4px;"
        )
        self.footer_layout.addWidget(self.hud_label)
        self.main_layout.addLayout(self.footer_layout)

        self.win.show()

        self.plot = self.plot_widget.addPlot()
        self.plot.setAspectLocked(True)
        self.plot.hideAxis("left")
        self.plot.hideAxis("bottom")
        self.plot.setRange(
            xRange=(PLOT_X_MIN, PLOT_X_MAX),
            yRange=(PLOT_Y_MIN, PLOT_Y_MAX),
            disableAutoRange=True,
        )
        self._add_background_image()

        circle_t = np.linspace(0.0, 2.0 * np.pi, 240)
        circle_x = CENTER_X + SENSOR_RADIUS * np.cos(circle_t)
        circle_y = CENTER_Y + SENSOR_RADIUS * np.sin(circle_t)
        self.plot.plot(circle_x, circle_y, pen=pg.mkPen((70, 70, 70), width=RING_SIZE_MAX))

        sensor_index_font = QtGui.QFont()
        sensor_index_font.setPointSize(SENSOR_INDEX_FONT_PT)
        for index, (x_pos, y_pos, _) in enumerate(sensor_pos):
            label = pg.TextItem(text=str(index + 1), anchor=(0.5, 0.5), color=(20, 20, 20))
            label.setFont(sensor_index_font)
            label.setPos(x_pos, y_pos)
            self.plot.addItem(label)

        sensor_value_font = QtGui.QFont()
        sensor_value_font.setPointSize(SENSOR_VALUE_FONT_PT)
        self.sensor_value_labels = []
        for x_pos, y_pos in sensor_label_pos:
            value_label = pg.TextItem(
                text="--",
                anchor=(0.5, 0.5),
                color=(255, 255, 255),
                fill=pg.mkBrush(0, 0, 0, 180),
            )
            value_label.setFont(sensor_value_font)
            value_label.setPos(x_pos, y_pos)
            self.plot.addItem(value_label)
            self.sensor_value_labels.append(value_label)

        self.ring_item = pg.ScatterPlotItem(size=7, pen=None, pxMode=True)
        self.plot.addItem(self.ring_item)

        # Arrows from each sensor toward center, length scaled by magnitude
        self.arrow_line_items = []
        self.arrow_head_items = []
        for _i in range(SENSOR_COUNT):
            line_item = pg.PlotDataItem(
                pen=pg.mkPen(ARROW_COLOR, width=ARROW_LINE_WIDTH)
            )
            self.plot.addItem(line_item)
            self.arrow_line_items.append(line_item)

            arrow_head = pg.ArrowItem(
                angle=0,
                headLen=ARROW_HEAD_LEN,
                headWidth=ARROW_HEAD_WIDTH,
                tailLen=None,
                pen=pg.mkPen(ARROW_COLOR, width=1),
                brush=pg.mkBrush(*ARROW_COLOR),
            )
            self.plot.addItem(arrow_head)
            self.arrow_head_items.append(arrow_head)

        self.sum_arrow_line_item = pg.PlotDataItem(
            pen=pg.mkPen(SUM_ARROW_COLOR, width=SUM_ARROW_LINE_WIDTH)
        )
        self.plot.addItem(self.sum_arrow_line_item)
        self.sum_arrow_head_item = pg.ArrowItem(
            angle=0,
            headLen=SUM_ARROW_HEAD_LEN,
            headWidth=SUM_ARROW_HEAD_WIDTH,
            tailLen=None,
            pen=pg.mkPen(SUM_ARROW_COLOR, width=1),
            brush=pg.mkBrush(*SUM_ARROW_COLOR),
        )
        self.plot.addItem(self.sum_arrow_head_item)

        self.value_label_default_fill = pg.mkBrush(0, 0, 0, 180)
        self.value_label_default_border = pg.mkPen(None)
        self.value_label_highlight_fill = pg.mkBrush(255, 40, 40, 220)
        self.value_label_highlight_border = pg.mkPen(110, 25, 0, width=2)

        cmap = pg.ColorMap(
            np.array([0.0, 0.45, 0.75, 1.0]),
            np.array(
                [
                    [30, 30, 45, 255],
                    [55, 95, 220, 255],
                    [255, 180, 40, 255],
                    [255, 0, 0, 255],
                ],
                dtype=np.ubyte,
            ),
        )
        lut_size = 256
        lut = cmap.getLookupTable(0.0, 1.0, lut_size, alpha=False)
        self.lut_size_minus_1 = lut_size - 1
        self.lut_brushes = [pg.mkBrush(int(r), int(g), int(b), 255) for r, g, b in lut]

        self.recv_timer = QtCore.QTimer()
        self.recv_timer.timeout.connect(self._on_recv_tick)
        self.recv_timer.start(RECV_POLL_INTERVAL_MS)

        self.draw_timer = QtCore.QTimer()
        self.draw_timer.timeout.connect(self._on_draw_tick)
        self.draw_timer.start(max(1, int(1000.0 / PLOT_FPS)))

        self.rate_timer = QtCore.QTimer()
        self.rate_timer.timeout.connect(self._report_rate)
        self.rate_timer.start(int(RATE_REPORT_INTERVAL_S * 1000))

    def _add_background_image(self):
        if not BACKGROUND_IMAGE_PATH.exists():
            return

        pixmap = QtGui.QPixmap(str(BACKGROUND_IMAGE_PATH))
        if pixmap.isNull():
            print(f"Unable to load background image: {BACKGROUND_IMAGE_PATH}")
            return

        background_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        plot_width = PLOT_X_MAX - PLOT_X_MIN
        plot_height = PLOT_Y_MAX - PLOT_Y_MIN
        image_width = pixmap.width()
        image_height = pixmap.height()
        image_scale = min(plot_width / image_width, plot_height / image_height) * 1.25
        scaled_width = image_width * image_scale
        scaled_height = image_height * image_scale
        offset_x = PLOT_X_MIN + (plot_width - scaled_width) / 2.0 - 50
        offset_y = PLOT_Y_MIN + (plot_height - scaled_height) / 2.0 - 15
        center_x = offset_x + scaled_width / 2.0
        center_y = offset_y + scaled_height / 2.0
        center_x, center_y = rotate_xy(center_x, center_y, PLOT_ROTATION_DEG)
        center_x += BACKGROUND_DISPLAY_SHIFT_X
        center_y += BACKGROUND_DISPLAY_SHIFT_Y

        background_item.setOffset(-image_width / 2.0, -image_height / 2.0)
        background_item.setPos(center_x, center_y)
        background_item.setScale(image_scale)
        background_item.setRotation(PLOT_ROTATION_DEG)
        background_item.setTransformationMode(QtCore.Qt.TransformationMode.SmoothTransformation)
        background_item.setOpacity(BACKGROUND_IMAGE_OPACITY)
        background_item.setZValue(-100)
        self.plot.addItem(background_item)
        self.background_item = background_item

    def _on_threshold_changed(self, value):
        self.highlight_threshold = float(value)
        self.threshold_value_label.setText(str(value))

    def _init_csv_logger(self):
        COLLECTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = COLLECTED_DATA_DIR / f"udp_capture_{timestamp}.csv"
        self.csv_file = self.csv_path.open("w", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_file)

        header = ["timestamp_unix_s", "timestamp_perf_s"]
        header.extend(f"sensor{i + 1}_x" for i in range(SENSOR_COUNT))
        header.extend(f"sensor{i + 1}_y" for i in range(SENSOR_COUNT))
        header.extend(f"sensor{i + 1}_z" for i in range(SENSOR_COUNT))
        header.extend(f"sensor{i + 1}_mag" for i in range(SENSOR_COUNT))
        self.csv_writer.writerow(header)
        self.csv_file.flush()
        print(f"Logging UDP samples to: {self.csv_path}")

    def _log_packet_to_csv(self, vals):
        if vals.size != PACKET_FLOAT_COUNT:
            return

        b_raw = vals.reshape(SENSOR_COUNT, AXES_PER_SENSOR)
        b = b_raw[self.stream_order, :] - self.b_offset
        sensor_mag = np.linalg.norm(b, axis=1)

        row = [time.time(), time.perf_counter()]
        row.extend(float(v) for v in b[:, 0])
        row.extend(float(v) for v in b[:, 1])
        row.extend(float(v) for v in b[:, 2])
        row.extend(float(v) for v in sensor_mag)
        self.csv_writer.writerow(row)

    def _close_csv_logger(self):
        if getattr(self, "csv_file", None) is not None and not self.csv_file.closed:
            self.csv_file.flush()
            self.csv_file.close()

    def _load_settings_yaml(self):
        if not SETTINGS_YAML_PATH.exists():
            return

        try:
            content = SETTINGS_YAML_PATH.read_text(encoding="utf-8")
            stream_order_text = None
            for raw_line in content.splitlines():
                line = raw_line.split("#", 1)[0].strip()
                if not line or not line.startswith("stream_order:"):
                    continue
                stream_order_text = line.split(":", 1)[1].strip()
                break

            if not stream_order_text:
                raise ValueError("Missing stream_order entry.")

            normalized_text = stream_order_text.replace("[", "").replace("]", "")
            self.stream_order = self._parse_reorder_text(normalized_text)
            print(f"Loaded stream order from {SETTINGS_YAML_PATH}: {self._order_to_text(self.stream_order)}")
        except Exception as exc:
            print(f"Unable to load settings from {SETTINGS_YAML_PATH}: {exc}")

    def _save_settings_yaml(self):
        stream_order_text = ", ".join(str(int(i) + 1) for i in self.stream_order)
        content = (
            "# UDP viewer settings\n"
            f"stream_order: [{stream_order_text}]\n"
        )
        SETTINGS_YAML_PATH.write_text(content, encoding="utf-8")

    def _order_to_text(self, order):
        return ",".join(str(int(i) + 1) for i in order)

    def _parse_reorder_text(self, text):
        tokens = [token.strip() for token in text.replace(";", ",").split(",") if token.strip()]
        if len(tokens) != SENSOR_COUNT:
            raise ValueError(f"Need exactly {SENSOR_COUNT} indices.")

        try:
            order = np.array([int(token) - 1 for token in tokens], dtype=np.int32)
        except ValueError as exc:
            raise ValueError("Indices must be integers.") from exc

        if np.any(order < 0) or np.any(order >= SENSOR_COUNT):
            raise ValueError(f"Indices must be in 1..{SENSOR_COUNT}.")
        if len(np.unique(order)) != SENSOR_COUNT:
            raise ValueError("Each index must appear exactly once.")
        return order

    def _on_apply_reorder_clicked(self):
        try:
            new_order = self._parse_reorder_text(self.reorder_input.text())
        except ValueError as exc:
            self.reorder_status_label.setStyleSheet(
                f"font-size: {ORDER_CONTROL_FONT_PT}pt; color: rgb(170, 0, 0);"
            )
            self.reorder_status_label.setText(str(exc))
            return

        self.stream_order = new_order
        self.reorder_input.setText(self._order_to_text(self.stream_order))
        self._save_settings_yaml()
        # Reset baseline when channel mapping changes to avoid stale offsets.
        self.b_offset.fill(0.0)
        self.reorder_status_label.setStyleSheet(
            f"font-size: {ORDER_CONTROL_FONT_PT}pt; color: rgb(0, 120, 0);"
        )
        self.reorder_status_label.setText("Order applied and saved. Baseline reset.")

    def _on_reset_reorder_clicked(self):
        self.stream_order = np.arange(SENSOR_COUNT, dtype=np.int32)
        self.reorder_input.setText(self._order_to_text(self.stream_order))
        self._save_settings_yaml()
        self.b_offset.fill(0.0)
        self.reorder_status_label.setStyleSheet(
            f"font-size: {ORDER_CONTROL_FONT_PT}pt; color: rgb(0, 120, 0);"
        )
        self.reorder_status_label.setText("Order reset and saved. Baseline reset.")

    def _on_tare_clicked(self):
        """Save current sensor readings as the baseline offset."""
        if self.latest_packet is not None:
            vals = np.frombuffer(self.latest_packet, dtype="<f4", count=PACKET_FLOAT_COUNT)
            if vals.size == PACKET_FLOAT_COUNT:
                B_raw = vals.reshape(SENSOR_COUNT, AXES_PER_SENSOR)
                self.b_offset = B_raw[self.stream_order, :].copy()
                print(f"Tared at: {self.b_offset}")

    def _magnitude_to_brushes(self, magnitudes):
        denom = max(1e-9, (MAG_MAX - MAG_MIN))
        norm = (magnitudes - MAG_MIN) / denom
        idx = np.clip((norm * self.lut_size_minus_1).astype(np.int32), 0, self.lut_size_minus_1)
        return [self.lut_brushes[i] for i in idx]

    def _magnitude_to_ring_sizes(self, magnitudes):
        denom = max(1e-9, (MAG_MAX - MAG_MIN))
        norm = np.clip((magnitudes - MAG_MIN) / denom, 0.0, 1.0)
        return RING_SIZE_MIN + (RING_SIZE_MAX - RING_SIZE_MIN) * norm

    def _update_value_label(self, label, magnitude):
        is_highlighted = magnitude >= self.highlight_threshold
        label.setText(f"{magnitude:5.1f}", color=(20, 20, 20) if is_highlighted else (255, 255, 255))
        label.fill = self.value_label_highlight_fill if is_highlighted else self.value_label_default_fill
        label.border = self.value_label_highlight_border if is_highlighted else self.value_label_default_border
        label.update()

    def _on_recv_tick(self):
        latest_data, packet_count = self.receiver.poll_latest()
        if packet_count > 0:
            self.latest_packet = latest_data
            # print("values =", struct.unpack("<12f", latest_data))  # Debug: print the raw packet data
            self.latest_packet_recv_time = time.perf_counter()
            self.packets_since_report += packet_count
            vals = np.frombuffer(latest_data, dtype="<f4", count=PACKET_FLOAT_COUNT)
            self._log_packet_to_csv(vals)

    def _on_draw_tick(self):
        if self.latest_packet is None:
            return

        draw_now = time.perf_counter()
        if self.last_draw_time is not None:
            dt = draw_now - self.last_draw_time
            if dt > 1e-6:
                instant_fps = 1.0 / dt
                self.render_fps = (0.85 * self.render_fps) + (0.15 * instant_fps)
        self.last_draw_time = draw_now

        vals = np.frombuffer(self.latest_packet, dtype="<f4", count=PACKET_FLOAT_COUNT)
        if vals.size != PACKET_FLOAT_COUNT:
            return
        # print("Received packet with values:", vals)  # Debug: print the raw sensor values
        B_raw = vals.reshape(SENSOR_COUNT, AXES_PER_SENSOR)
        B = B_raw[self.stream_order, :] - self.b_offset
        # print("B:", B)  # Debug: print the raw sensor values
        sensor_mag = np.linalg.norm(B, axis=1)
        ring_mag = np.interp(ring_angles_deg, SENSOR_ANGLES_DEG, sensor_mag)

        self.ring_item.setData(
            x=ring_x,
            y=ring_y,
            brush=self._magnitude_to_brushes(ring_mag),
            size=self._magnitude_to_ring_sizes(ring_mag),
            pen=None,
        )

        # Update arrows: from sensor toward center, length proportional to magnitude
        sum_dx = 0.0
        sum_dy = 0.0
        for i in range(SENSOR_COUNT):
            sx, sy = sensor_pos[i, 0], sensor_pos[i, 1]
            # Unit vector from sensor toward center
            udx = (CENTER_X - sx) / SENSOR_RADIUS
            udy = (CENTER_Y - sy) / SENSOR_RADIUS
            arrow_len = np.clip(sensor_mag[i] / MAG_MAX, 0.0, 1.0) * SENSOR_RADIUS * ARROW_LENGTH_SCALE
            dx = udx * arrow_len
            dy = udy * arrow_len
            ex = sx + dx
            ey = sy + dy
            self.arrow_line_items[i].setData([sx, ex], [sy, ey])
            # ArrowItem angle=0 points left; positive angles rotate CW in screen coords (Y-down).
            # Data-coord direction angle (Y-up math convention): atan2(udy, udx).
            # Conversion to ArrowItem angle: 180 - math_angle accounts for left-default and Y-flip.
            math_angle_deg = np.degrees(np.arctan2(udy, udx))
            self.arrow_head_items[i].setPos(ex, ey)
            self.arrow_head_items[i].setStyle(angle=180.0 - math_angle_deg)
            sum_dx += dx
            sum_dy += dy

        sum_arrow_len = float(np.hypot(sum_dx, sum_dy))
        if sum_arrow_len > 1e-6:
            sum_arrow_max_len = SENSOR_RADIUS * ARROW_LENGTH_SCALE
            if sum_arrow_len > sum_arrow_max_len:
                scale = sum_arrow_max_len / sum_arrow_len
                sum_dx *= scale
                sum_dy *= scale

            sum_ex = CENTER_X + sum_dx
            sum_ey = CENTER_Y + sum_dy
            sum_math_angle_deg = np.degrees(np.arctan2(sum_dy, sum_dx))
            self.sum_arrow_line_item.setData([CENTER_X, sum_ex], [CENTER_Y, sum_ey])
            self.sum_arrow_head_item.setPos(sum_ex, sum_ey)
            self.sum_arrow_head_item.setStyle(angle=180.0 - sum_math_angle_deg)
        else:
            self.sum_arrow_line_item.setData([], [])
            self.sum_arrow_head_item.setPos(CENTER_X, CENTER_Y)

        for label, magnitude in zip(self.sensor_value_labels, sensor_mag):
            self._update_value_label(label, magnitude)

        if self.latest_packet_recv_time is None:
            latency_text = "--"
        else:
            latency_ms = (draw_now - self.latest_packet_recv_time) * 1000.0
            self.latency_sum_ms += latency_ms
            self.latency_count += 1

            latency_avg_ms = self.latency_sum_ms / self.latency_count
            latency_text = f"{latency_avg_ms:5.2f}"

        self.hud_label.setText(
            f"latency avg: {latency_text} ms | render: {self.render_fps:5.1f} fps"
        )

    def _report_rate(self):
        now = time.perf_counter()
        elapsed = now - self.last_rate_report_time
        if elapsed <= 0:
            return

        data_rate_hz = self.packets_since_report / elapsed
        print(f"Data rate: {data_rate_hz:.1f} packets/s")
        self.last_rate_report_time = now
        self.packets_since_report = 0
        self.latency_sum_ms = 0.0
        self.latency_count = 0
        self.latency_min_ms = None
        self.latency_max_ms = None

    def run(self):
        try:
            self.app.exec()
        finally:
            self._close_csv_logger()


def reset_device(serial_port=SERIAL_PORT, baud=SERIAL_BAUD, timeout_s=SERIAL_TIMEOUT_S):
    ser = serial.Serial(serial_port, baud, timeout=timeout_s)
    ser.setDTR(False)
    time.sleep(1)
    ser.reset_input_buffer()
    ser.setDTR(True)
    time.sleep(STARTUP_DELAY_S)
    ser.close()


if __name__ == "__main__":
    # reset_device()
    viewer = LiveUdpPlot()
    viewer.run()
