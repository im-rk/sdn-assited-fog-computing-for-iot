# SDN-Assisted Fog Computing for IoT

Intelligent IoT data routing using Software Defined Networking (SDN).
The SDN layer automatically routes data to Fog (edge) or Cloud based on
policy-driven Deep Packet Inspection — with zero hardcoded logic in any server.

## Architecture

```
IoT Devices (h1/h2/h3)
    |  send UDP to 10.0.0.100:9000   <- devices know only this address
    v
OpenFlow Switch (s1)                 <- Mininet virtual switch
    |  no flow rule -> PacketIn
    v
Ryu SDN Controller                   <- THE SDN brain
    |  Deep Packet Inspection
    |  PolicyEngine -> routing_policy_mininet.json
    |  OFPActionSetField: rewrites dst IP + port + MAC at switch
    |  Installs flow rule on switch (idle_timeout=5s)
    v
Fog Server (10.0.0.4:5001)    <- EMERGENCY / CRITICAL traffic
Cloud Server (10.0.0.5:5002)  <- ANALYTICS / BULK traffic
    v
API Gateway (:8000)           <- Aggregates both servers
    v
Dashboard                     <- Live web UI
```

## Project Structure

```
config/
  routing_policy.json          <- Rules for simulation mode (127.0.0.1 IPs)
  routing_policy_mininet.json  <- Rules for real SDN mode (10.0.0.x IPs)

controller/
  policy_engine.py             <- Loads JSON rules, evaluates any payload
  sdn_controller.py            <- Ryu OpenFlow controller (real SDN)
  sdn_proxy.py                 <- Software simulation of SDN (no Mininet needed)

iot_devices/
  fire_alarm.py                <- Smoke/alarm sensor simulator
  temperature_sensor.py        <- Temperature / AQI sensor simulator
  analytics_generator.py       <- Bulk historical data generator

servers/
  fog_server.py                <- Edge server: low-latency critical processing
  cloud_server.py              <- Cloud server: heavy analytics processing

gateway/
  api_gateway.py               <- FastAPI gateway: aggregates all services

dashboard/
  index.html / app.js / style.css  <- Live web dashboard

topology/
  network_topology.py          <- Mininet virtual network topology

run_all.sh       <- Start in simulation mode (no Mininet)
run_mininet.sh   <- Start in real SDN mode (Ryu + Mininet)
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Network Simulation | Mininet |
| SDN Controller | Ryu (OpenFlow 1.3) |
| IoT Transport | UDP (raw socket, no broker) |
| Routing Logic | Policy Engine (JSON-driven, zero hardcoded) |
| Servers | Flask |
| API Gateway | FastAPI |
| Dashboard | HTML / CSS / JavaScript |

## Running the Project

### Prerequisites
```bash
pip install -r requirements.txt

# For real SDN mode only:
sudo apt-get install mininet
pip install ryu
```

### Option A — Real SDN Mode (Ryu + Mininet)
```bash
./run_mininet.sh
```
Starts Ryu controller, Mininet topology, all servers and IoT devices automatically.
Packets traverse a real OpenFlow switch. Ryu does DPI and installs flow rules.

### Option B — Simulation Mode (no Mininet required)
```bash
./run_all.sh
```
The SDN Proxy replaces the Ryu+Mininet layer in pure software.
Same PolicyEngine, same routing decisions — just no virtual network.

### Dashboard
Open `dashboard/index.html` in your browser after starting either mode.

## How Routing Works

All routing logic lives in the JSON policy file — no hardcoded thresholds in any `.py` file.

| Priority | Condition | Routes to |
|---|---|---|
| 100 | smoke_level >= 80 | Fog (EMERGENCY) |
| 90 | smoke_level >= 50 | Fog (CRITICAL) |
| 85 | status in ALARM/EMERGENCY/DANGER | Fog (CRITICAL) |
| 80 | temperature >= 45°C or <= 0°C | Fog (CRITICAL) |
| 75 | air_quality_index >= 150 | Fog (CRITICAL) |
| 50 | num_points >= 20 | Cloud (BULK) |
| 0 | (everything else) | Cloud (ANALYTICS) |

To change routing: edit `config/routing_policy.json` (simulation) or
`config/routing_policy_mininet.json` (Mininet). No code changes needed.


