#!/usr/bin/env python3
# Copyright (C) 2009-2010:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#
# This file is part of Shinken.

import optparse
import os
import subprocess
import sys
import tempfile
from xml.etree.ElementTree import ElementTree

VERSION = '0.1.1'
DEFAULT_CMD = (
    'sudo nmap %s -sU -sS --min-rate %d --max-retries %d -T4 -O -oX %s'
    if os.name != 'nt'
    else 'nmap %s -sU -sS --min-rate %d --max-retries %d -T4 -O -oX %s'
)

parser = optparse.OptionParser(
    '%prog [options] -t nmap scanning targets', version='%prog ' + VERSION
)
parser.add_option('-t', '--targets', dest='targets', help='NMap scanning targets.')
parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose output.')
parser.add_option('--min-rate', dest='min_rate', help='Min rate option for nmap. Default: 1000')
parser.add_option('--max-retries', dest='max_retries', help='Max retries option for nmap. Default: 0')
parser.add_option('-s', '--simulate', dest='simulate', help='Read an existing nmap XML output.')
opts, args = parser.parse_args()

if not opts.simulate and not opts.targets:
    parser.error('Requires at least one nmap target for scanning (option -t/--targets)')

targets = []
if opts.targets:
    targets.append(opts.targets)
targets.extend(args)
simulate = opts.simulate
min_rate = int(opts.min_rate) if opts.min_rate else 1000
max_retries = int(opts.max_retries) if opts.max_retries else 0
verbose = bool(opts.verbose)

print('Got our target', targets)


def debug(message):
    if verbose:
        print(message)


def is_up(host):
    status = host.find('status')
    return status is not None and status.attrib.get('state') == 'up'


class DetectedHost:
    def __init__(self):
        self.ip = ''
        self.mac_vendor = ''
        self.host_name = ''
        self.os_possibilities = []
        self.os = ('', '', '', '')
        self.open_ports = []
        self.parent = ''
        self.parents = []
        self.os_name = 'Unknown OS'
        self.os_version = 'Unknown Version'
        self.os_type = 'Unknown Type'
        self.os_vendor = 'Unknown Vendor'

    def set_host_name(self, name):
        if not self.host_name:
            self.host_name = name

    def get_name(self):
        return self.host_name or self.ip or None

    def is_vmware_esx(self):
        if self.mac_vendor.lower() != 'vmware':
            return False
        return all(port in self.open_ports for port in [22, 80, 443, 902, 903, 5989])

    def is_vmware_vm(self):
        return not self.is_vmware_esx() and self.mac_vendor.lower() == 'vmware'

    def add_os_possibility(self, os_name, osgen, accuracy, os_type, vendor):
        try:
            accuracy = int(accuracy)
        except (TypeError, ValueError):
            accuracy = 0
        self.os_possibilities.append((os_name, osgen, accuracy, os_type, vendor))

    def look_for_parent(self, all_hosts):
        self.parents = []
        if not self.parent:
            return
        for host in all_hosts:
            if host.get_name() == self.parent:
                self.parents.append(host.get_name())

    def compute_os(self):
        if not self.os_possibilities:
            return
        self.os = max(self.os_possibilities, key=lambda candidate: candidate[2])
        os_name, osgen, _accuracy, os_type, vendor = self.os
        self.os_name = (os_name or 'Unknown OS').lower()
        self.os_version = (osgen or 'Unknown Version').lower()
        self.os_type = (os_type or 'Unknown Type').lower()
        self.os_vendor = (vendor or 'Unknown Vendor').lower()

    def get_discovery_system(self):
        return '\n'.join([
            '%s::os=%s' % (self.get_name(), self.os_name),
            '%s::osversion=%s' % (self.get_name(), self.os_version),
            '%s::ostype=%s' % (self.get_name(), self.os_type),
            '%s::osvendor=%s' % (self.get_name(), self.os_vendor),
        ])

    def get_discovery_macvendor(self):
        return '%s::macvendor=%s' % (self.get_name(), self.mac_vendor)

    def get_discovery_ports(self):
        if not self.open_ports:
            return ''
        return '%s::openports=%s' % (self.get_name(), ','.join(map(str, self.open_ports)))

    def get_discovery_parents(self):
        if not self.parents:
            return ''
        return '%s::parents=%s' % (self.get_name(), ','.join(self.parents))

    def get_dicovery_fqdn(self):
        return '%s::fqdn=%s' % (self.get_name(), self.host_name) if self.host_name else ''

    def get_discovery_ip(self):
        return '%s::ip=%s' % (self.get_name(), self.ip) if self.ip else ''

    def get_discovery_output(self):
        result = [
            '%s::isup=1' % self.get_name(),
            self.get_discovery_system(),
            self.get_discovery_macvendor(),
            self.get_discovery_ports(),
            self.get_discovery_parents(),
            self.get_dicovery_fqdn(),
            self.get_discovery_ip(),
        ]
        return [entry for entry in result if entry]


def run_nmap():
    fd, tmp_path = tempfile.mkstemp()
    os.close(fd)
    cmd = DEFAULT_CMD % (' '.join(targets), min_rate, max_retries, tmp_path)
    print('Launching command,', cmd)
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=False, shell=True, text=True,
        )
    except OSError as exp:
        print('Debug: Error in launching command:', cmd, exp)
        raise SystemExit(2)
    stdoutdata, stderrdata = process.communicate()
    debug(stdoutdata)
    if process.returncode != 0:
        print("Error: nmap returned an error: '%s'" % stderrdata)
        raise SystemExit(2)
    return tmp_path


xml_input = simulate or run_nmap()
try:
    tree = ElementTree()
    tree.parse(xml_input)
except (OSError, ValueError) as exp:
    print("Error opening file '%s': %s" % (xml_input, exp))
    raise SystemExit(2)

hosts = tree.findall('host')
debug('Number of hosts: %d' % len(hosts))
all_hosts = []

for host in hosts:
    if not is_up(host):
        continue

    detected = DetectedHost()
    for addr in host.findall('address'):
        addr_type = addr.attrib.get('addrtype')
        if addr_type == 'ipv4':
            detected.ip = addr.attrib.get('addr', '')
        elif addr_type == 'mac':
            detected.mac_vendor = addr.attrib.get('vendor', '')

    for hostnames in host.findall('hostnames'):
        for hostname in hostnames.findall('hostname'):
            detected.set_host_name(hostname.attrib.get('name', ''))

    for trace in host.findall('trace'):
        hops = trace.findall('hop')
        distance = len(hops)
        if distance >= 2:
            for hop in hops:
                if int(hop.attrib.get('ttl', 0)) == distance - 1:
                    detected.parent = hop.attrib.get('host') or hop.attrib.get('ipaddr', '')

    os_node = host.find('os')
    classes = []
    if os_node is not None:
        classes = os_node.findall('osclass')
        if not classes:
            os_match = os_node.find('osmatch')
            if os_match is not None:
                classes = os_match.findall('osclass')

    if classes:
        for os_class in classes:
            detected.add_os_possibility(
                os_class.attrib.get('osfamily', ''),
                os_class.attrib.get('osgen', ''),
                os_class.attrib.get('accuracy', 0),
                os_class.attrib.get('type', ''),
                os_class.attrib.get('vendor', ''),
            )
    else:
        detected.add_os_possibility('Unknown', 'Unknown', 0, 'Unknown', 'Unknown')
    detected.compute_os()

    for ports in host.findall('ports'):
        for port in ports.findall('port'):
            state = port.find('state')
            if state is not None and state.attrib.get('state') == 'open':
                detected.open_ports.append(int(port.attrib['portid']))

    all_hosts.append(detected)

for host in all_hosts:
    if not host.get_name():
        continue
    host.look_for_parent(all_hosts)
    print('\n'.join(host.get_discovery_output()))

if not simulate:
    try:
        os.unlink(xml_input)
    except OSError:
        pass
