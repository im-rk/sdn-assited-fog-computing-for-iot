# SDN-Assisted Fog Computing for IoT — Architecture

## System Overview

```
+-----------------------------------------------------------------------------+
|                           SYSTEM ARCHITECTURE                               |
+-----------------------------------------------------------------------------+
|                                                                             |
|  +----------+  +----------+  +----------+                                  |
|  |   Temp   |  |   Fire   |  |Analytics |    IoT Layer                     |
|  |  Sensor  |  |  Alarm   |  |Generator |    (h1/h2/h3 in Mininet)         |
|  +-----+----+  +-----+----+  +-----+----+                                  |
|        |             |             |                                        |
|        +-------------+-------------+                                        |
|                UDP to 10.0.0.100:9000 (devices know ONLY this)             |
|                      |                                                      |
|                      v                                                      |
|         +-----------------+   table-miss   +-----------------+             |
|         |  OpenFlow        +--------------->  Ryu SDN         |             |
|         |  Switch (s1)     <---------------+  Controller      |             |
|         |  (Mininet OVS)  |  PacketOut +   |  sdn_controller  |             |
|         +--------+--------+  FlowRule     |  .py             |             |
|      rewritten   |                        |                  |             |
|      dst IP+port |          PolicyEngine <--  routing_policy  |             |
|                  |          (JSON rules)      _mininet.json  |             |
|        +---------+-----------+            +-----------------+             |
|        v                     v                                             |
|  +-----------+         +-----------+                                       |
|  |  Fog      |         |  Cloud    |   Processing Layer                    |
|  |  10.0.0.4 |         |  10.0.0.5 |                                       |
|  |  UDP:5001 |         |  UDP:5002 |                                       |
|  |  HTTP:5101|         |  HTTP:5102|                                       |
|  +-----+-----+         +-----+-----+                                       |
|        |                     |                                             |
|        +----------+----------+                                             |
|                   v                                                        |
|          +---------------+                                                 |
|          |  API Gateway  |   Gateway Layer                                 |
|          |    :8000      |                                                 |
|          +-------+-------+                                                 |
|                  v                                                         |
|          +---------------+                                                 |
|          |   Dashboard   |   Presentation Layer                            |
|          +---------------+                                                 |
+-----------------------------------------------------------------------------+
```

## Components

| Component | Port | Purpose |
|-----------|------|---------|
| Temperature Sensor (h2) | - | Sends periodic sensor readings → SDN decides destination |
| Fire Alarm Sensor (h1) | - | Sends smoke/alarm readings → SDN decides destination |
| Analytics Generator (h3) | - | Sends bulk historical batches → SDN decides destination |
| OpenFlow Switch (s1) | - | Hardware-level packet switching, executes installed flow rules |
| Ryu SDN Controller | 6633 | DPI + PolicyEngine + OpenFlow flow rule installation at switch |
| Fog Server | UDP:5001 / HTTP:5101 | Low-latency edge processing (sub-ms) |
| Cloud Server | UDP:5002 / HTTP:5102 | Heavy analytics processing (50–150ms) |
| API Gateway | 8000 | Aggregates Fog + Cloud + SDN Proxy into one REST API |

## Data Flow (Real SDN Mode — Ryu + Mininet)

1. **IoT sensors** send raw UDP JSON payloads to `10.0.0.100:9000`
   — they know nothing about Fog or Cloud
2. **OpenFlow Switch (s1)** receives the packet — no matching flow rule
   → sends **PacketIn** event to the Ryu controller
3. **Ryu SDN Controller** performs Deep Packet Inspection:
   - Parses the UDP payload (JSON sensor data)
   - Passes to **PolicyEngine** which evaluates rules from `routing_policy_mininet.json`
   - Gets routing decision: node (fog/cloud), traffic_class, reason
   - Uses `OFPActionSetField` to rewrite `eth_dst` + `ipv4_dst` + `udp_dst` at the switch
   - Installs a short-lived flow rule (idle_timeout=5s) on the switch
   - Sends the packet immediately via PacketOut
4. **Fog / Cloud server** receives the packet, reads SDN routing metadata
   — zero hardcoded logic, acts on what the SDN layer decided
5. **API Gateway** aggregates data from Fog + Cloud + SDN Proxy REST APIs
6. **Dashboard** polls `/dashboard` every 3 seconds and displays live metrics

## Data Flow (Simulation Mode — sdn_proxy.py)

Same routing logic, no virtual network:
1. IoT devices send UDP to `127.0.0.1:9000`
2. `sdn_proxy.py` receives, calls PolicyEngine, enriches payload with `_sdn_routing`
   metadata, and forwards to Fog (`:5001`) or Cloud (`:5002`) directly

## Running the Project

### Option A — Real SDN Mode (Ryu + Mininet)
```bash
# One command starts everything:
./run_mininet.sh
```

### Option B — Simulation Mode (no Mininet needed)
```bash
./run_all.sh
```

### Dashboard
Open `dashboard/index.html` in your browser after starting either mode.
