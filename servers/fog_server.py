#!/usr/bin/env python3
"""
Fog Server - Edge Computing Node
Handles CRITICAL data with low-latency processing

Runs on: 10.0.0.4:5001
"""

import json
import logging
import socket
import threading
import time
from datetime import datetime
from collections import deque
from flask import Flask, jsonify

# Configuration
HOST = '0.0.0.0'
UDP_PORT = 5001  # Critical data port
HTTP_PORT = 5101  # API endpoint
MAX_ALERTS = 100  # Keep last 100 alerts

# Shared data store — guarded by a lock (UDP thread + Flask thread both write)
_lock = threading.Lock()
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
logger = logging.getLogger('FogServer')


def _infer_class_from_data(data: dict, server_role: str) -> str:
    """
    Fallback traffic class inference used in Mininet/Ryu mode.

    In Mininet mode, the Ryu SDN controller rewrites packet headers via
    OpenFlow (L2/L3/L4) but cannot inject a JSON field into the UDP payload.
    So '_sdn_routing' metadata won't be present.  We infer the class from
    context: if a packet reached this server, the SDN controller already
    decided it belongs here — so we just mark it by server role.
    """
    if server_role == 'fog':
        # Everything that arrives at fog was routed here as CRITICAL or EMERGENCY
        # by the Ryu controller — so mark it accordingly.
        return 'CRITICAL'
    return 'ANALYTICS'


def process_critical_alert(data):
    """
    Process an alert routed here by the SDN Proxy.

    ZERO hardcoded severity logic — the traffic classification is read
    from the '_sdn_routing' metadata injected by the SDN Proxy.
    The Fog server simply acts on whatever the SDN layer decided.
    """
    receive_time = datetime.now()
    processing_start = time.time()

    # Read SDN routing metadata (injected by the proxy — no hardcoding)
    # In Mininet/Ryu mode, OpenFlow only rewrites headers (no payload injection),
    # so we fall back to inferring from the fact that we ARE the fog server.
    sdn_meta = data.get('_sdn_routing', {})
    traffic_class = sdn_meta.get('traffic_class') or _infer_class_from_data(data, 'fog')
    rule_id       = sdn_meta.get('rule_id', 'OpenFlow-routed')
    rule_name     = sdn_meta.get('rule_name', 'Routed by Ryu SDN controller')
    reason        = sdn_meta.get('reason', 'Packet rewritten at switch by Ryu')

    # Build alert record from whatever fields the sensor sent
    alert = {
        'id':            stats['total_alerts'] + 1,
        'received_at':   receive_time.isoformat(),
        'sensor_id':     data.get('sensor_id', 'UNKNOWN'),
        'sensor_type':   data.get('sensor_type', 'unknown'),
        'data_type':     data.get('data_type', 'unknown'),
        'status':        data.get('status', 'UNKNOWN'),
        'traffic_class': traffic_class,
        'rule_id':       rule_id,
        'rule_name':     rule_name,
        'smoke_level':   data.get('smoke_level'),
        'value':         data.get('value'),
        'location':      data.get('location', 'Unknown'),
        'reason':        reason,
        'action_taken':  'ALERT_DISPATCHED',
    }

    # Determine response action based on SDN traffic class (not hardcoded fields)
    if traffic_class == 'EMERGENCY':
        alert['action_taken'] = 'EMERGENCY_SERVICES_NOTIFIED'
        alert['severity'] = 'EMERGENCY'
        with _lock:
            stats['critical_count'] += 1
    elif traffic_class == 'CRITICAL':
        alert['action_taken'] = 'SECURITY_NOTIFIED'
        alert['severity'] = 'HIGH'
        with _lock:
            stats['critical_count'] += 1
    else:
        alert['action_taken'] = 'LOGGED'
        alert['severity'] = 'NORMAL'
        with _lock:
            stats['warning_count'] += 1

    processing_time = (time.time() - processing_start) * 1000  # ms
    alert['processing_time_ms'] = round(processing_time, 2)

    # Update stats — protected by lock
    with _lock:
        stats['total_alerts'] += 1
        stats['avg_response_time_ms'] = round(
            (stats['avg_response_time_ms'] * (stats['total_alerts'] - 1) + processing_time) / stats['total_alerts'],
            2
        )
        alerts_queue.append(alert)

    return alert


def _handle_packet(data: bytes, addr: tuple):
    """Process a single packet in its own thread — non-blocking listener."""
    try:
        message = json.loads(data.decode('utf-8'))
        alert = process_critical_alert(message)
        logger.info(
            '[%04d] Class=%-10s Severity=%-9s Action=%s Rule=%s Time=%.2fms',
            alert['id'], alert['traffic_class'], alert['severity'],
            alert['action_taken'], alert['rule_id'], alert['processing_time_ms']
        )
    except json.JSONDecodeError as e:
        logger.error('Invalid JSON from %s: %s', addr, e)
    except Exception as e:
        logger.exception('Packet handling error from %s: %s', addr, e)


def udp_listener():
    """Listen for incoming UDP packets. Dispatches each packet to its own thread
    so processing time never blocks the receive loop."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, UDP_PORT))
    logger.info('Fog Server UDP listening on %s:%d', HOST, UDP_PORT)

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            threading.Thread(target=_handle_packet, args=(data, addr), daemon=True).start()
        except Exception as e:
            logger.error('Listener error: %s', e)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'fog-server'})


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get server statistics."""
    with _lock:
        snapshot = dict(stats)
    return jsonify({
        'stats': snapshot,
        'uptime_seconds': (datetime.now() - datetime.fromisoformat(snapshot['start_time'])).total_seconds()
    })


@app.route('/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts."""
    with _lock:
        data = list(alerts_queue)
    return jsonify({
        'count': len(data),
        'alerts': data
    })


@app.route('/alerts/latest', methods=['GET'])
def get_latest_alert():
    """Get the most recent alert."""
    if alerts_queue:
        return jsonify(alerts_queue[-1])
    return jsonify({'message': 'No alerts yet'}), 404


def main():
    logging.basicConfig(
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        level=logging.INFO,
        datefmt='%H:%M:%S'
    )
    logger.info('=' * 60)
    logger.info('FOG SERVER - Edge Computing Node')
    logger.info('UDP Port : %d (CRITICAL / EMERGENCY traffic)', UDP_PORT)
    logger.info('HTTP Port: %d (REST API)', HTTP_PORT)
    logger.info('=' * 60)

    # Start UDP listener in background
    udp_thread = threading.Thread(target=udp_listener, daemon=True)
    udp_thread.start()

    # Start Flask API
    app.run(host=HOST, port=HTTP_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
