#!/usr/bin/env python3
"""
Ryu SDN Controller - Policy-Driven DPI
========================================
Performs Deep Packet Inspection (DPI) on packets destined for the collector.
Rewrites destination IP and port based on policy rules.
"""

import json
import logging
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, udp
from ryu.lib.packet import ether_types

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from policy_engine import PolicyEngine

class PolicySDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(PolicySDNController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.engine = PolicyEngine()
        
        # Get collection endpoint from policy
        self.COLLECTOR_IP, self.COLLECTOR_PORT = self.engine.get_collection_endpoint()
        self.logger.info(f"SDN Controller initialized. Collector: {self.COLLECTOR_IP}:{self.COLLECTOR_PORT}")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst, idle_timeout=idle_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    idle_timeout=idle_timeout)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        
        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        # Learn MAC address
        self.mac_to_port[dpid][src] = in_port

        # Check if it's an IP packet
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)

        if ip_pkt and udp_pkt and ip_pkt.dst == self.COLLECTOR_IP and udp_pkt.dst_port == self.COLLECTOR_PORT:
            # DPI - Handle IoT Packet
            self._handle_iot_packet(datapath, msg, pkt, ip_pkt, udp_pkt, in_port)
            return

        # Standard L2 forwarding
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]
        
        # Install flow if not flooding
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def _handle_iot_packet(self, datapath, msg, pkt, ip_pkt, udp_pkt, in_port):
        """Perform DPI and rewrite packet destination based on policy."""
        parser = datapath.ofproto_parser
        
        # Get actual application payload (skip Ethernet, IP, UDP headers)
        payload = bytes(pkt.protocols[-1])
        
        # Use Policy Engine to decide destination
        result = self.engine.evaluate(payload)
        
        node = result["node"]
        dst_ip = node["host"]
        dst_port = node["port"]
        
        self.logger.info(f"DPI MATCH: {result['rule_id']} [{result['traffic_class']}] -> {result['node_name'].upper()}")
        self.logger.info(f"REWRITING: {dst_ip}:{dst_port} | Reason: {result['reason']}")

        # Hardcode out_port for simulation purposes if not found in mac table
        # In a real environment, we'd look up the MAC of the Fog/Cloud node
        out_port = datapath.ofproto.OFPP_FLOOD 

        actions = [
            parser.OFPActionSetField(ipv4_dst=dst_ip),
            parser.OFPActionSetField(udp_dst=dst_port),
            parser.OFPActionOutput(out_port)
        ]

        # Install temporary flow rule for this specific flow to reduce controller load
        match = parser.OFPMatch(in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
                                ipv4_src=ip_pkt.src, ipv4_dst=ip_pkt.dst,
                                ip_proto=17, udp_src=udp_pkt.src_port, udp_dst=udp_pkt.dst_port)
        
        # Short idle_timeout because content might change (e.g. fire starts)
        self.add_flow(datapath, 10, match, actions, idle_timeout=5)

        data = None
        if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
