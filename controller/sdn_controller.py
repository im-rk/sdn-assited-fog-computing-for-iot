#!/usr/bin/env python3
"""
Ryu SDN Controller - Policy-Driven DPI

Receives IoT packets from the OpenFlow switch via PacketIn,
classifies them using the policy engine, and installs flow rules
to route traffic to fog or cloud server.

Run with: ryu-manager controller/sdn_controller.py
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

import collections
_stats_lock = threading.Lock()
_routing_stats = {
    'total_packets': 0,
    'by_node': {'fog': 0, 'cloud': 0},
    'by_class': {'EMERGENCY': 0, 'CRITICAL': 0, 'ANALYTICS': 0, 'BULK': 0},
}
_routing_log = collections.deque(maxlen=50)


class StatsHTTPHandler(BaseHTTPRequestHandler):
    
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
    """OpenFlow 1.3 SDN controller with policy-driven DPI routing."""
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PolicySDNController, self).__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.ip_to_port  = {}
        self.ip_to_mac   = {}

        self.engine = PolicyEngine(policy_path=_MININET_POLICY)
        self.COLLECTOR_IP, self.COLLECTOR_PORT = self.engine.get_collection_endpoint()

        http_thread = threading.Thread(target=_run_http_server, daemon=True)
        http_thread.start()

        self.logger.info("=" * 60)
        self.logger.info("Ryu SDN Controller started (Policy-Driven DPI)")
        self.logger.info(f"Intercept address : {self.COLLECTOR_IP}:{self.COLLECTOR_PORT}")
        self.logger.info(f"Policy rules      : {len(self.engine.rules)}")
        self.logger.info(f"Routing nodes     : {list(self.engine.nodes.keys())}")
        self.logger.info(f"Stats endpoint    : http://127.0.0.1:9002/stats")
        self.logger.info("=" * 60)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Called when a switch connects. Installs the table-miss rule."""
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        # Table-miss: send unmatched packets to controller
        match   = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

        # High-priority rule: always send UDP:9000 traffic to controller for DPI
        intercept_match = parser.OFPMatch(
            eth_type=0x0800,        # IPv4
            ip_proto=17,            # UDP
            udp_dst=self.COLLECTOR_PORT  # 9000
        )
        self._add_flow(datapath, priority=100, match=intercept_match, actions=actions)
        self.logger.info(f"Switch {datapath.id:#x} connected — table-miss + UDP:9000 intercept installed")

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

        self.mac_to_port[dpid][eth.src] = in_port

        # Learn IP/MAC from ARP so we know which port leads to fog/cloud
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self.ip_to_port[dpid][arp_pkt.src_ip] = in_port
            self.ip_to_mac[dpid][arp_pkt.src_ip]  = arp_pkt.src_mac

        ip_pkt  = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)

        if (ip_pkt and udp_pkt
                and ip_pkt.dst  == self.COLLECTOR_IP
                and udp_pkt.dst_port == self.COLLECTOR_PORT):
            self._handle_iot_packet(datapath, msg, pkt, ip_pkt, udp_pkt, in_port)
            return

        # Normal L2 forwarding for all other traffic
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

    def _handle_iot_packet(self, datapath, msg, pkt, ip_pkt, udp_pkt, in_port):
        """DPI + routing for IoT packets. Classifies payload, installs flow rule, forwards packet."""
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        dpid    = datapath.id

        payload = bytes(pkt.protocols[-1])
        result  = self.engine.evaluate(payload)

        node     = result["node"]
        dst_ip   = node["host"]
        dst_port = node["port"]
        traffic_class = result["traffic_class"]
        node_name = result["node_name"]

        global _routing_stats, _routing_log
        with _stats_lock:
            _routing_stats['total_packets'] += 1
            if node_name in _routing_stats['by_node']:
                _routing_stats['by_node'][node_name] += 1
            if traffic_class in _routing_stats['by_class']:
                _routing_stats['by_class'][traffic_class] += 1
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

        out_port = self.ip_to_port[dpid].get(dst_ip, ofproto.OFPP_FLOOD)
        dst_mac  = self.ip_to_mac[dpid].get(dst_ip)

        if out_port == ofproto.OFPP_FLOOD:
            self.logger.warning(f"[DPI] Port for {dst_ip} not yet learned — flooding.")

        actions = []
        if dst_mac:
            actions.append(parser.OFPActionSetField(eth_dst=dst_mac))
        actions += [
            parser.OFPActionSetField(ipv4_dst=dst_ip),
            parser.OFPActionSetField(udp_dst=dst_port),
            parser.OFPActionOutput(out_port),
        ]

        # idle_timeout=5s so DPI re-runs after a period of inactivity
        # (sensor readings can change class over time)
        match = parser.OFPMatch(
            in_port=in_port,
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip_pkt.src,
            ipv4_dst=ip_pkt.dst,   # always 10.0.0.100 (collector)
            ip_proto=17,            # UDP
            udp_dst=udp_pkt.dst_port,  # always 9000
        )
        self._add_flow(datapath, priority=10, match=match, actions=actions, idle_timeout=5)

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
