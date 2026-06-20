import argparse
import csv
from pathlib import Path
import time

import numpy as np

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
except ImportError as exc:
    raise SystemExit(
        "Missing GUI dependencies. Install with: pip install pyqtgraph PyQt5"
    ) from exc


CENTER_X = 0.0
CENTER_Y = 0.0
SENSOR_RADIUS = 70.0
ANGLE_STEP = 30.0
NUM_SENSORS = 8
SENSOR_START_ANGLE_DEG = -90
SENSOR_ANGLES_DEG = SENSOR_START_ANGLE_DEG + np.arange(NUM_SENSORS) * ANGLE_STEP
PLOT_ROTATION_DEG = 180.0

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
COLLECTED_DATA_DIR = Path(__file__).with_name("collected_data")

PLOT_FPS = 100.0
CONTROL_FONT_PT = 30
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
sensor_label_pos = np.column_stack((label_x, label_y))

ring_angles_deg = np.linspace(ARC_START_DEG, ARC_END_DEG, RING_SAMPLE_COUNT, endpoint=False)
ring_angles_rad = np.deg2rad(ring_angles_deg)
ring_base_x = CENTER_X + SENSOR_RADIUS * np.cos(ring_angles_rad)
ring_base_y = CENTER_Y + SENSOR_RADIUS * np.sin(ring_angles_rad)
ring_x, ring_y = rotate_xy(ring_base_x, ring_base_y, PLOT_ROTATION_DEG)


def pick_csv_interactively():
    csv_files = sorted(COLLECTED_DATA_DIR.glob("**/*.csv"))
    if not csv_files:
        print(f"No CSV files found in {COLLECTED_DATA_DIR}")
        return None

    print("Available recordings:")
    for idx, path in enumerate(csv_files):
        print(f"  [{idx}] {path.relative_to(Path(__file__).parent)}")

    selection = input("Select file number: ").strip()
    try:
        selected_idx = int(selection)
    except ValueError:
        print("Invalid selection.")
        return None

    if selected_idx < 0 or selected_idx >= len(csv_files):
        print("Selection out of range.")
        return None

    return csv_files[selected_idx]


def load_replay_rows(csv_path: Path):
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        required = ["timestamp_perf_s"] + [f"sensor{i + 1}_mag" for i in range(NUM_SENSORS)]
        missing = [column for column in required if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(missing)}"
            )

        for row in reader:
            try:
                ts_perf = float(row["timestamp_perf_s"])
                magnitudes = np.array(
                    [float(row[f"sensor{i + 1}_mag"]) for i in range(NUM_SENSORS)],
                    dtype=np.float32,
                )
            except (TypeError, ValueError):
                continue
            rows.append((ts_perf, magnitudes))

    if not rows:
        raise ValueError("No valid rows found in CSV.")

    return rows


class ReplayPlot:
    def __init__(self, csv_path: Path, speed: float):
        self.csv_path = csv_path
        self.speed = max(1e-6, float(speed))
        self.rows = load_replay_rows(csv_path)
        self.t0 = self.rows[0][0]
        self.last_row = self.rows[-1][0]
        self.total_duration_s = self.last_row - self.t0
        self.current_idx = 0
        self.started_wall = time.perf_counter()
        self.highlight_threshold = float(HIGHLIGHT_THRESHOLD)

        self.app = pg.mkQApp("UDP Sensor Replay Viewer")
        self.win = QtWidgets.QWidget()
        self.win.setWindowTitle(f"Replay: {csv_path.name}")
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
        self.main_layout.addLayout(self.threshold_layout)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground("w")
        self.main_layout.addWidget(self.plot_widget)

        self.footer_layout = QtWidgets.QHBoxLayout()
        self.footer_layout.addStretch(1)
        self.hud_label = QtWidgets.QLabel("replay t: -- s | speed: --")
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

        self.arrow_line_items = []
        self.arrow_head_items = []
        for _ in range(NUM_SENSORS):
            line_item = pg.PlotDataItem(pen=pg.mkPen(ARROW_COLOR, width=ARROW_LINE_WIDTH))
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

        self.draw_timer = QtCore.QTimer()
        self.draw_timer.timeout.connect(self._on_draw_tick)
        self.draw_timer.start(max(1, int(1000.0 / PLOT_FPS)))

        print(
            f"Loaded {len(self.rows)} frames from {self.csv_path} | "
            f"duration={self.total_duration_s:.2f}s | speed=x{self.speed:.2f}"
        )

    def _on_threshold_changed(self, value):
        self.highlight_threshold = float(value)
        self.threshold_value_label.setText(str(value))

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

    def _current_replay_time(self):
        elapsed_wall = time.perf_counter() - self.started_wall
        return self.t0 + elapsed_wall * self.speed

    def _on_draw_tick(self):
        replay_ts = self._current_replay_time()

        while self.current_idx + 1 < len(self.rows) and self.rows[self.current_idx + 1][0] <= replay_ts:
            self.current_idx += 1

        _, sensor_mag = self.rows[self.current_idx]
        ring_mag = np.interp(ring_angles_deg, SENSOR_ANGLES_DEG, sensor_mag)

        self.ring_item.setData(
            x=ring_x,
            y=ring_y,
            brush=self._magnitude_to_brushes(ring_mag),
            size=self._magnitude_to_ring_sizes(ring_mag),
            pen=None,
        )

        sum_dx = 0.0
        sum_dy = 0.0
        for i in range(NUM_SENSORS):
            sx, sy = sensor_pos[i, 0], sensor_pos[i, 1]
            udx = (CENTER_X - sx) / SENSOR_RADIUS
            udy = (CENTER_Y - sy) / SENSOR_RADIUS
            arrow_len = np.clip(sensor_mag[i] / MAG_MAX, 0.0, 1.0) * SENSOR_RADIUS * ARROW_LENGTH_SCALE
            dx = udx * arrow_len
            dy = udy * arrow_len
            ex = sx + dx
            ey = sy + dy
            self.arrow_line_items[i].setData([sx, ex], [sy, ey])
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

        elapsed_s = max(0.0, self.rows[self.current_idx][0] - self.t0)
        self.hud_label.setText(
            f"replay t: {elapsed_s:6.2f}s | speed: x{self.speed:.2f}"
        )

        if self.current_idx >= len(self.rows) - 1:
            self.draw_timer.stop()
            print("Replay finished.")

    def run(self):
        self.app.exec()


def main():
    parser = argparse.ArgumentParser(description="Replay recorded DynaSense CSV logs with live-style visualization.")
    parser.add_argument("csv_file", nargs="?", help="Path to CSV recording.")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier (2.0 = 2x, 0.5 = half speed).",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file) if args.csv_file else pick_csv_interactively()
    if csv_path is None:
        return
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    replay = ReplayPlot(csv_path=csv_path, speed=args.speed)
    replay.run()


if __name__ == "__main__":
    main()
