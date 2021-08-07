import pynetbox
import subprocess
from typing import Optional

from utils import has_tag

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

    def create_inner(self, prefix_length: int=30, description: str="") -> 'Prefix':
        return Prefix(self.netbox_object.available_prefixes.create({
            "prefix_length": prefix_length,
            "description": description,
        }))

    def create_address(self, description: str) -> Address:
        return Address(self.netbox_object.available_ips.create({
            "description": description,
        }))

    def get_or_create_address(self, device_name: str) -> Address:
        api = getattr(nb.ipam, 'ip-addresses')

        existing_ips = api.filter(parent=self.cidr)
        for ip in existing_ips:
            if ip.description == device_name:
                return Address(ip)

        return self.create_address(device_name)


class Interface:
    netbox_object: pynetbox.core.response.Record = None

    def __init__(self, netbox_object: pynetbox.core.response.Record):
        self.netbox_object = netbox_object

    @property
    def id(self) -> int:
        return self.netbox_object.id

    @property
    def name(self) -> str:
        return self.netbox_object.name

    @property
    def tags(self) -> list:
        return self.netbox_object.tags

    @property
    def description(self) -> str:
        return self.netbox_object.description

    @property
    def ip(self) -> Optional[Address]:
        api = getattr(nb.ipam, 'ip-addresses')
        result = api.get(vminterface_id=self.id)
        if result:
            return Address(result)
        else:
            return None


class Device:
    netbox_object: pynetbox.core.response.Record = None
    public_ip: Address = None

    def __init__(self, netbox_object: pynetbox.core.response.Record):
        self.netbox_object = netbox_object

        public_interface = self.public_interface
        self.public_ip = public_interface.ip if public_interface else None

    @property
    def name(self) -> str:
        return self.netbox_object.name

    @property
    def asn(self) -> int:
        return self.netbox_object.site.asn

    @property
    def public_key(self) -> str:
        return self.netbox_object.custom_fields['wg-public-key']

    @property
    def interfaces(self) -> list[Interface]:
        return get_interfaces().get(self.name, [])

    def create_nic(self, target_name: str) -> Interface:
        existing = self.interfaces
        index = 0
        for interface in existing:
            if str(interface.name).startswith('wg'):
                existing_index = int(interface.name[2:])
                if existing_index <= index:
                    index = existing_index + 1

        api = nb.virtualization.interfaces
        return api.create({
            "name": f"wg{index}",
            "virtual_machine": {"name": self.name},
            "description": str(target_name)
        })

    @property
    def public_interface(self) -> Interface:
        public_interfaces = list(filter(lambda interface: has_tag(interface, TAG_PUBLIC_INTERFACE), self.interfaces))
        assert 0 <= len(public_interfaces) <= 1
        return public_interfaces[0] if public_interfaces else None


def get_interfaces() -> dict[str, Interface]:
    global interfaces

    if not interfaces:
        api = nb.virtualization.interfaces

        for interface in api.all():
            vm = str(interface.virtual_machine.name)
            if vm not in interfaces.keys():
                interfaces[vm] = [Interface(interface)]
            else:
                interfaces[vm].append(Interface(interface))

    return interfaces


def get_devices() -> dict[str, Device]:
    # Physical devices not implemented yet
    api = getattr(nb.virtualization, 'virtual-machines')
    devices = {}

    for vm in api.all():
        if not has_tag(vm, TAG_COREVPN):
            continue

        devices[vm.name] = Device(netbox_object=vm)

    return devices


def get_link_prefix_pool() -> Prefix:
    api = nb.ipam.prefixes
    return Prefix(api.get(tag=TAG_COREVPN_PREFIXES))


def get_link_prefix(device1_name: str, device2_name: str) -> Prefix:
    names = sorted([device1_name, device2_name])

    api = nb.ipam.prefixes

    pool = get_link_prefix_pool()
    parent_prefix = pool.cidr

    description = f"{names[0]} - {names[1]} [WG]"

    prefixes = api.filter(within=parent_prefix)
    for prefix in prefixes:
        if str(prefix.description) == description:
            return Prefix(prefix)

    # Else create a new one
    return pool.create_inner(description=description)
