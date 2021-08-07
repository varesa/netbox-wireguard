import pynetbox
import subprocess
from typing import Optional

from utils import die, find_description, has_tag

URL = 'http://localhost:8000'
TOKEN = subprocess.check_output(['secret-tool', 'lookup', 'service', 'netbox']).decode()


TAG_COREVPN = 'Core VPN'
TAG_PUBLIC_INTERFACE = 'Public interface'
TAG_COREVPN_PREFIXES = 'core-vpn-link-network-pool'

nb = pynetbox.api(URL, token=TOKEN)

interfaces = {}


class Address:
    netbox_object: pynetbox.core.response.Record = None

    def __init__(self, netbox_object: pynetbox.core.response.Record):
        self.netbox_object = netbox_object

    @property
    def with_mask(self) -> str:
        return self.netbox_object.address

    @property
    def without_mask(self) -> str:
        return self.with_mask.split('/')[0]


class Prefix:
    netbox_object: pynetbox.core.response.Record = None

    def __init__(self, netbox_object: pynetbox.core.response.Record):
        self.netbox_object = netbox_object

    @property
    def cidr(self) -> str:
        return self.netbox_object.prefix

    def create_inner(self, prefix_length=30, description=""):
        return Prefix(self.netbox_object.available_prefixes.create({
            "prefix_length": prefix_length,
            "description": description,
        }))

    def create_address(self, description):
        return Address(self.netbox_object.available_ips.create({
            "description": description,
        }))


class Device:
    netbox_object: pynetbox.core.response.Record = None
    public_ip: Address = None
    public_key: str = None
    interfaces = None

    def __init__(self, netbox_object: pynetbox.core.response.Record, public_ip: Address, interfaces):
        self.netbox_object = netbox_object
        self.public_ip = public_ip
        self.interfaces = interfaces

    @property
    def name(self) -> str:
        return self.netbox_object.name

    @property
    def asn(self) -> int:
        return self.netbox_object.site.asn

    @property
    def public_key(self) -> str:
        return self.netbox_object.custom_fields['wg-public-key']


def get_interfaces():
    global interfaces

    if not interfaces:
        api = nb.virtualization.interfaces

        for interface in api.all():
            vm = str(interface.virtual_machine.name)
            if vm not in interfaces.keys():
                interfaces[vm] = [interface]
            else:
                interfaces[vm].append(interface)

    return interfaces


def get_interfaces_for_vm(name: str):
    interfaces = get_interfaces()
    return interfaces.get(name, [])


def find_public_interface(interfaces: list):
    for interface in interfaces:
        if has_tag(interface, TAG_PUBLIC_INTERFACE):
            return interface
    return None


def get_interface_ip(interface) -> Optional[Address]:
    api = getattr(nb.ipam, 'ip-addresses')
    result = api.get(vminterface_id=interface.id)
    if result:
        return Address(result)
    else:
        return None


def create_nic(device: Device, target_name: str):
    existing = get_interfaces_for_vm(device.name)
    index = 0
    for interface in existing:
        if str(interface.name).startswith('wg'):
            existing_index = int(interface.name[2:])
            if existing_index <= index:
                index = existing_index + 1

    api = nb.virtualization.interfaces
    return api.create({
        "name": f"wg{index}",
        "virtual_machine": {"name": device.name},
        "description": str(target_name)
    })


def get_devices() -> dict[Device]:
    # Physical devices not implemented yet
    api = getattr(nb.virtualization, 'virtual-machines')
    devices = {}

    for vm in api.all():
        if not has_tag(vm, TAG_COREVPN):
            continue

        interfaces = get_interfaces_for_vm(vm.name)
        public_interface = find_public_interface(interfaces)
        public_ip = get_interface_ip(public_interface) if public_interface else None

        devices[vm.name] = Device(
            netbox_object=vm,
            interfaces=interfaces,
            public_ip=public_ip,
        )

    return devices


def get_link_prefix_parent() -> Prefix:
    api = nb.ipam.prefixes
    return Prefix(api.get(tag=TAG_COREVPN_PREFIXES))


def get_link_prefix(device1_name: str, device2_name: str) -> Prefix:
    names = sorted([device1_name, device2_name])

    api = nb.ipam.prefixes

    pool = get_link_prefix_parent()
    parent_prefix = pool.cidr

    description = f"{names[0]} - {names[1]} [WG]"

    prefixes = api.filter(within=parent_prefix)
    for prefix in prefixes:
        if str(prefix.description) == description:
            return Prefix(prefix)

    # Else create a new one
    return pool.create_inner(description=description)


def get_link_ip(prefix: pynetbox.core.response.Record, device_name: str) -> Address:
    api = getattr(nb.ipam, 'ip-addresses')

    existing_ips = api.filter(parent=prefix.cidr)
    for ip in existing_ips:
        if ip.description == device_name:
            return Address(ip)

    return prefix.create_address(device_name)