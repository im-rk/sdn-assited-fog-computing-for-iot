#!/usr/bin/env python3
"""
Fire Alarm Sensor Simulator
============================
Sends fire/smoke sensor data to the SDN network endpoint.

IMPORTANT: This device does NOT know whether data goes to Fog or Cloud.
It only knows the single SDN endpoint address and sends all data there.

In Simulation mode:  sends to sdn_proxy.py  (127.0.0.1:9000)
In Mininet mode:     sends to 10.0.0.100:9000 — packets enter the OpenFlow
                     switch, which sends them to the Ryu SDN controller for
                     DPI and policy-driven routing to Fog or Cloud.
"""

import json
import time
import random
import socket
import argparse
from datetime import datetime

# Single SDN endpoint — device knows NOTHING about Fog/Cloud
# Simulation mode: 127.0.0.1  |  Mininet mode: 10.0.0.100 (passed via --host)
SDN_ENDPOINT_HOST = "127.0.0.1"
SDN_ENDPOINT_PORT = 9000

SENSOR_ID  = "FIRE_001"
LOCATION   = "Building A, Floor 2"


def read_smoke_sensor() -> int:
    """Simulate a smoke sensor reading (0-100%)."""
    return random.randint(0, 20)  # Normally calm


def generate_alarm_payload(smoke_level: int) -> dict:
    """
    Build a sensor payload.
    No destination fields -- the NETWORK decides where this goes.
    """
    return {
        "sensor_id":   SENSOR_ID,
        "sensor_type": "smoke_detector",
        "smoke_level": smoke_level,
        "status":      "ALARM" if smoke_level > 50 else "NORMAL",
        "location":    LOCATION,
        "timestamp":   datetime.now().isoformat(),
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
    parser = argparse.ArgumentParser(description="Fire Alarm Sensor Simulator")
    parser.add_argument("--host",          default=SDN_ENDPOINT_HOST)
    parser.add_argument("--port",    type=int, default=SDN_ENDPOINT_PORT)
    parser.add_argument("--interval",type=float, default=2.0,
                        help="Seconds between readings")
    parser.add_argument("--alarm-chance", type=float, default=0.15,
                        help="Probability of a high-smoke event (0-1)")
    args = parser.parse_args()

    print(f"Fire Alarm Sensor [{SENSOR_ID}] started")
    print(f"Sending to SDN Proxy -> {args.host}:{args.port}")
    print(f"  (The SDN proxy decides Fog or Cloud -- this device does not know)")
    print("-" * 55)

    sent = 0
    try:
        while True:
            if random.random() < args.alarm_chance:
                smoke = random.randint(55, 100)   # Elevated / dangerous
            else:
                smoke = read_smoke_sensor()        # Normal

            payload = generate_alarm_payload(smoke)
            sent += 1

            if send(payload, args.host, args.port):
                status = "ALERT" if smoke > 50 else "NORMAL"
                print(f"[{sent:04d}] Smoke={smoke:3d}% | Status={payload['status']}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nSensor stopped. Total readings sent: {sent}")


if __name__ == "__main__":
    main()
