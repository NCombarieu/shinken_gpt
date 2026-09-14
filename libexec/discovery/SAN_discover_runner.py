#!/usr/bin/env python3
# Copyright (C) 2009-2012:
#    Romain, FORLOT, romain.forlot@sydel.fr
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import fcntl
import optparse
import re
import socket
import struct
import subprocess

SIOCGIFNETMASK = 0x891B
eth_dev_name = 'eth0'

parser = optparse.OptionParser('%prog [options] -t target')
cmd = {
    'ibm_ds': '/opt/IBM_DS/client/SMcli',
    'example': '/path/to/cmd',
}
parser.add_option('-t', '--target', dest='target', help='IP to manage. One at a time only')
parser.add_option('-v', '--vendor', dest='vendor', help='specify SAN vendor [ibm_ds|...]')
parser.add_option('-n', '--network', action='store_true', dest='network', help='Take controller IP which are on same network as you are')
parser.add_option('-d', '--debug', action='store_true', dest='debug', help='be more verbose')

opts, _args = parser.parse_args()
target = opts.target
vendor = opts.vendor
debug = bool(opts.debug)
network = bool(opts.network)

if not target:
    parser.error('Require at least one ip (option -t)')
if not vendor:
    parser.error('Require SAN vendor name. [ibm_ds|...]')


def _decode(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return value


def debugging(txt):
    if debug:
        print(_decode(txt))


san_vendor = {
    'ibm_ds': {
        'add_cmd': [cmd['ibm_ds'], '-A', target],
        'getprofile_cmd': [cmd['ibm_ds'], target, '-c', 'show storagesubsystem profile;'],
        'sanname_regex': re.compile(r'PROFILE FOR STORAGE SUBSYSTEM:\s(?P<sanname>\w+)\s+.*$', re.S | re.M),
        'controllers_ip_regex': re.compile(r'IP address:\s+((?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))', re.S | re.M),
    },
    'example': {
        'add_cmd': [cmd['example'], 'arg1', 'arg2'],
        'getprofile_cmd': [cmd['example'], 'arg1', 'arg2'],
        'sanname_regex': re.compile(r'(?P<sanname>\w+)', re.S | re.M),
        'controllers_ip_regex': re.compile(r'IP address:\s+((?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?).(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))', re.S | re.M),
    },
}


def get_network_mask(ifname):
    ifname_bytes = ifname.encode('utf-8') if isinstance(ifname, str) else ifname
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        netmask = fcntl.ioctl(sock, SIOCGIFNETMASK, struct.pack('256s', ifname_bytes))[20:24]
    return socket.inet_ntoa(netmask)


def get_ip_address(ifname):
    ifname_bytes = ifname.encode('utf-8') if isinstance(ifname, str) else ifname
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        return socket.inet_ntoa(
            fcntl.ioctl(
                sock.fileno(),
                0x8915,
                struct.pack('256s', ifname_bytes[:15]),
            )[20:24]
        )


def address_in_network(ip, net):
    ipaddr = struct.unpack('L', socket.inet_aton(ip))[0]
    netaddr, bits = net.split('/')
    netmask = struct.unpack('L', socket.inet_aton(netaddr))[0] & struct.unpack('L', socket.inet_aton(bits))[0]
    return ipaddr & netmask == netmask


def set_ip():
    adding = subprocess.Popen(' '.join(v['add_cmd']), stdout=subprocess.PIPE, shell=True)
    stdoutdata, _ = adding.communicate()
    debugging(stdoutdata)


def get_san_profile():
    get_managed_dev = subprocess.Popen(v['getprofile_cmd'], stdout=subprocess.PIPE, text=True)
    stdoutdata, _ = get_managed_dev.communicate()
    debugging(stdoutdata)
    return stdoutdata


def get_name(san_profile):
    match = v['sanname_regex'].search(san_profile)
    if match is None:
        print('Can not retrieve San name')
        return None
    return match.group('sanname')


def get_controllers_ip(san_profile, keep_on_same_network=False):
    controllers = v['controllers_ip_regex'].findall(san_profile)
    debugging('Find ip : %s' % controllers)
    if keep_on_same_network:
        my_ip = get_ip_address(eth_dev_name)
        my_netmask = get_network_mask(eth_dev_name)
        my_subnet_unpacked = struct.unpack('L', socket.inet_aton(my_ip))[0] & struct.unpack('L', socket.inet_aton(my_netmask))[0]
        my_subnet = socket.inet_ntoa(struct.pack('L', my_subnet_unpacked))
        network_spec = '/'.join([my_subnet, my_netmask])
        controllers = [ip for ip in controllers if address_in_network(ip, network_spec)]
    return controllers


def get_discovery_output(sanname, controller_ips):
    for index, ip in enumerate(controller_ips, 1):
        print('%s::_ctrl%d=%s' % (sanname, index, ip))


v = san_vendor[vendor]
set_ip()
profile = get_san_profile()
sanname = get_name(profile)
ctrl_ip = get_controllers_ip(profile, network)
get_discovery_output(sanname, ctrl_ip)
