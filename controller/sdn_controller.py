#!/usr/bin/env python3
"""
Ryu SDN Controller — Policy-Driven DPI (THE SDN BRAIN)
=======================================================
This IS where the SDN intelligence lives.

When a Mininet IoT device sends a packet to the collector (10.0.0.100:9000),
the OpenFlow switch has no flow rule for it → sends it here via PacketIn.

This controller:
  1. Parses the UDP payload (Deep Packet Inspection)
  2. Calls PolicyEngine → evaluates rules from routing_policy_mininet.json
  3. Decides: Fog (10.0.0.4) or Cloud (10.0.0.5) — ZERO hardcoded logic
  4. Rewrites the destination IP + port + MAC at the switch level (OpenFlow)
  5. Installs a short-lived flow rule on the switch (future packets skip controller)
  6. Sends the current packet immediately via PacketOut

The routing_policy_mininet.json file drives ALL decisions.
Change that file → routing changes. No code modification ever needed.

Run with:  ryu-manager controller/sdn_controller.py
"""

import os
import sys
import logging
import threading
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, udp, arp
from ryu.lib.packet import ether_types

sys.path.insert(0, os.path.dirname(__file__))
from policy_engine import PolicyEngine

# Mininet policy file — uses 10.0.0.x IPs (not 127.0.0.1)
_MININET_POLICY = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'routing_policy_mininet.json'
)

# ── Global stats + routing log for HTTP endpoint ───────────────────────────────
import collections
_stats_lock = threading.Lock()
_routing_stats = {
    'total_packets': 0,
    'by_node': {'fog': 0, 'cloud': 0},
    'by_class': {'EMERGENCY': 0, 'CRITICAL': 0, 'ANALYTICS': 0, 'BULK': 0},
}
_routing_log = collections.deque(maxlen=50)  # Last 50 routing decisions

# ── Simple HTTP request handler for stats endpoint ──────────────────────────────
class StatsHTTPHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for /stats and /health endpoints."""
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/stats':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            with _stats_lock:
                response = {
                    'stats': _routing_stats.copy(),
                    'timestamp': datetime.now().isoformat()
                }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == '/routing-log':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            with _stats_lock:
                response = {
                    'events': list(_routing_log),
                    'timestamp': datetime.now().isoformat()
                }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'service': 'ryu-sdn-controller', 'status': 'healthy'}
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass

def _run_http_server():
    """Run the HTTP stats server in a separate thread."""
    server = HTTPServer(('127.0.0.1', 9002), StatsHTTPHandler)
    server.serve_forever()



class PolicySDNController(app_manager.RyuApp):
    """
    OpenFlow 1.3 controller.

    Tables maintained:
      mac_to_port[dpid][mac]  → switch port  (standard L2 learning)
      ip_to_port[dpid][ip]    → switch port  (learned from ARP — used for DPI routing)
      ip_to_mac[dpid][ip]     → MAC address  (needed to rewrite eth_dst)
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PolicySDNController, self).__init__(*args, **kwargs)

        # Forwarding tables
        self.mac_to_port = {}   # dpid → { mac → port }
        self.ip_to_port  = {}   # dpid → { ip  → port }
        self.ip_to_mac   = {}   # dpid → { ip  → mac  }

        # Load policy — reads Mininet IPs, thresholds, rules from JSON
        self.engine = PolicyEngine(policy_path=_MININET_POLICY)
        self.COLLECTOR_IP, self.COLLECTOR_PORT = self.engine.get_collection_endpoint()

        # Start HTTP stats server in daemon thread
        http_thread = threading.Thread(target=_run_http_server, daemon=True)
        http_thread.start()

        self.logger.info("=" * 60)
        self.logger.info("Ryu SDN Controller started (Policy-Driven DPI)")
        self.logger.info(f"Intercept address : {self.COLLECTOR_IP}:{self.COLLECTOR_PORT}")
        self.logger.info(f"Policy rules      : {len(self.engine.rules)}")
        self.logger.info(f"Routing nodes     : {list(self.engine.nodes.keys())}")
        self.logger.info(f"Stats endpoint    : http://127.0.0.1:9002/stats")
        self.logger.info("=" * 60)

    # ── Switch handshake ─────────────────────────────────────────────────────
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Called when a switch connects. Installs the table-miss rule."""
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        # Table-miss: send ALL unmatched packets to this controller
        match   = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

        # HIGH-PRIORITY intercept: UDP dst port 9000 → ALWAYS send to controller
        # This overrides any ARP-learned forwarding rules (those are priority=1)
        # so IoT packets destined to the collector IP always reach Ryu for DPI.
        intercept_match = parser.OFPMatch(
            eth_type=0x0800,        # IPv4
            ip_proto=17,            # UDP
            udp_dst=self.COLLECTOR_PORT  # 9000
        )
        self._add_flow(datapath, priority=100, match=intercept_match, actions=actions)
        self.logger.info(f"Switch {datapath.id:#x} connected — table-miss + UDP:9000 intercept installed")

    # ── PacketIn handler (called for every unmatched packet) ─────────────────
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        in_port  = msg.match['in_port']
        dpid     = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return  # Ignore LLDP

        self.mac_to_port.setdefault(dpid, {})
        self.ip_to_port.setdefault(dpid, {})
        self.ip_to_mac.setdefault(dpid, {})

        # ── Learn MAC → port (standard L2) ───────────────────────────────────
        self.mac_to_port[dpid][eth.src] = in_port

        # ── Learn IP → port and IP → MAC from ARP packets ────────────────────
        # This is how the controller knows which switch port leads to fog/cloud.
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self.ip_to_port[dpid][arp_pkt.src_ip] = in_port
            self.ip_to_mac[dpid][arp_pkt.src_ip]  = arp_pkt.src_mac
            self.logger.debug(
                f"ARP learn: {arp_pkt.src_ip} → MAC {arp_pkt.src_mac} on port {in_port}"
            )

        # ── IoT packet: DPI + SDN routing decision ────────────────────────────
        ip_pkt  = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)

        if (ip_pkt and udp_pkt
                and ip_pkt.dst  == self.COLLECTOR_IP
                and udp_pkt.dst_port == self.COLLECTOR_PORT):
            # This is an IoT data packet — SDN controller decides where it goes
            self._handle_iot_packet(datapath, msg, pkt, ip_pkt, udp_pkt, in_port)
            return

        # ── All other traffic: normal L2 forwarding ───────────────────────────
        dst      = eth.dst
        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=eth.src)
            self._add_flow(datapath, priority=1, match=match, actions=actions)

        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out  = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                   in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    # ── SDN DPI Routing ───────────────────────────────────────────────────────
    def _handle_iot_packet(self, datapath, msg, pkt, ip_pkt, udp_pkt, in_port):
        """
        The core SDN routing logic — called for every IoT packet.

        Steps:
          1. Extract UDP payload (the IoT JSON sensor reading)
          2. Pass to PolicyEngine → it evaluates all rules from the JSON file
          3. Get routing decision: which node (fog/cloud), traffic class, reason
          4. Look up the destination's MAC and switch port (learned via ARP)
          5. Build OpenFlow actions: rewrite eth_dst + ipv4_dst + udp_dst
          6. Install a flow rule on the switch (idle_timeout=5s)
          7. Send this packet now via PacketOut

        ZERO hardcoded logic here. Everything comes from routing_policy_mininet.json.
        """
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        dpid    = datapath.id

        # ── Step 1 & 2: DPI — pass raw bytes to PolicyEngine ─────────────────
        payload = bytes(pkt.protocols[-1])   # UDP payload (the JSON sensor data)
        result  = self.engine.evaluate(payload)

        node     = result["node"]
        dst_ip   = node["host"]    # e.g. 10.0.0.4 (fog) or 10.0.0.5 (cloud)
        dst_port = node["port"]    # e.g. 5001 or 5002
        traffic_class = result["traffic_class"]
        node_name = result["node_name"]

        # ── Update global stats + routing log ────────────────────────────────
        global _routing_stats, _routing_log
        with _stats_lock:
            _routing_stats['total_packets'] += 1
            if node_name in _routing_stats['by_node']:
                _routing_stats['by_node'][node_name] += 1
            if traffic_class in _routing_stats['by_class']:
                _routing_stats['by_class'][traffic_class] += 1
            # Append routing event for the dashboard feed
            _routing_log.append({
                'timestamp':     datetime.now().isoformat(),
                'traffic_class': traffic_class,
                'destination':   node_name.upper(),
                'source_ip':     ip_pkt.src,
                'sensor_id':     node_name,
                'confidence':    1.0,
                'reason':        result.get('reason', ''),
                'rule_id':       result.get('rule_id', ''),
                'dst_ip':        dst_ip,
                'dst_port':      dst_port,
            })

        self.logger.info(
            f"[DPI] Rule={result['rule_id']} | Class={traffic_class} "
            f"| → {node_name.upper()} ({dst_ip}:{dst_port})"
        )
        self.logger.info(f"[DPI] Reason: {result['reason']}")

        # ── Step 3: Look up destination MAC and switch port ───────────────────
        # Populated by the ARP learning above — no hardcoding
        out_port = self.ip_to_port[dpid].get(dst_ip, ofproto.OFPP_FLOOD)
        dst_mac  = self.ip_to_mac[dpid].get(dst_ip)

        if out_port == ofproto.OFPP_FLOOD:
            self.logger.warning(
                f"[DPI] Port for {dst_ip} not yet learned — sending flood. "
                f"Will resolve after first ARP from that host."
            )

        # ── Step 4: Build OpenFlow rewrite actions ────────────────────────────
        # These actions execute AT THE SWITCH HARDWARE LEVEL — pure SDN
        actions = []
        if dst_mac:
            # Rewrite Ethernet destination to the correct host's MAC
            actions.append(parser.OFPActionSetField(eth_dst=dst_mac))
        actions += [
            parser.OFPActionSetField(ipv4_dst=dst_ip),    # Rewrite IP destination
            parser.OFPActionSetField(udp_dst=dst_port),   # Rewrite UDP port
            parser.OFPActionOutput(out_port),             # Forward out the right port
        ]

        # ── Step 5: Install flow rule on the switch ───────────────────────────
        # Match on: source IP + destination IP + destination UDP port.
        # We intentionally do NOT match on udp_src (source port) because IoT
        # devices open a new socket per packet → random ephemeral source port
        # each time → a udp_src match would never fire for the second packet.
        #
        # idle_timeout=5s: rule expires after 5s of inactivity.
        # This is intentionally short — sensor state can change (e.g. temp
        # crosses threshold), so we re-run DPI after 5s, not use a stale rule.
        #
        # How this properly demonstrates SDN:
        #   Packet 1  → switch miss → PacketIn → controller DPI → rule installed
        #   Packets 2-N (within 5s, same src IP) → switch handles autonomously
        #   After 5s idle → rule expires → next packet goes to controller again
        match = parser.OFPMatch(
            in_port=in_port,
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip_pkt.src,
            ipv4_dst=ip_pkt.dst,   # always 10.0.0.100 (collector)
            ip_proto=17,            # UDP
            udp_dst=udp_pkt.dst_port,  # always 9000
        )
        self._add_flow(datapath, priority=10, match=match, actions=actions, idle_timeout=5)

        # ── Step 6: Send THIS packet now ─────────────────────────────────────
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out  = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)
        self.logger.info(
            f"[SDN] PacketOut sent → {dst_ip}:{dst_port} "
            f"via switch port {out_port} | FlowRule installed (TTL=5s)"
        )

    # ── Helper ────────────────────────────────────────────────────────────────
    def _add_flow(self, datapath, priority, match, actions,
                  buffer_id=None, idle_timeout=0):
        """Install a flow entry on the switch."""
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        inst    = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        kwargs = dict(datapath=datapath, priority=priority, match=match,
                      instructions=inst, idle_timeout=idle_timeout)
        if buffer_id and buffer_id != ofproto.OFP_NO_BUFFER:
            kwargs['buffer_id'] = buffer_id

        datapath.send_msg(parser.OFPFlowMod(**kwargs))
