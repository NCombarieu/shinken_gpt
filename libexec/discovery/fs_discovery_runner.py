#!/usr/bin/env python3
# Copyright (C) 2009-2012:
#    Camille, VACQUIE
#    Romain, FORLOT, romain.forlot@sydel.fr
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import optparse
import re

import netsnmp

parser = optparse.OptionParser('%prog [options] -H HOSTADRESS -C SNMPCOMMUNITYREAD -O ARG1 -V SNMPVERSION -l SNMPSECNAME -L SNMPSECLEVEL -p SNMPAUTHPROTO -x SNMPAUTHPASS')
parser.add_option("-H", "--hostname", dest="hostname", help="Hostname to scan")
parser.add_option("-m", "--mode", dest="mode", help="Discovery mode : [ macros | tags ]. Macros will creates host macros and tags will add tags for each fs detected.")
parser.add_option("-C", "--community", dest="community", help="Community to scan (default:public)")
parser.add_option("-O", "--os", dest="os", help="OS from scanned host")
parser.add_option("-V", "--version", dest="version", type=int, help="Version number for SNMP (1, 2 or 3; default:1)")
parser.add_option("-l", "--login", dest="snmpv3_user", help="User name for snmpv3(default:admin)")
parser.add_option("-L", "--level", dest="snmpv3_level", help="Security level for snmpv3(default:authNoPriv)")
parser.add_option("-p", "--authproto", dest="snmpv3_auth", help="Authentication protocol for snmpv3(default:MD5)")
parser.add_option("-x", "--authpass", dest="snmpv3_auth_pass", help="Authentication password for snmpv3(default:monpassword)")

opts, _args = parser.parse_args()

hostname = opts.hostname
operating_system = opts.os
mode = {'macros': '_fs', 'tags': 'fs'}

if not hostname:
    parser.error("Requires one host and its os to scan (option -H)")
if not opts.mode:
    parser.error("Requires mode. Please choose between macros or tags")
if not operating_system:
    parser.error("Requires the os host(option -O)")

community = opts.community or 'public'
version = opts.version or 1
snmpv3_user = opts.snmpv3_user or 'myuser'
snmpv3_level = opts.snmpv3_level or 'authNoPriv'
snmpv3_auth = opts.snmpv3_auth or 'MD5'
snmpv3_auth_pass = opts.snmpv3_auth_pass or 'mypassword'

oid_aix_linux = ".1.3.6.1.2.1.25.3.8.1.2"
oid_hpux = ".1.3.6.1.4.1.11.2.3.1.2.2.1.10"


def get_fs_discovery(oid):
    mount_point = netsnmp.Varbind(oid)
    result = netsnmp.snmpwalk(
        mount_point,
        Version=version,
        DestHost=hostname,
        Community=community,
        SecName=snmpv3_user,
        SecLevel=snmpv3_level,
        AuthProto=snmpv3_auth,
        AuthPass=snmpv3_auth_pass,
    )
    return list(result)


def get_fs_discovery_output(values):
    filesystems = []
    for element in values:
        value = re.sub(r'\W', '_', element)
        if value == '_':
            value = '_root'
        filesystems.append(value)
    print("%s::%s=%s" % (hostname, mode[opts.mode], ','.join(filesystems)))


scan = []
if operating_system in {'aix', 'linux'}:
    scan = get_fs_discovery(oid_aix_linux)
elif operating_system == 'hp-ux':
    scan = get_fs_discovery(oid_hpux)

get_fs_discovery_output(scan)
