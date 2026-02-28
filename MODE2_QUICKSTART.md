# MODE 2: REAL SDN WITH MININET - QUICK START GUIDE

## 🎯 What is Mode 2?

Real Software-Defined Network using:
- **Mininet**: Virtual network with 6 hosts
- **OVS (Open vSwitch)**: Switch that forwards packets
- **Ryu**: OpenFlow controller that classifies and routes traffic
- **Fog/Cloud Servers**: Running inside Mininet virtual hosts

---

## 🚀 STEP 1: Kill Everything

```bash
pkill -9 -f "gateway" 2>/dev/null
pkill -9 -f "ryu-manager" 2>/dev/null
sudo pkill -9 -f "python3 topology" 2>/dev/null
sudo killall -9 ovs-vswitchd ovsdb-server 2>/dev/null
sleep 1
echo "✓ All cleaned"
```

---

## 🖥️ STEP 2: Start 3 Services (in 3 different terminals)

### TERMINAL A: Mininet Topology (REQUIRES SUDO)

```bash
cd /home/ramkumar-k-r/Desktop/IOT
sudo python3 topology/network_topology.py --no-cli
```

✅ Wait 10 seconds. You should see:
```
*** Adding controller
*** Starting 1 switches
*** Starting 6 hosts
*** Configuring hosts...
*** Starting network...
```

---

### TERMINAL B: Ryu SDN Controller

```bash
cd /home/ramkumar-k-r/Desktop/IOT
source venv_ryu/bin/activate
ryu-manager controller/sdn_controller.py
```

✅ Wait 3 seconds. You should see:
```
Ryu SDN Controller started (Policy-Driven DPI)
Intercept address : 10.0.0.100:9000
Policy rules      : 8
Routing nodes     : ['fog', 'cloud']
```

---

### TERMINAL C: API Gateway

```bash
cd /home/ramkumar-k-r/Desktop/IOT
source venv/bin/activate
FOG_URL=http://10.0.0.4:5101 CLOUD_URL=http://10.0.0.5:5102 python3 gateway/api_gateway.py
```

✅ Wait 3 seconds. You should see:
```
API GATEWAY v2 - SDN-IoT Unified Access Point
Fog Server  : http://10.0.0.4:5101
Cloud Server : http://10.0.0.5:5102
Gateway     : http://localhost:8000
```

---

## 🌐 STEP 3: Open Dashboard

Once all 3 services are running, open in browser:

```
http://localhost:8000/dashboard
```

Or use command line:
```bash
firefox http://localhost:8000/dashboard &
```

✅ **WAIT 20-30 SECONDS** for data to populate!

The dashboard should show:
- ✓ Green "Connected" indicator
- ✓ Non-zero packet counts at top
- ✓ Fog and Cloud latency metrics
- ✓ Yellow verdict banner (Fog is XX× faster)

---

## 📸 SCREENSHOTS FOR PPT

Once dashboard is populated, take these 5 screenshots:

### 1. **Full Dashboard Overview**
- Entire page with all metrics visible
- Shows complete system state
- **Caption**: "Mode 2 Real SDN Architecture"

### 2. **System Health Panel** (Top section)
- Fog Server card: Alerts, Critical, Latency
- Cloud Server card: Batches, Data Points, Latency
- **Caption**: "All Services Live and Responding"

### 3. **Latency Comparison**
- Latency bars (Fog vs Cloud)
- Pie chart showing traffic split
- **Caption**: "Fog processes high-priority traffic faster"

### 4. **Latency Evaluation Verdict** ⭐ MOST IMPORTANT
- Yellow banner with verdict
- Comparison table (Avg, P95, P99, Samples)
- **Caption**: "Real OpenFlow Routing: [X]ms delay saved per packet"

### 5. **Ryu Terminal Output**
- Screenshot of Terminal B showing routing decisions
- Examples:
  ```
  [DPI] Rule=R001 | Class=EMERGENCY → FOG
  [DPI] Rule=R008 | Class=ANALYTICS → CLOUD
  [SDN] PacketOut sent → 10.0.0.4:5001
  ```
- **Caption**: "Policy-Driven DPI Routing in Action"

---

## 📊 What You Should See

| Metric | Expected Value |
|--------|----------------|
| Total Packets | 150-300+ |
| Fog Routed | 100-200+ |
| Cloud Routed | 50-150+ |
| Fog Latency | **2-5ms** ✅ FAST |
| Cloud Latency | **80-150ms** 🐢 SLOW |
| Speedup Factor | **20-30×** |
| Verdict | "Fog is 20-30× faster than Cloud" |

---

## 🔧 TROUBLESHOOTING

### All stats showing ZERO?
- ✓ Wait longer (stats take 20-30 seconds to accumulate)
- ✓ Check if all 3 services are running
- ✓ Look at Ryu terminal for routing logs

### "Mininet must run as root"
- ✓ Use `sudo python3` (not just `python3`)

### Fog/Cloud showing "unhealthy"
- ✓ Verify Mininet is running and all 6 hosts started
- ✓ Check Terminal A output for errors

### Dashboard blank/showing "Waiting for traffic"
- ✓ IoT devices need 20+ seconds to generate enough data
- ✓ Refresh browser (Ctrl+R)

---

## 📝 DATA FLOW (What's Happening)

```
IoT Device (h1)
    ↓
creates JSON sensor reading
    ↓
sends UDP to 10.0.0.100:9000
    ↓
OVS Switch intercepts
    ↓
sends PacketIn to Ryu Controller
    ↓
Ryu evaluates PolicyEngine rules
    ↓
decides: CRITICAL → Fog, ANALYTICS → Cloud
    ↓
rewrites IP+Port+MAC via OpenFlow
    ↓
Switch forwards packet to Fog (10.0.0.4) or Cloud (10.0.0.5)
    ↓
Server measures latency, logs alert
    ↓
Gateway aggregates metrics
    ↓
Dashboard displays in real-time
```

---

## ✅ SUCCESS CHECKLIST

Before taking screenshots, verify:

- [ ] All 3 terminals showing "started successfully"
- [ ] Ryu terminal shows routing decisions (search for "[DPI]")
- [ ] Dashboard shows green "Connected" indicator
- [ ] Top stats show non-zero numbers
- [ ] Fog latency < Cloud latency visibly
- [ ] Yellow verdict banner visible
- [ ] Browser page stable (metrics not jumping wildly)

---

## 🎓 Key Insight for Your PPT

**Mode 2 proves the concept with REAL Network Architecture:**
- Real OpenFlow switches (OVS)
- Real packet interception and rewriting
- Real network namespace isolation
- Hardware-based routing decisions

**Result: Fog Computing WORKS, saving milliseconds per packet** ✅

---

Generated: 2025-03-01 | Project: SDN-Assisted Fog Computing for IoT
