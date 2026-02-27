# SDN-Assisted Fog Computing for IoT — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SYSTEM ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                                  │
│  │   Temp   │  │   Fire   │  │Analytics │    IoT Layer                     │
│  │  Sensor  │  │  Alarm   │  │Generator │                                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                                  │
│       │             │             │                                         │
│       └─────────────┼─────────────┘                                         │
│                     │ UDP                                                   │
│                     ▼                                                       │
│            ┌────────────────┐         ┌─────────────────┐                  │
│            │   SDN Switch   │◄───────►│  SDN Controller │  Network Layer   │
│            │   (Mininet)    │         │     (Ryu)       │                  │
│            └───────┬────────┘         └─────────────────┘                  │
│                    │                                                        │
│       ┌────────────┼────────────┐                                          │
│       │ CRITICAL   │   ANALYTICS│                                          │
│       ▼            │            ▼                                          │
│  ┌─────────┐       │       ┌─────────┐                                     │
│  │   Fog   │       │       │  Cloud  │   Processing Layer                  │
│  │ :5001   │       │       │  :5002  │                                     │
│  └────┬────┘       │       └────┬────┘                                     │
│       │            │            │                                          │
│       └────────────┼────────────┘                                          │
│                    ▼                                                        │
│            ┌───────────────┐                                               │
│            │  API Gateway  │   Gateway Layer                               │
│            │    :8000      │                                               │
│            └───────┬───────┘                                               │
│                    ▼                                                        │
│            ┌───────────────┐                                               │
│            │   Dashboard   │   Presentation Layer                          │
│            └───────────────┘                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Port | Purpose |
|-----------|------|---------|
| Temperature Sensor | - | Sends analytics data (ANALYTICS type) |
| Fire Alarm | - | Sends critical alerts (CRITICAL type) |
| Analytics Generator | - | Sends bulk historical data |
| SDN Switch | - | OpenFlow switch routing packets |
| SDN Controller | 6633 | Ryu controller with routing rules |
| Fog Server | 5001 (UDP), 5101 (HTTP) | Low-latency edge processing |
| Cloud Server | 5002 (UDP), 5102 (HTTP) | Heavy analytics processing |
| API Gateway | 8000 | Aggregates data for dashboard |

## Data Flow

1. **IoT sensors** generate data with type identifier (CRITICAL/ANALYTICS)
2. **SDN Switch** receives packets
3. **SDN Controller** inspects packets and determines route:
   - Port 5001 → Fog Node
   - Port 5002 → Cloud Node
4. **Fog/Cloud servers** process data and expose REST APIs
5. **API Gateway** aggregates data from both servers
6. **Dashboard** polls gateway and displays real-time metrics

## Running the Project

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
sudo apt-get install mininet
```

### Step 2: Start Servers (in separate terminals)
```bash
# Terminal 1: Fog Server
python servers/fog_server.py

# Terminal 2: Cloud Server
python servers/cloud_server.py

# Terminal 3: API Gateway
python gateway/api_gateway.py
```

### Step 3: Start IoT Simulators
```bash
# Terminal 4: Fire Alarm
python iot_devices/fire_alarm.py

# Terminal 5: Temperature Sensor
python iot_devices/temperature_sensor.py

# Terminal 6: Analytics Generator
python iot_devices/analytics_generator.py
```

### Step 4: Open Dashboard
Open `dashboard/index.html` in a browser or serve with:
```bash
cd dashboard && python -m http.server 8080
```

### (Optional) Run with Mininet
```bash
# Terminal: Start Ryu Controller
ryu-manager controller/sdn_controller.py

# Terminal: Start Mininet Topology
sudo python topology/network_topology.py
```
