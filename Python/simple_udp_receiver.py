import socket
import struct
import time

PORT = 4210
RATE_REPORT_INTERVAL_S = 1.0

# create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

sock.bind(("", PORT))

# send discovery broadcast
sock.sendto(b"DISCOVER", ("255.255.255.255", PORT))

print("Sent discovery... waiting for data")

last_rate_report_time = time.perf_counter()
packets_since_report = 0

while True:
    data, addr = sock.recvfrom(1024)

    if len(data) == 96:
        values = struct.unpack("<24f", data)
        packets_since_report += 1
        current_time = time.perf_counter()
        elapsed_since_report = current_time - last_rate_report_time
        if elapsed_since_report >= RATE_REPORT_INTERVAL_S:
            data_rate_hz = packets_since_report / elapsed_since_report
            print(f"Data rate: {data_rate_hz:.1f} packets/s")
            last_rate_report_time = current_time
            packets_since_report = 0
        print(tuple(round(value) for value in values))
    else:
        print("Received non-data packet:", data)
