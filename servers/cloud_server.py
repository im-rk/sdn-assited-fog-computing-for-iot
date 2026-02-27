#!/usr/bin/env python3
"""
Cloud Server - Heavy Analytics Processing
Handles ANALYTICS data for storage and ML processing

Runs on: 10.0.0.5:5002
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
UDP_PORT = 5002  # Analytics data port
HTTP_PORT = 5102  # API endpoint
MAX_RECORDS = 1000  # Keep last 1000 data points

# Shared data store
analytics_data = deque(maxlen=MAX_RECORDS)
stats = {
    'total_batches': 0,
    'total_data_points': 0,
    'total_bytes_received': 0,
    'avg_processing_time_ms': 0,
    'start_time': datetime.now().isoformat()
}

# Flask app for API
app = Flask(__name__)
app.logger.setLevel(logging.WARNING)


def process_analytics_data(data):
    """Process analytics data with heavy computation simulation."""
    receive_time = datetime.now()
    processing_start = time.time()
    
    # Simulate cloud processing (heavier than fog)
    time.sleep(0.01)  # Simulate processing delay
    
    batch_size = len(data.get('data_points', []))
    data_size = len(json.dumps(data))
    
    # Create record
    record = {
        'id': stats['total_batches'] + 1,
        'received_at': receive_time.isoformat(),
        'sensor_id': data.get('sensor_id', 'UNKNOWN'),
        'data_type': data.get('data_type', 'unknown'),
        'batch_size': batch_size,
        'payload_size_bytes': data_size,
        'request_type': data.get('request_type', 'UNKNOWN'),
        'status': 'PROCESSED'
    }
    
    # Perform "analytics" - calculate statistics from data points
    if data.get('data_points'):
        temps = [p.get('temperature', 0) for p in data['data_points'] if p.get('temperature')]
        if temps:
            record['analytics'] = {
                'avg_temperature': round(sum(temps) / len(temps), 2),
                'max_temperature': max(temps),
                'min_temperature': min(temps)
            }
    
    processing_time = (time.time() - processing_start) * 1000  # ms
    record['processing_time_ms'] = round(processing_time, 2)
    
    # Update stats
    stats['total_batches'] += 1
    stats['total_data_points'] += batch_size
    stats['total_bytes_received'] += data_size
    stats['avg_processing_time_ms'] = round(
        (stats['avg_processing_time_ms'] * (stats['total_batches'] - 1) + processing_time) / stats['total_batches'],
        2
    )
    
    # Store record
    analytics_data.append(record)
    
    return record


def udp_listener():
    """Listen for incoming UDP packets."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, UDP_PORT))

    print(f"Cloud Server UDP listening on {HOST}:{UDP_PORT}")

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            message = json.loads(data.decode('utf-8'))

            record = process_analytics_data(message)

            print(f"[{record['id']}] PROCESSED | "
                  f"Points: {record['batch_size']} | "
                  f"Size: {record['payload_size_bytes']/1024:.2f}KB | "
                  f"Time: {record['processing_time_ms']}ms")

        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON: {e}")
        except Exception as e:
            print(f"[ERROR] {e}")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'cloud-server'})


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get server statistics."""
    return jsonify({
        'stats': stats,
        'uptime_seconds': (datetime.now() - datetime.fromisoformat(stats['start_time'])).total_seconds(),
        'throughput_kbps': round(stats['total_bytes_received'] / 1024 /
                                 max(1, (datetime.now() - datetime.fromisoformat(stats['start_time'])).total_seconds()), 2)
    })


@app.route('/data', methods=['GET'])
def get_data():
    """Get processed analytics data."""
    return jsonify({
        'count': len(analytics_data),
        'records': list(analytics_data)[-50:]  # Return last 50
    })


@app.route('/data/summary', methods=['GET'])
def get_summary():
    """Get analytics summary."""
    if not analytics_data:
        return jsonify({'message': 'No data yet'}), 404

    all_analytics = [r.get('analytics', {}) for r in analytics_data if r.get('analytics')]

    if all_analytics:
        return jsonify({
            'total_batches': stats['total_batches'],
            'total_data_points': stats['total_data_points'],
            'overall_avg_temp': round(sum(a.get('avg_temperature', 0) for a in all_analytics) / len(all_analytics), 2)
        })

    return jsonify({'message': 'No analytics computed yet'}), 404


def main():
    print("=" * 60)
    print("CLOUD SERVER - Heavy Analytics Processing")
    print("=" * 60)
    print(f"UDP Port: {UDP_PORT} (for ANALYTICS IoT data)")
    print(f"HTTP Port: {HTTP_PORT} (for API access)")
    print(f"ML/Analytics processing enabled")
    print("=" * 60)

    # Start UDP listener in background
    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()

    # Start Flask API
    app.run(host=HOST, port=HTTP_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
