#!/usr/bin/env python3
"""
Mininet Topology - SDN-Assisted Fog Computing
==============================================
Creates a standard star topology:
- 3 Host (IoT Devices)
- 1 Switch (Open vSwitch)
- 1 Controller (Ryu)
- 1 Fog Server
- 1 Cloud Server
- 1 Collector (Proxy/Gateway node)
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel

class FogIoTTopo(Topo):
    def build(self):
        # Add switch
        s1 = self.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')

        # Add nodes
        # IoT Devices
        h1 = self.addHost('h1', ip='10.0.0.1')
        h2 = self.addHost('h2', ip='10.0.0.2')
        h3 = self.addHost('h3', ip='10.0.0.3')

        # Servers
        fog = self.addHost('fog', ip='10.0.0.4')
        cloud = self.addHost('cloud', ip='10.0.0.5')
        
        # Collector (SDN Proxy/Gateway)
        collector = self.addHost('collector', ip='10.0.0.100')

        # Connect nodes to switch
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(fog, s1)
        self.addLink(cloud, s1)
        self.addLink(collector, s1)

def run():
    topo = FogIoTTopo()
    net = Mininet(topo=topo, controller=RemoteController, switch=OVSSwitch)
    net.start()
    
    print("Network started.")
    print("Nodes: h1(IoT), h2(IoT), h3(IoT), fog, cloud, collector")
    
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
