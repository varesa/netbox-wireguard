from pdb import set_trace as st
import pynetbox
import subprocess
import sys
from textwrap import dedent
from typing import List

URL = 'http://localhost:8000'
TOKEN = subprocess.check_output(['secret-tool', 'lookup', 'service', 'netbox']).decode()


TAG_COREVPN = 'Core VPN'
TAG_PUBLIC_INTERFACE = 'Public interface'
TAG_COREVPN_PREFIXES = 'core-vpn-link-network-pool'

nb = pynetbox.api(URL, token=TOKEN)


def die(message: str):
    print(message)
    sys.exit(1)


def has_tag(record, required_tag):
    for tag in record.tags:
        if str(tag) == required_tag:
            return True
    return False


def find_description(records, required_description):
    for record in records:
        if str(record.description) == required_description:
            return record
    else:
        return None


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


def get_link_prefix(device1, device2):
    names = sorted([device1.name, device2.name])

    api = nb.ipam.prefixes

    pool = api.get(tag=TAG_COREVPN_PREFIXES)
    parent_prefix = pool.prefix

    description = f"{names[0]} - {names[1]} [WG]"

    prefixes = api.filter(within=parent_prefix)
    for prefix in prefixes:
        if str(prefix.description) == description:
            return prefix.prefix

    # Else create a new one
    return pool.available_prefixes.create({"prefix_length": 30, "description": description})


def generate_wg_interface(interface_name, remote_device):
    print(dedent(f"""
    set interfaces wireguard {interface_name} address '<tbd>/30'
    set interfaces wireguard {interface_name} description 'to {remote_device.name}'
    set interfaces wireguard {interface_name} mtu '1420'
    set interfaces wireguard {interface_name} peer {remote_device.name} address '{remote_device.pubip}'
    set interfaces wireguard {interface_name} peer {remote_device.name} allowed-ips '0.0.0.0/0'
    set interfaces wireguard {interface_name} peer {remote_device.name} port '<tbd>'
    set interfaces wireguard {interface_name} peer {remote_device.name} pubkey '{remote_device.pubkey}'
    set interfaces wireguard {interface_name} port '<tbd>'

    """))


def gen_config_device(conf_device, peer_device):
    print(conf_device.name, conf_device.pubkey, conf_device.pubip, conf_device.site.asn)

    conf_device_nic = find_description(conf_device.interfaces, peer_device.name) \
        or create_nic(conf_device, peer_device.name)

    prefix = get_link_prefix(conf_device, peer_device)

    generate_wg_interface(str(conf_device_nic), peer_device)


def main():
    devices = get_devices()

    device1 = devices.get(sys.argv[1], None) or die(f"Device {sys.argv[1]} not found")
    device2 = devices.get(sys.argv[2], None) or die(f"Device {sys.argv[2]} not found")

    gen_config_device(device1, device2)
    gen_config_device(device2, device1)


if __name__ == '__main__':
    main()
