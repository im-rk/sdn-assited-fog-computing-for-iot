#!/usr/bin/env python3
"""
Analytics Data Generator
==========================
Sends bulk historical sensor data to the SDN Proxy.

IMPORTANT: This device does NOT know whether data goes to Fog or Cloud.
It just sends to the SDN Proxy on port 9000.
The SDN Proxy performs DPI, detects the large payload size,
and routes to Cloud automatically.
"""

import json
import time
import random
import socket
import argparse
from datetime import datetime, timedelta

# Single SDN endpoint
SDN_PROXY_HOST = "127.0.0.1"
SDN_PROXY_PORT = 9000

SENSOR_ID = "ANALYTICS_001"


def generate_historical_readings(num_points: int = 50) -> list:
    """Generate a batch of past readings spanning 24 hours."""
    base_time  = datetime.now() - timedelta(hours=24)
    readings   = []

    for i in range(num_points):
        ts = base_time + timedelta(minutes=i * 30)
        readings.append({
            "timestamp":         ts.isoformat(),
            "temperature":       round(random.uniform(18.0, 35.0), 2),
            "humidity":          round(random.uniform(30.0, 80.0), 2),
            "pressure":          round(random.uniform(1000.0, 1025.0), 2),
            "air_quality_index": random.randint(20, 140),
            "co2_ppm":           random.randint(400, 1200),
        })

    return readings


def generate_payload(num_points: int = 50) -> dict:
    """
    Build a bulk analytics payload.
    No destination info -- SDN proxy detects large payload and routes to Cloud.
    """
    return {
        "sensor_id":   SENSOR_ID,
        "sensor_type": "multi_sensor_array",
        "data_type":   "bulk_historical",
        "num_points":  num_points,
        "data_points": generate_historical_readings(num_points),
        "timestamp":   datetime.now().isoformat(),
    }


def send(payload: dict, host: str, port: int) -> tuple:
    try:
        data = json.dumps(payload).encode()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(data, (host, port))
        sock.close()
        return True, len(data)
    except Exception as e:
        print(f"[ERROR] {e}")
        return False, 0


def main():
    parser = argparse.ArgumentParser(description="Analytics Data Generator")
    parser.add_argument("--host",         default=SDN_PROXY_HOST)
    parser.add_argument("--port",  type=int,   default=SDN_PROXY_PORT)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--points",   type=int,   default=50,
                        help="Data points per batch")
    args = parser.parse_args()

    print(f"Analytics Generator [{SENSOR_ID}] started")
    print(f"Sending to SDN Proxy -> {args.host}:{args.port}")
    print(f"  (SDN proxy detects bulk payload -> routes to Cloud automatically)")
    print("-" * 55)

    batch = 0
    try:
        while True:
            payload = generate_payload(args.points)
            batch  += 1
            ok, size = send(payload, args.host, args.port)

            if ok:
                print(f"[{batch:04d}] Sent {args.points} points | "
                      f"Payload: {size/1024:.1f} KB")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nGenerator stopped. Total batches sent: {batch}")


if __name__ == "__main__":
    main()
