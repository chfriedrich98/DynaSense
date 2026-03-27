import serial
from serial.tools import list_ports
import time
import csv
from datetime import datetime
import matplotlib.pyplot as plt
import os

ports = list_ports.comports()
for port in ports: print (port)

port = '/dev/ttyACM0'  # Change this to your Arduino's port
baud_rate = 115200 # Change this to match the baud rate set for your Arduino
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
date_folder = datetime.now().strftime('%Y_%m_%d')
script_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(script_dir, 'collected_data', date_folder)
os.makedirs(data_path, exist_ok=True)
f = open(f'{data_path}/sensor_data_{timestamp}.csv', 'w', newline='')
writer = csv.writer(f, delimiter=',')
sensor_data_stream_started = False
headers = []
heatmap_rows = 3
heatmap_cols = 4
expected_value_count = heatmap_rows * heatmap_cols

serialCom = serial.Serial(port, baud_rate, timeout=0.01)

plt.ion()
figure, axis = plt.subplots()
heatmap = axis.imshow([[0.0] * heatmap_cols for _ in range(heatmap_rows)], cmap="viridis", aspect="auto")
axis.set_title("Sensor Heatmap")
axis.set_xlabel("Column")
axis.set_ylabel("Row")
axis.set_xticks(range(heatmap_cols))
axis.set_yticks(range(heatmap_rows))
figure.colorbar(heatmap, ax=axis)
plt.show(block=False)

# Reset the Arduino
serialCom.setDTR(False)
time.sleep(1)
serialCom.flushInput()
serialCom.setDTR(True)

try:
    while True:
        try:
            s_bytes = serialCom.readline()
            if not s_bytes:
                continue

            decoded_bytes = s_bytes.decode('utf-8').strip('\r\n')
            if not sensor_data_stream_started: # Print initialization messages until the headers are received
                print(decoded_bytes)
                if decoded_bytes.startswith("headers"):
                    headers = decoded_bytes.split()
                    headers = headers[1:]  # Remove the "headers: " part

                    writer.writerow(headers)
                    print("Received headers:", headers)
                    sensor_data_stream_started = True
            else:
                latest_bytes = s_bytes
                while serialCom.in_waiting > 0:
                    newer_bytes = serialCom.readline()
                    if newer_bytes:
                        latest_bytes = newer_bytes
                    else:
                        break

                decoded_bytes = latest_bytes.decode('utf-8').strip('\r\n')
                data_values = decoded_bytes.split()

                sensor_values = data_values[1:]  # Remove the timestamp

                # if len(data_values) != expected_value_count:
                #     print("Skipping incomplete data row:", decoded_bytes)
                #     continue
                writer.writerow(data_values)
                print("Received data:", data_values)
                heatmap_values = [abs(float(value)) for value in sensor_values]
                heatmap_grid = [
                    [
                        heatmap_values[column * heatmap_rows + row]
                        for column in range(heatmap_cols)
                    ]
                    for row in range(heatmap_rows)
                ]
                # Swap columns 3 and 4 (indices 2 and 3)
                for row in heatmap_grid:
                    row[2], row[3] = row[3], row[2]
                heatmap.set_data(heatmap_grid)
                heatmap.set_clim(vmin=0, vmax=200)
                plt.pause(0.004)
        except Exception as error:
            print("Error reading from serial port:", error)
finally:
    print("Closing serial port.")
    serialCom.close()
    print("Serial port closed.")
    print("Closing plot.")
    plt.close(figure)
    print("Plot closed.")
    print("Closing CSV file.")
    f.close()
    print("CSV file closed.")
