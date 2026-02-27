#!/usr/bin/env python3
"""
Cloud Server - Heavy Analytics Processing
Handles ANALYTICS data for storage and ML processing

Runs on: 10.0.0.5:5002
"""

import json
import logging
import socket
import threading
import time
import random
from datetime import datetime
from collections import deque
from flask import Flask, jsonify

# Configuration
HOST = '0.0.0.0'
UDP_PORT = 5002  # Analytics data port
HTTP_PORT = 5102  # API endpoint
MAX_RECORDS = 1000  # Keep last 1000 data points

# Shared data store — guarded by a lock (UDP thread + Flask thread both write)
_lock = threading.Lock()
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
logger = logging.getLogger('CloudServer')


def _infer_class_from_data(data: dict, server_role: str) -> str:
    """
    Fallback traffic class inference used in Mininet/Ryu mode.

    In Mininet mode, the Ryu SDN controller rewrites packet headers via
    OpenFlow (L2/L3/L4) but cannot inject a JSON field into the UDP payload.
    So '_sdn_routing' metadata won't be present.  We infer from the server role.
    """
    if server_role == 'cloud':
        # Everything that arrives at cloud was routed here as ANALYTICS or BULK
        # by the Ryu controller.
        return 'ANALYTICS'
    return 'CRITICAL'


def process_analytics_data(data):
    """
    Process analytics data with heavy computation simulation.

    Reads SDN routing metadata from '_sdn_routing' — no hardcoded logic.
    Simulates realistic cloud latency (network hop + processing).
    """
    receive_time = datetime.now()
    processing_start = time.time()

    # Read SDN routing metadata (injected by sdn_proxy in simulation mode).
    # In Mininet/Ryu mode, OpenFlow only rewrites headers — no payload injection.
    # Fall back to inferring from the fact that we ARE the cloud server.
    sdn_meta = data.get('_sdn_routing', {})
    traffic_class = sdn_meta.get('traffic_class') or _infer_class_from_data(data, 'cloud')
    rule_id       = sdn_meta.get('rule_id', 'OpenFlow-routed')

    # Simulate realistic cloud processing delay in a non-blocking way:
    # The sleep is inside process_analytics_data() which runs per-thread,
    # so it never holds up the UDP receive loop.
    time.sleep(random.uniform(0.05, 0.15))  # 50-150ms realistic cloud delay

    batch_size = len(data.get('data_points', []))
    data_size = len(json.dumps(data))

    # Create record
    record = {
        'id':                  stats['total_batches'] + 1,
        'received_at':         receive_time.isoformat(),
        'sensor_id':           data.get('sensor_id', 'UNKNOWN'),
        'data_type':           data.get('data_type', 'unknown'),
        'batch_size':          batch_size,
        'payload_size_bytes':  data_size,
        'traffic_class':       traffic_class,
        'rule_id':             rule_id,
        'status':              'PROCESSED'
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

    # Update stats — protected by lock
    with _lock:
        stats['total_batches'] += 1
        stats['total_data_points'] += batch_size
        stats['total_bytes_received'] += data_size
        stats['avg_processing_time_ms'] = round(
            (stats['avg_processing_time_ms'] * (stats['total_batches'] - 1) + processing_time) / stats['total_batches'],
            2
        )
        analytics_data.append(record)
    
    return record


def _handle_packet(data: bytes, addr: tuple):
    """Process a single packet in its own thread — non-blocking listener."""
    try:
        message = json.loads(data.decode('utf-8'))
        record = process_analytics_data(message)
        logger.info(
            '[%04d] Class=%-10s Points=%3d  Size=%.2fKB  Rule=%s  Time=%.2fms',
            record['id'], record['traffic_class'], record['batch_size'],
            record['payload_size_bytes'] / 1024, record['rule_id'],
            record['processing_time_ms']
        )
    except json.JSONDecodeError as e:
        logger.error('Invalid JSON from %s: %s', addr, e)
    except Exception as e:
        logger.exception('Packet handling error from %s: %s', addr, e)


def udp_listener():
    """Listen for incoming UDP packets. Each packet is dispatched to its own
    thread so the 50-150ms cloud delay never blocks the receive loop."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, UDP_PORT))
    logger.info('Cloud Server UDP listening on %s:%d', HOST, UDP_PORT)

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            threading.Thread(target=_handle_packet, args=(data, addr), daemon=True).start()
        except Exception as e:
            logger.error('Listener error: %s', e)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'cloud-server'})


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get server statistics."""
    with _lock:
        snapshot = dict(stats)
    uptime = (datetime.now() - datetime.fromisoformat(snapshot['start_time'])).total_seconds()
    return jsonify({
        'stats': snapshot,
        'uptime_seconds': uptime,
        'throughput_kbps': round(snapshot['total_bytes_received'] / 1024 / max(1, uptime), 2)
    })


@app.route('/data', methods=['GET'])
def get_data():
    """Get processed analytics data."""
    with _lock:
        data = list(analytics_data)[-50:]
    return jsonify({'count': len(data), 'records': data})


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
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        level=logging.INFO,
        datefmt='%H:%M:%S'
    )
    logger.info('=' * 60)
    logger.info('CLOUD SERVER - Heavy Analytics Processing')
    logger.info('UDP Port : %d (ANALYTICS / BULK traffic)', UDP_PORT)
    logger.info('HTTP Port: %d (REST API)', HTTP_PORT)
    logger.info('=' * 60)

    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()

    app.run(host=HOST, port=HTTP_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
