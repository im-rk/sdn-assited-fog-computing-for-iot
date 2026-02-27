#!/usr/bin/env python3
"""
Fog Server - Edge Computing Node
Handles CRITICAL data with low-latency processing

Runs on: 10.0.0.4:5001
"""

import json
import socket
import threading
import time
from datetime import datetime
from collections import deque
from flask import Flask, jsonify
import logging

# Configuration
HOST = '0.0.0.0'
UDP_PORT = 5001  # Critical data port
HTTP_PORT = 5101  # API endpoint
MAX_ALERTS = 100  # Keep last 100 alerts

# Shared data store
alerts_queue = deque(maxlen=MAX_ALERTS)
stats = {
    'total_alerts': 0,
    'critical_count': 0,
    'warning_count': 0,
    'avg_response_time_ms': 0,
    'start_time': datetime.now().isoformat()
}

# Flask app for API
app = Flask(__name__)
app.logger.setLevel(logging.WARNING)


def process_critical_alert(data):
    """Process critical alert with immediate action."""
    receive_time = datetime.now()
    
    # Simulate fast edge processing
    processing_start = time.time()
    
    # Parse and enrich the alert
    alert = {
        'id': stats['total_alerts'] + 1,
        'received_at': receive_time.isoformat(),
        'sensor_id': data.get('sensor_id', 'UNKNOWN'),
        'data_type': data.get('data_type', 'unknown'),
        'status': data.get('status', 'UNKNOWN'),
        'severity': data.get('severity', 'UNKNOWN'),
        'smoke_level': data.get('smoke_level', 0),
        'location': data.get('location', 'Unknown'),
        'action_taken': 'ALERT_DISPATCHED'
    }
    
    # Determine action based on severity
    if alert['severity'] == 'HIGH':
        alert['action_taken'] = 'EMERGENCY_SERVICES_NOTIFIED'
        stats['critical_count'] += 1
    else:
        alert['action_taken'] = 'SECURITY_NOTIFIED'
        stats['warning_count'] += 1
    
    processing_time = (time.time() - processing_start) * 1000  # ms
    alert['processing_time_ms'] = round(processing_time, 2)
    
    # Update stats
    stats['total_alerts'] += 1
    stats['avg_response_time_ms'] = round(
        (stats['avg_response_time_ms'] * (stats['total_alerts'] - 1) + processing_time) / stats['total_alerts'],
        2
    )
    
    # Store alert
    alerts_queue.append(alert)
    
    return alert


def udp_listener():
    """Listen for incoming UDP packets."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, UDP_PORT))

    print(f"Fog Server UDP listening on {HOST}:{UDP_PORT}")

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            message = json.loads(data.decode('utf-8'))

            alert = process_critical_alert(message)

            print(f"[{alert['id']}] PROCESSED | "
                  f"Severity: {alert['severity']} | "
                  f"Action: {alert['action_taken']} | "
                  f"Time: {alert['processing_time_ms']}ms")

        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON: {e}")
        except Exception as e:
            print(f"[ERROR] {e}")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'fog-server'})


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get server statistics."""
    return jsonify({
        'stats': stats,
        'uptime_seconds': (datetime.now() - datetime.fromisoformat(stats['start_time'])).total_seconds()
    })


@app.route('/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts."""
    return jsonify({
        'count': len(alerts_queue),
        'alerts': list(alerts_queue)
    })


@app.route('/alerts/latest', methods=['GET'])
def get_latest_alert():
    """Get the most recent alert."""
    if alerts_queue:
        return jsonify(alerts_queue[-1])
    return jsonify({'message': 'No alerts yet'}), 404


def main():
    print("=" * 60)
    print("FOG SERVER - Edge Computing Node")
    print("=" * 60)
    print(f"UDP Port: {UDP_PORT} (for CRITICAL IoT data)")
    print(f"HTTP Port: {HTTP_PORT} (for API access)")
    print(f"Low-latency processing enabled")
    print("=" * 60)
    
    # Start UDP listener in background
    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()
    
    # Start Flask API
    app.run(host=HOST, port=HTTP_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
