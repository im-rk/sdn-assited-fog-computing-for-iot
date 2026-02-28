#!/usr/bin/env python3
"""
Mininet Topology — SDN-Assisted Fog Computing for IoT
======================================================
Star topology: all hosts connected to a single OpenFlow switch.
The Ryu SDN controller runs externally and controls the switch.

Data flow:
  IoT Host (h1/h2/h3)
      │  sends UDP to 10.0.0.100:9000 (collector — virtual SDN intercept address)
      ▼
  OpenFlow Switch (s1)
      │  no flow rule → sends PacketIn to Ryu controller
      ▼
  Ryu SDN Controller (sdn_controller.py)
      │  DPI → PolicyEngine → routing decision (JSON policy, no hardcoding)
      │  rewrites dst IP + port + MAC at the switch
      │  installs flow rule (next packets bypass controller)
      ▼
  Fog Server (10.0.0.4:5001)   ← EMERGENCY / CRITICAL traffic
  Cloud Server (10.0.0.5:5002) ← ANALYTICS / BULK traffic

Run order:
  Terminal 1:  ryu-manager controller/sdn_controller.py
  Terminal 2:  sudo python3 topology/network_topology.py
  Terminal 3:  python3 gateway/api_gateway.py          (optional — for dashboard)
"""

import os
import time

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VENV_PYTHON  = os.path.join(PROJECT_ROOT, 'venv', 'bin', 'python3')


class FogIoTTopo(Topo):
    """
    Network layout:

      h1 (10.0.0.1) ─────┐
      h2 (10.0.0.2) ──── s1 ──── [Ryu Controller @ localhost:6633]
      h3 (10.0.0.3) ─────┤
      fog   (10.0.0.4)───┤   ← critical/emergency traffic lands here
      cloud (10.0.0.5)───┤   ← analytics/bulk traffic lands here
      collector(10.0.0.100)┘  ← virtual SDN intercept IP (Ryu intercepts before arrival)
    """

    def build(self):
        s1 = self.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')

        # IoT Device nodes — know NOTHING about Fog or Cloud
        # They only know the collector address (10.0.0.100:9000)
        h1 = self.addHost('h1',    ip='10.0.0.1/24',   mac='00:00:00:00:00:01')
        h2 = self.addHost('h2',    ip='10.0.0.2/24',   mac='00:00:00:00:00:02')
        h3 = self.addHost('h3',    ip='10.0.0.3/24',   mac='00:00:00:00:00:03')

        # Processing nodes — Ryu routes critical → fog, analytics → cloud
        fog       = self.addHost('fog',       ip='10.0.0.4/24',   mac='00:00:00:00:00:04')
        cloud     = self.addHost('cloud',     ip='10.0.0.5/24',   mac='00:00:00:00:00:05')

        # Virtual collector — IoT devices send here.
        # Ryu intercepts packets BEFORE they reach this host and redirects them.
        collector = self.addHost('collector', ip='10.0.0.100/24', mac='00:00:00:00:00:64')

        # Star topology — all connected to the single OpenFlow switch
        self.addLink(h1,        s1)
        self.addLink(h2,        s1)
        self.addLink(h3,        s1)
        self.addLink(fog,       s1)
        self.addLink(cloud,     s1)
        self.addLink(collector, s1)


def run(no_cli=False):
    topo = FogIoTTopo()
    net  = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6633),
        switch=OVSSwitch
    )
    net.start()

    fog       = net.get('fog')
    cloud     = net.get('cloud')
    h1        = net.get('h1')
    h2        = net.get('h2')
    h3        = net.get('h3')

    info('\n' + '=' * 65 + '\n')
    info('  SDN-Assisted Fog Computing for IoT — Mininet\n')
    info('=' * 65 + '\n\n')

    # ── Connectivity check ────────────────────────────────────────────────────
    info('[1/5] Testing connectivity (ping all)...\n')
    packet_loss = net.pingAll()
    info(f'       Packet loss: {packet_loss}%\n\n')

    # ── Start Fog and Cloud servers on their respective hosts ─────────────────
    info('[2/5] Starting Fog Server on fog (10.0.0.4:5001)...\n')
    fog.cmd(f'{VENV_PYTHON} {PROJECT_ROOT}/servers/fog_server.py > /tmp/fog_server.log 2>&1 &')

    info('[3/5] Starting Cloud Server on cloud (10.0.0.5:5002)...\n')
    cloud.cmd(f'{VENV_PYTHON} {PROJECT_ROOT}/servers/cloud_server.py > /tmp/cloud_server.log 2>&1 &')

    info('       Waiting for servers to initialise...\n')
    time.sleep(2)

    # ── Start IoT device simulators on their respective hosts ─────────────────
    # Each device sends to 10.0.0.100:9000 (the virtual SDN intercept address).
    # They have NO idea whether data goes to Fog or Cloud — the SDN controller decides.
    info('[4/5] Starting IoT device simulators...\n')

    info('       h1 → Fire Alarm Sensor      → 10.0.0.100:9000\n')
    h1.cmd(
        f'{VENV_PYTHON} {PROJECT_ROOT}/iot_devices/fire_alarm.py '
        f'--host 10.0.0.100 --port 9000 '
        f'> /tmp/fire_alarm.log 2>&1 &'
    )

    info('       h2 → Temperature Sensor     → 10.0.0.100:9000\n')
    h2.cmd(
        f'{VENV_PYTHON} {PROJECT_ROOT}/iot_devices/temperature_sensor.py '
        f'--host 10.0.0.100 --port 9000 '
        f'> /tmp/temp_sensor.log 2>&1 &'
    )

    info('       h3 → Analytics Generator    → 10.0.0.100:9000\n')
    h3.cmd(
        f'{VENV_PYTHON} {PROJECT_ROOT}/iot_devices/analytics_generator.py '
        f'--host 10.0.0.100 --port 9000 '
        f'> /tmp/analytics.log 2>&1 &'
    )

    time.sleep(1)

    info('\n[5/5] All hosts active. IoT data is flowing.\n')
    info('       Ryu controller is inspecting packets and making routing decisions.\n\n')

    info('=' * 65 + '\n')
    info('  HOSTS\n')
    info('  h1   10.0.0.1    Fire Alarm Sensor\n')
    info('  h2   10.0.0.2    Temperature Sensor\n')
    info('  h3   10.0.0.3    Analytics Generator\n')
    info('  fog  10.0.0.4    Fog/Edge Server     (UDP:5001  HTTP:5101)\n')
    info('  cld  10.0.0.5    Cloud Server        (UDP:5002  HTTP:5102)\n')
    info('  coll 10.0.0.100  Virtual SDN intercept address\n\n')
    info('  LOGS (tail these to see live traffic)\n')
    info('  Fog server   : tail -f /tmp/fog_server.log\n')
    info('  Cloud server : tail -f /tmp/cloud_server.log\n')
    info('  Fire alarm   : tail -f /tmp/fire_alarm.log\n')
    info('  Temp sensor  : tail -f /tmp/temp_sensor.log\n\n')
    info('  DASHBOARD\n')
    info('  Start gateway: python3 gateway/api_gateway.py\n')
    info('  Then open:     dashboard/index.html\n\n')
    info('  Type "exit" or Ctrl-D to stop the network.\n')
    info('=' * 65 + '\n\n')

    if no_cli:
        info('Running in daemon mode (--no-cli). Press Ctrl+C to stop.\n')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        CLI(net)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    info('\nStopping all processes on hosts...\n')
    for host in [h1, h2, h3, fog, cloud]:
        host.cmd('kill %python3 2>/dev/null; true')

    net.stop()
    info('Network stopped.\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-cli', action='store_true', help='Run without interactive CLI (daemon mode)')
    args = parser.parse_args()
    setLogLevel('info')
    run(no_cli=args.no_cli)
