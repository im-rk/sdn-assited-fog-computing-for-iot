# SDN-Assisted Fog Computing for IoT

A software simulation demonstrating intelligent SDN-based routing of IoT data between Fog (edge) and Cloud nodes.

## 🎯 Overview

This project simulates an intelligent IoT data routing system where:
- **Critical data** (fire alarms, emergencies) → Routes to **Fog Node** (fast, local processing)
- **Analytics data** (logs, historical) → Routes to **Cloud Node** (remote, heavy processing)
- **SDN Controller** makes real-time routing decisions based on packet inspection

## 🏗️ Architecture

```
IoT Sensors → MQTT Broker → SDN Switch → Fog/Cloud Servers → API Gateway → Dashboard
                               ↑
                        SDN Controller (Ryu)
```

## 📁 Project Structure

```
├── topology/           # Mininet network topology
├── controller/         # Ryu SDN controller
├── iot_devices/        # IoT sensor simulators
├── servers/            # Fog and Cloud servers
├── gateway/            # API Gateway
├── dashboard/          # Web visualization
└── docs/               # Documentation
```

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Network Simulation | Mininet |
| SDN Controller | Ryu (Python) |
| IoT Protocol | MQTT (Mosquitto) |
| Servers | Flask |
| API Gateway | FastAPI |
| Dashboard | HTML/CSS/JavaScript |

## 🚀 Quick Start

### Prerequisites
```bash
# Install Mininet
sudo apt-get install mininet

# Install Mosquitto MQTT Broker
sudo apt-get install mosquitto mosquitto-clients

# Install Python dependencies
pip install -r requirements.txt
```

### Run the Project
```bash
# Terminal 1: Start MQTT Broker
mosquitto

# Terminal 2: Start Ryu Controller
ryu-manager controller/sdn_controller.py

# Terminal 3: Start Fog Server
python servers/fog_server.py

# Terminal 4: Start Cloud Server
python servers/cloud_server.py

# Terminal 5: Start API Gateway
python gateway/api_gateway.py

# Terminal 6: Run Mininet Topology
sudo python topology/network_topology.py

# Terminal 7: Run IoT Simulators
python iot_devices/temperature_sensor.py
python iot_devices/fire_alarm.py
```

### Access Dashboard
Open `http://localhost:8080` in your browser.

## 📊 Features

- ✅ SDN-based intelligent packet routing
- ✅ Real-time IoT data simulation
- ✅ MQTT publish/subscribe communication
- ✅ Fog computing for low-latency processing
- ✅ Cloud computing for heavy analytics
- ✅ Live web dashboard with metrics

## 📝 License

MIT License
