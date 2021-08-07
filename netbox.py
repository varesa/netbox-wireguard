from pdb import set_trace as st
import pynetbox
import subprocess
from typing import List

from utils import die, find_description, has_tag

URL = 'http://localhost:8000'
TOKEN = subprocess.check_output(['secret-tool', 'lookup', 'service', 'netbox']).decode()


TAG_COREVPN = 'Core VPN'
TAG_PUBLIC_INTERFACE = 'Public interface'
TAG_COREVPN_PREFIXES = 'core-vpn-link-network-pool'

nb = pynetbox.api(URL, token=TOKEN)

interfaces = {}


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


def find_public_interface(interfaces: List):
    for interface in interfaces:
        if has_tag(interface, TAG_PUBLIC_INTERFACE):
            return interface
    return None


def get_interface_ip(interface):
    api = getattr(nb.ipam, 'ip-addresses')
    result = api.get(vminterface_id=interface.id)
    if result:
        return result.address.split('/')[0]
    else:
        return None


def create_nic(vm, target_name: str):
    existing = get_interfaces_for_vm(vm.name)
    index = 0
    for interface in existing:
        if str(interface.name).startswith('wg'):
            existing_index = int(interface.name[2:])
            if existing_index <= index:
                index = existing_index + 1

    api = nb.virtualization.interfaces
    return api.create({
        "name": f"wg{index}",
        "virtual_machine": {"name": vm.name},
        "description": str(target_name)
    })


def get_devices():
    # Physical devices not implemented yet
    api = getattr(nb.virtualization, 'virtual-machines')
    vms = {}

    for vm in api.all():
        if not has_tag(vm, TAG_COREVPN):
            continue
        interfaces = get_interfaces_for_vm(vm.name)
        public_interface = find_public_interface(interfaces) or die(f"Could not find public interface for {vm.name}")
        public_ip = get_interface_ip(public_interface)
        setattr(vm, 'interfaces', interfaces)
        setattr(vm, 'pubkey', vm.custom_fields['wg-public-key'])
        setattr(vm, 'pubip', str(public_ip))
        vms[vm.name] = vm

    return vms


def get_link_prefix_parent():
    api = nb.ipam.prefixes
    return api.get(tag=TAG_COREVPN_PREFIXES)


def get_link_prefix(device1_name: str, device2_name: str):
    names = sorted([device1_name, device2_name])

    api = nb.ipam.prefixes

    pool = get_link_prefix_parent()
    parent_prefix = pool.prefix

    description = f"{names[0]} - {names[1]} [WG]"

    prefixes = api.filter(within=parent_prefix)
    for prefix in prefixes:
        if str(prefix.description) == description:
            return prefix

    # Else create a new one
    return pool.available_prefixes.create({"prefix_length": 30, "description": description})


def get_link_ip(prefix: pynetbox.core.response.Record, device_name: str) -> pynetbox.core.response.Record:
    api = getattr(nb.ipam, 'ip-addresses')

    existing_ips = api.filter(parent=prefix.prefix)
    for ip in existing_ips:
        if ip.description == device_name:
            return ip

    return prefix.available_ips.create({"description": device_name})


