#!/usr/bin/env python3
"""
SDN Proxy -- Policy-Driven IoT Traffic Controller
==================================================
Industry-standard, ZERO hardcoded routing logic.

All decisions come from: config/routing_policy.json
  - Which fields to inspect    -> policy file
  - What thresholds to apply   -> policy file
  - Where to send the packet   -> policy file

This code is a GENERIC executor. It knows nothing about:
  - Fire alarms
  - Fog or Cloud
  - IP addresses
  - Port numbers
  - Any domain concept

Change the JSON config file -> routing changes.
No code modification ever needed.

How it works:
  1. Listens on the port defined in routing_policy.json
  2. Receives raw UDP packet from any IoT device
  3. Parses JSON payload (DPI)
  4. Passes to PolicyEngine -> evaluates rules top-down by priority
  5. Forwards to the winning node (host:port from policy file)
  6. Logs the decision with which rule triggered
"""

import json
import socket
import threading
import logging
import time
from datetime import datetime
from collections import deque
from flask import Flask, jsonify
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from policy_engine import PolicyEngine

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SDNProxy")

HTTP_MONITORING_PORT = 9001   # Port for the REST monitoring API

# -- Runtime State ------------------------------------------------------------
engine      = PolicyEngine()          # Loads everything from JSON policy
routing_log = deque(maxlen=300)
stats = {
    "total_packets":  0,
    "by_rule":        {},    # rule_id -> count
    "by_node":        {},    # node_name -> count
    "by_class":       {},    # traffic_class -> count
    "start_time":     datetime.now().isoformat()
}
stats_lock = threading.Lock()

# -- Flask Monitoring API -----------------------------------------------------
app = Flask(__name__)
app.logger.setLevel(logging.WARNING)

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "sdn-proxy"})

@app.route("/stats")
def get_stats():
    with stats_lock:
        s = dict(stats)
    uptime = (datetime.now() - datetime.fromisoformat(s["start_time"])).total_seconds()
    return jsonify({"stats": s, "uptime_seconds": round(uptime, 1)})

@app.route("/routing-log")
def get_routing_log():
    return jsonify({"count": len(routing_log), "events": list(routing_log)})

@app.route("/policy")
def get_policy():
    """Expose the loaded policy -- useful for introspection and debugging."""
    return jsonify(engine.policy)

@app.route("/policy/reload", methods=["POST"])
def reload_policy():
    """Hot-reload policy without restarting the proxy."""
    engine.reload_policy()
    return jsonify({"status": "reloaded", "rules": len(engine.rules)})

# -- Core Forwarding ----------------------------------------------------------
def forward_packet(payload: bytes, node: dict):
    """Send packet to the destination node defined in the policy."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(payload, (node["host"], node["port"]))
    sock.close()

def process_packet(payload: bytes, source_addr: tuple):
    """
    Main pipeline:
      RAW BYTES -> PolicyEngine.evaluate() -> Forward -> Log
    """
    # Evaluate against policy rules
    result = engine.evaluate(payload)

    # Update runtime stats
    with stats_lock:
        stats["total_packets"] += 1

        rid = result["rule_id"]
        stats["by_rule"][rid] = stats["by_rule"].get(rid, 0) + 1

        node = result["node_name"]
        stats["by_node"][node] = stats["by_node"].get(node, 0) + 1

        tc = result["traffic_class"]
        stats["by_class"][tc] = stats["by_class"].get(tc, 0) + 1

        pkt_num = stats["total_packets"]

    # Forward to the node the policy chose
    forward_packet(payload, result["node"])

    # Log the decision
    event = {
        "id":            pkt_num,
        "timestamp":     datetime.now().isoformat(),
        "source_ip":     source_addr[0],
        "payload_bytes": len(payload),
        "rule_id":       result["rule_id"],
        "rule_name":     result["rule_name"],
        "traffic_class": result["traffic_class"],
        "destination":   result["node_name"].upper(),
        "node_host":     result["node"]["host"],
        "node_port":     result["node"]["port"],
        "reason":        result["reason"],
        "sensor_id":     result["data"].get("sensor_id", "UNKNOWN"),
        "confidence":    1.0     # Policy rules are deterministic
    }
    routing_log.append(event)

    # Console output
    dest_label = result["node"]["label"]
    print(
        f"[{pkt_num:04d}] [{result['rule_id']}] "
        f"{result['traffic_class']:<10} -> {dest_label} | "
        f"{result['reason']}"
    )

# -- UDP Listener -------------------------------------------------------------
def udp_listener():
    """
    Binds to the collection endpoint defined in routing_policy.json.
    Reads host and port from the policy -- not hardcoded here.
    """
    ep_host, ep_port = engine.get_collection_endpoint()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ep_host, ep_port))
    logger.info(f"Listening on {ep_host}:{ep_port} (from policy file)")

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            threading.Thread(target=process_packet, args=(data, addr), daemon=True).start()
        except Exception as e:
            logger.error(f"Listener error: {e}")

# -- Main ---------------------------------------------------------------------
def main():
    ep_host, ep_port = engine.get_collection_endpoint()

    print("=" * 70)
    print("SDN PROXY -- Policy-Driven IoT Traffic Controller")
    print("=" * 70)
    print(f"Policy file : config/routing_policy.json")
    print(f"Listening   : {ep_host}:{ep_port}  (all IoT devices send here)")
    print(f"Monitor API : http://localhost:{HTTP_MONITORING_PORT}")
    print()
    print(f"Loaded {len(engine.rules)} rules, {len(engine.nodes)} nodes:")
    for rule in engine.rules:
        cond = " AND ".join(
            f"{c['field']} {c['operator']} {c['value']}"
            for c in rule["conditions"]
        ) or "(default)"
        print(f"   [{rule['priority']:3d}] {rule['id']} | {cond} -> {rule['action']['route_to'].upper()}")
    print()
    print("  Destination nodes:")
    for name, node in engine.nodes.items():
        print(f"    {name:<10} -> {node['host']}:{node['port']}  ({node['label']})")
    print("=" * 70)
    print()

    listener_thread = threading.Thread(target=udp_listener, daemon=True)
    listener_thread.start()

    app.run(host="0.0.0.0", port=HTTP_MONITORING_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
