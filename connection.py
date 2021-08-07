from netbox import get_link_ip, get_link_prefix_parent, get_link_prefix, create_nic
from utils import get_subnet_offset, find_description


class ConnectionEndpoint:
    device = None
    interface_name: str = None
    public_ip: str = None
    tunnel_ip: str = None
    port: int = None

    def __init__(self, device, interface_name, public_ip, tunnel_ip, port):
        self.device = device
        self.interface_name = interface_name
        self.public_ip = public_ip
        self.tunnel_ip = tunnel_ip
        self.port = port


def make_connection(local_device, peer_device) -> ConnectionEndpoint:
    interface_name = find_description(local_device.interfaces, peer_device.name) \
                      or create_nic(local_device, peer_device.name)

    prefix = get_link_prefix(local_device.name, peer_device.name)
    offset = get_subnet_offset(get_link_prefix_parent().prefix, prefix.prefix)
    port = 51820 + offset
    link_ip = get_link_ip(prefix, local_device.name).address

    return ConnectionEndpoint(
        device=local_device,
        interface_name=interface_name,
        public_ip=local_device.pubip,
        tunnel_ip=link_ip,
        port=port,
    )