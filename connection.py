from netbox import get_link_prefix_parent, get_link_prefix, Device, Address
from utils import get_subnet_offset, find_description, die


class ConnectionEndpoint:
    device = None
    interface_name: str = None
    public_ip: Address = None
    tunnel_ip: Address = None
    port: int = None
    asn: int = None

    def __init__(self, device, interface_name, public_ip, tunnel_ip, port, asn):
        self.device = device
        self.interface_name = interface_name
        self.public_ip = public_ip
        self.tunnel_ip = tunnel_ip
        self.port = port
        self.asn = asn


def make_connection(local_device: Device, peer_device: Device) -> ConnectionEndpoint:
    interface_name = find_description(local_device.interfaces, peer_device.name) \
                      or local_device.create_nic(peer_device.name)

    prefix = get_link_prefix(local_device.name, peer_device.name)
    offset = get_subnet_offset(get_link_prefix_parent().cidr, prefix.cidr)
    port = 51820 + offset
    link_ip = prefix.get_or_create_address(local_device.name)

    return ConnectionEndpoint(
        device=local_device,
        interface_name=interface_name,
        public_ip=local_device.public_ip or die(f"Could not find public interface for {local_device.name}"),
        tunnel_ip=link_ip,
        port=port,
        asn=local_device.asn,
    )