import sys
import ipaddress


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


def get_subnet_offset(parent: str, child: str):
    """
    Return the index of the subnet inside a pool when pool is evenly divided into smaller subnets.
    E.g. 10.0.0.4/30 is the 2nd (offset=1) subnet with a /30 mask inside 10.0.0.0/24
    """

    subnets = [str(subnet) for subnet in ipaddress.IPv4Network(parent).subnets(new_prefix=30)]
    return subnets.index(child)