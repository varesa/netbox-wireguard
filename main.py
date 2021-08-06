from pdb import set_trace as st
import pynetbox
import subprocess
from typing import List

URL = 'http://localhost:8000'
TOKEN = subprocess.check_output(['secret-tool', 'lookup', 'service', 'netbox']).decode()


TAG_COREVPN = 'Core VPN'

nb = pynetbox.api(URL, token=TOKEN)


class Device:
    def __init__(self, name: str, asn: int, interfaces: List):
        self.name = name
        self.asn = asn
        self.interfaces = interfaces


def has_tag(record, required_tag):
    for tag in record.tags:
        if str(tag) == required_tag:
            return True
    return False


interfaces = {}


def get_interfaces():
    global interfaces

    if not interfaces:
        api = nb.virtualization.interfaces

        for interface in api.all():
            vm = interface.virtual_machine
            if vm not in interfaces.keys():
                interfaces[vm] = [interface]
            else:
                interfaces[vm].append(interface)

    return interfaces


def get_interfaces_for_vm(name: str):
    interfaces = get_interfaces()
    return interfaces[name]


def get_devices():
    # Physical devices not implemented yet
    api = getattr(nb.virtualization, 'virtual-machines')
    vms = []

    for vm in api.all():
        if not has_tag(vm, TAG_COREVPN):
            continue
        interfaces = get_interfaces_for_vm(vm.name)
        vms.append(Device(vm.name, vm.site.asn, interfaces))

    return vms


devices = get_devices()
st()
