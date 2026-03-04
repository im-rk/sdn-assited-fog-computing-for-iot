#!/bin/bash

set -e

PROJECT="/home/ramkumar-k-r/Desktop/IOT"
cd "$PROJECT"

echo "[1/5] Cleaning up any previous state..."
pkill -9 -f "ryu-manager" 2>/dev/null || true
pkill -9 -f "api_gateway" 2>/dev/null || true
sudo pkill -9 -f "network_topology" 2>/dev/null || true
sudo mn -c 2>/dev/null || true
sleep 2

echo "[2/5] Starting Ryu controller..."
source venv_ryu/bin/activate
ryu-manager controller/sdn_controller.py > logs/ryu.log 2>&1 &
sleep 5

curl -s http://127.0.0.1:9002/health | grep -q "healthy" && echo "  Ryu is up." || { echo "  Ryu failed to start. Check logs/ryu.log"; exit 1; }

echo "[3/5] Starting Mininet topology..."
sudo python3 topology/network_topology.py --no-cli > logs/mininet.log 2>&1 &
sleep 12

echo "[4/5] Fixing OVS bridge..."
sudo ip link set s1 up
sudo ip addr add 10.0.0.254/24 dev s1 2>/dev/null || true
sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=200,arp,actions=normal"
sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=200,tcp,tp_dst=5101,actions=normal"
sudo ovs-ofctl -O OpenFlow13 add-flow s1 "priority=200,tcp,tp_dst=5102,actions=normal"

echo "[5/5] Starting API Gateway..."
source venv/bin/activate
FOG_URL=http://10.0.0.4:5101 CLOUD_URL=http://10.0.0.5:5102 RYU_STATS_URL=http://127.0.0.1:9002 \
    python3 gateway/api_gateway.py > logs/gateway.log 2>&1 &
sleep 5

curl -s http://localhost:8000/health | grep -q "healthy" && echo "  Gateway is up." || { echo "  Gateway failed. Check logs/gateway.log"; exit 1; }

echo ""
echo "=========================================="
echo "  Mode 2 Real SDN is running!"
echo "  Dashboard: http://localhost:8000/dashboard"
echo "=========================================="
