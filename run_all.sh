#!/usr/bin/env bash
# ==============================================================================
# SDN-Assisted Fog Computing for IoT — SIMULATION MODE (No Mininet required)
# ==============================================================================
# This script simulates the SDN behaviour in pure software.
# The sdn_proxy.py acts as the SDN controller:
#   - Receives packets from IoT devices (UDP port 9000)
#   - Performs DPI using the same PolicyEngine and routing_policy.json
#   - Forwards to Fog or Cloud based on policy rules
#
# For REAL SDN with OpenFlow (Ryu + Mininet), run:  ./run_mininet.sh
# That mode uses actual OpenFlow flow rule installation at the switch level.
#
# Usage:  ./run_all.sh        (starts everything)
#         ./run_all.sh stop   (kills all background processes)
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PIDS=()

cleanup() {
    echo ""
    echo "============================================"
    echo "Stopping all services..."
    echo "============================================"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null && echo "  Stopped PID $pid" || true
    done
    echo "All services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

if [[ "$1" == "stop" ]]; then
    echo "Killing any running project processes..."
    pkill -f "fog_server.py"    2>/dev/null || true
    pkill -f "cloud_server.py"  2>/dev/null || true
    pkill -f "sdn_proxy.py"    2>/dev/null || true
    pkill -f "api_gateway.py"  2>/dev/null || true
    pkill -f "temperature_sensor.py" 2>/dev/null || true
    pkill -f "fire_alarm.py"   2>/dev/null || true
    pkill -f "analytics_generator.py" 2>/dev/null || true
    echo "Done."
    exit 0
fi

echo "============================================"
echo " SDN-Assisted Fog Computing for IoT"
echo " Mode: SIMULATION (sdn_proxy.py = SDN brain)"
echo " For real SDN (Ryu+Mininet): ./run_mininet.sh"
echo "============================================"
echo ""

# 1. Fog Server
echo "[1/6] Starting Fog Server (port 5001/5101)..."
python3 servers/fog_server.py &
PIDS+=($!)
sleep 1

# 2. Cloud Server
echo "[2/6] Starting Cloud Server (port 5002/5102)..."
python3 servers/cloud_server.py &
PIDS+=($!)
sleep 1

# 3. SDN Proxy (the policy-driven traffic controller)
echo "[3/6] Starting SDN Proxy (port 9000/9001)..."
python3 controller/sdn_proxy.py &
PIDS+=($!)
sleep 1

# 4. API Gateway
echo "[4/6] Starting API Gateway (port 8000)..."
python3 gateway/api_gateway.py &
PIDS+=($!)
sleep 1

# 5. IoT Devices
echo "[5/6] Starting IoT Devices..."
python3 iot_devices/fire_alarm.py &
PIDS+=($!)

python3 iot_devices/temperature_sensor.py &
PIDS+=($!)

python3 iot_devices/analytics_generator.py &
PIDS+=($!)

sleep 1

echo ""
echo "============================================"
echo " All services running!"
echo "============================================"
echo ""
echo "  Fog Server      : http://localhost:5101"
echo "  Cloud Server    : http://localhost:5102"
echo "  SDN Proxy       : http://localhost:9001"
echo "  API Gateway     : http://localhost:8000"
echo "  API Docs        : http://localhost:8000/docs"
echo "  Dashboard       : Open dashboard/index.html in browser"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "============================================"
echo ""

# Wait for any process to exit
wait
