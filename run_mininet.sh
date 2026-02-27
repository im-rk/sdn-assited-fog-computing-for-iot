#!/usr/bin/env bash
# ==============================================================================
# SDN-Assisted Fog Computing for IoT — REAL SDN MODE (Mininet + Ryu)
# ==============================================================================
# This script runs the project using actual SDN:
#   - Ryu OpenFlow controller makes all routing decisions
#   - Mininet creates a virtual network with an OpenFlow switch
#   - IoT devices send to 10.0.0.100:9000 (virtual SDN intercept address)
#   - The switch sends unmatched packets to the Ryu controller
#   - Ryu does DPI, calls PolicyEngine, rewrites dst IP/port/MAC at the switch
#   - Packets are delivered to Fog (10.0.0.4) or Cloud (10.0.0.5)
#
# Requirements:
#   sudo apt-get install mininet
#   pip install ryu
#   pip install -r requirements.txt
#
# Usage:  ./run_mininet.sh
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo " SDN-Assisted Fog Computing for IoT"
echo " Mode: REAL SDN (Ryu OpenFlow Controller + Mininet)"
echo "============================================================"
echo ""
echo "Architecture:"
echo "  IoT Devices (h1/h2/h3)"
echo "      |  send UDP to 10.0.0.100:9000"
echo "      v"
echo "  OpenFlow Switch (s1)"
echo "      |  table-miss -> PacketIn -> Ryu Controller"
echo "      v"
echo "  Ryu SDN Controller  <-- THIS is the SDN brain"
echo "      |  DPI -> PolicyEngine -> routing decision"
echo "      |  rewrites dst IP + port + MAC at switch level"
echo "      v"
echo "  Fog (10.0.0.4:5001)   or   Cloud (10.0.0.5:5002)"
echo ""

# Check dependencies
if ! command -v ryu-manager &>/dev/null; then
    echo "[ERROR] ryu-manager not found. Install with: pip install ryu"
    exit 1
fi

if ! command -v mn &>/dev/null; then
    echo "[ERROR] mininet not found. Install with: sudo apt-get install mininet"
    exit 1
fi

RYU_PID=""
GW_PID=""

cleanup() {
    echo ""
    echo "Stopping Ryu controller and API gateway..."
    [[ -n "$RYU_PID" ]] && kill "$RYU_PID" 2>/dev/null || true
    [[ -n "$GW_PID"  ]] && kill "$GW_PID"  2>/dev/null || true
    # Clean up any leftover Mininet state
    sudo mn --clean 2>/dev/null || true
    echo "Done."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Step 1: Clean any leftover Mininet state from previous runs
echo "[1/4] Cleaning previous Mininet state..."
sudo mn --clean 2>/dev/null || true
sleep 1

# Step 2: Start the Ryu SDN Controller in background
echo "[2/4] Starting Ryu SDN Controller..."
echo "      Loading: controller/sdn_controller.py"
echo "      Policy : config/routing_policy_mininet.json"
ryu-manager controller/sdn_controller.py &
RYU_PID=$!
echo "      Ryu PID: $RYU_PID"
sleep 3   # Give Ryu time to start and listen on port 6633

# Step 3: Start API Gateway (optional — for dashboard)
echo "[3/4] Starting API Gateway (port 8000)..."
python3 gateway/api_gateway.py &
GW_PID=$!
sleep 1

# Step 4: Start Mininet topology (foreground — blocks until you type "exit")
echo "[4/4] Starting Mininet topology (sudo required)..."
echo ""
echo "============================================================"
echo " Once Mininet starts, IoT traffic will flow automatically."
echo " Ryu controller logs above show routing decisions in real time."
echo " Dashboard: open dashboard/index.html in your browser."
echo " Type 'exit' in the Mininet CLI to stop everything."
echo "============================================================"
echo ""

sudo python3 topology/network_topology.py

cleanup
