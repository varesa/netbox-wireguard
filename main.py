from pdb import set_trace as st
import sys
from textwrap import dedent

from utils import die, find_description, has_tag, get_subnet_offset
from netbox import create_nic, get_link_prefix, get_devices, get_link_ip, get_link_prefix_parent
from connection import ConnectionEndpoint, make_connection


def generate_wg_interface(local_endpoint: ConnectionEndpoint, remote_endpoint: ConnectionEndpoint):
    print(dedent(f"""
    set interfaces wireguard {local_endpoint.interface_name} address '{local_endpoint.tunnel_ip}/30'
    set interfaces wireguard {local_endpoint.interface_name} description 'to {remote_endpoint.device.name}'
    set interfaces wireguard {local_endpoint.interface_name} mtu '1420'
    set interfaces wireguard {local_endpoint.interface_name} peer {remote_endpoint.device.name} address '{remote_endpoint.device.pubip}'
    set interfaces wireguard {local_endpoint.interface_name} peer {remote_endpoint.device.name} allowed-ips '0.0.0.0/0'
    set interfaces wireguard {local_endpoint.interface_name} peer {remote_endpoint.device.name} port '{local_endpoint.port}'
    set interfaces wireguard {local_endpoint.interface_name} peer {remote_endpoint.device.name} pubkey '{remote_endpoint.device.pubkey}'
    set interfaces wireguard {local_endpoint.interface_name} port '{local_endpoint.port}'
    """))


def generate_bgp_peer(local_endpoint: ConnectionEndpoint, remote_endpoint: ConnectionEndpoint):
    print(dedent(f"""
    set protocols bgp {local_endpoint.asn} neighbor {remote_endpoint.tunnel_ip} address-family ipv4-unicast route-map import 'ONLYRFC1918PREFIXES'
    set protocols bgp {local_endpoint.asn} neighbor {remote_endpoint.tunnel_ip} address-family ipv4-unicast route-map export 'ONLYRFC1918PREFIXES'
    set protocols bgp {local_endpoint.asn} neighbor {remote_endpoint.tunnel_ip} address-family ipv4-unicast soft-reconfiguration inbound
    set protocols bgp {local_endpoint.asn} neighbor {remote_endpoint.tunnel_ip} description '{remote_endpoint.device.name}'
    set protocols bgp {local_endpoint.asn} neighbor {remote_endpoint.tunnel_ip} remote-as '{remote_endpoint.asn}'
    """))


def gen_config_device(conf_device, peer_device):
    local_ep = make_connection(conf_device, peer_device)
    remote_ep = make_connection(peer_device, conf_device)

    generate_wg_interface(local_ep, remote_ep)
    generate_bgp_peer(local_ep, remote_ep)


def main():
    devices = get_devices()

    device1 = devices.get(sys.argv[1], None) or die(f"Device {sys.argv[1]} not found")
    device2 = devices.get(sys.argv[2], None) or die(f"Device {sys.argv[2]} not found")

    gen_config_device(device1, device2)
    gen_config_device(device2, device1)


if __name__ == '__main__':
    main()
