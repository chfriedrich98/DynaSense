import csv
import time
import argparse
import os
import glob
import matplotlib.pyplot as plt

heatmap_rows = 3
heatmap_cols = 4

def pick_csv_interactively():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'collected_data')
    csv_files = sorted(glob.glob(os.path.join(data_dir, '**', '*.csv'), recursive=True))
    if not csv_files:
        print("No CSV files found in", data_dir)
        return None
    print("Available recordings:")
    for i, path in enumerate(csv_files):
        print(f"  [{i}] {os.path.relpath(path, script_dir)}")
    idx = int(input("Select file number: "))
    return csv_files[idx]


def replay(csv_path, speed=1.0):
    print(f"Replaying: {csv_path}  (speed x{speed})")

    plt.ion()
    figure, axis = plt.subplots()
    heatmap = axis.imshow(
        [[0.0] * heatmap_cols for _ in range(heatmap_rows)],
        cmap="viridis", aspect="auto"
    )
    axis.set_title(f"Replay: {os.path.basename(csv_path)}")
    axis.set_xlabel("Column")
    axis.set_ylabel("Row")
    axis.set_xticks(range(heatmap_cols))
    axis.set_yticks(range(heatmap_rows))
    figure.colorbar(heatmap, ax=axis)
    time_text = axis.text(
        0.01, 0.97, 't = 0.00 s',
        transform=axis.transAxes,
        va='top', ha='left',
        color='white', fontsize=10,
        bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.5)
    )
    plt.show(block=False)

    with open(csv_path, newline='') as f:
        reader = csv.reader(f)
        headers = next(reader)  # skip header row

        rows = list(reader)

    prev_ts = None
    wall_start = None

    for row in rows:
        if not row or len(row) < 2:
            continue

        try:
            ts = float(row[0])
        except ValueError:
            continue

        sensor_values = row[1:]

        if prev_ts is None:
            wall_start = time.monotonic()
            prev_ts = ts
        else:
            target_elapsed = (ts - rows[0][0] if False else ts - float(rows[0][0])) / speed
            elapsed = time.monotonic() - wall_start
            sleep_time = target_elapsed - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        try:
            values = [abs(float(v)) for v in sensor_values]
        except ValueError:
            print("Skipping malformed row:", row)
            continue

        if len(values) != heatmap_rows * heatmap_cols:
            print(f"Skipping row with unexpected value count ({len(values)}):", row)
            continue

        heatmap_grid = [
            [
                values[column * heatmap_rows + row_idx]
                for column in range(heatmap_cols)
            ]
            for row_idx in range(heatmap_rows)
        ]
        # Swap columns 3 and 4 (indices 2 and 3) — matches live script
        for grid_row in heatmap_grid:
            grid_row[2], grid_row[3] = grid_row[3], grid_row[2]

        heatmap.set_data(heatmap_grid)
        heatmap.set_clim(vmin=0, vmax=200)
        time_text.set_text(f't = {ts:.2f} s')
        plt.pause(0.001)

    print("Replay finished.")
    plt.ioff()
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Replay recorded DynaSense sensor data.")
    parser.add_argument('csv_file', nargs='?', help='Path to the CSV recording to replay.')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='Playback speed multiplier (e.g. 2.0 = double speed). Default: 1.0')
    args = parser.parse_args()

    csv_path = args.csv_file
    if not csv_path:
        csv_path = pick_csv_interactively()
    if not csv_path:
        return

    replay(csv_path, speed=args.speed)


if __name__ == '__main__':
    main()
