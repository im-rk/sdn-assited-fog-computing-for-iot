#!/usr/bin/env python3
"""
Temperature Sensor Simulator
==============================
Sends periodic temperature readings to the SDN Proxy.

IMPORTANT: This device does NOT know whether data goes to Fog or Cloud.
It just sends to the SDN Proxy on port 9000.
The SDN Proxy performs DPI and decides the destination automatically.
"""

import json
import time
import random
import socket
import argparse
from datetime import datetime

# Single SDN endpoint
SDN_PROXY_HOST = "127.0.0.1"
SDN_PROXY_PORT = 9000

SENSOR_ID = "TEMP_001"
LOCATION  = "Room A1"


def read_temperature() -> float:
    """Simulate a temperature reading with realistic Gaussian variation."""
    base = 25.0
    variation = random.gauss(0, 4)
    return round(base + variation, 2)


def generate_payload(temp: float) -> dict:
    """
    Build a temperature payload.
    No destination info -- SDN proxy classifies entirely from content.
    """
    aqi = random.randint(20, 180)

    return {
        "sensor_id":         SENSOR_ID,
        "sensor_type":       "temperature",
        "data_type":         "temperature",
        "value":             temp,
        "unit":              "celsius",
        "air_quality_index": aqi,
        "humidity":          round(random.uniform(30.0, 80.0), 1),
        "location":          LOCATION,
        "timestamp":         datetime.now().isoformat(),
    }


def send(payload: dict, host: str, port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps(payload).encode(), (host, port))
        sock.close()
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Temperature Sensor Simulator")
    parser.add_argument("--host",         default=SDN_PROXY_HOST)
    parser.add_argument("--port",   type=int,   default=SDN_PROXY_PORT)
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Seconds between readings")
    args = parser.parse_args()

    print(f"Temperature Sensor [{SENSOR_ID}] started")
    print(f"Sending to SDN Proxy -> {args.host}:{args.port}")
    print(f"  (The SDN proxy decides Fog or Cloud -- this device does not know)")
    print("-" * 55)

    sent = 0
    try:
        while True:
            temp = read_temperature()
            payload = generate_payload(temp)
            sent += 1

            if send(payload, args.host, args.port):
                warn = " [DANGER]" if temp >= 45 or temp <= 0 else ""
                print(f"[{sent:04d}] Temp={temp:6.2f}C | "
                      f"AQI={payload['air_quality_index']:3d} | "
                      f"Hum={payload['humidity']}%{warn}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nSensor stopped. Total readings sent: {sent}")


if __name__ == "__main__":
    main()
