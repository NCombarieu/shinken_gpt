#!/usr/bin/env python3
# Copyright (C) 2009-2010:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel <h.goebel@goebel-consult.de>
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import sys
import shutil
import optparse
from subprocess import Popen, PIPE

VERSION = '0.1'


def _split_rules(rules):
    return [r.strip() for r in rules.split('|')]


def _apply_rules(name, rules):
    if 'nofqdn' in rules:
        name = name.split('.', 1)[0]
    if 'lower' in rules:
        name = name.lower()
    return name


def get_vmware_hosts(check_esx_path, vcenter, user, password):
    list_host_cmd = [check_esx_path, '-D', vcenter, '-u', user, '-p', password,
                     '-l', 'runtime', '-s', 'listhost']
    output = Popen(list_host_cmd, stdout=PIPE, text=True).communicate()
    parts = output[0].split(':')
    if len(parts) < 2:
        raise RuntimeError("Unexpected output from check_esx3.pl: %s" % output[0])
    hsts_raw = parts[1].split('|')[0]
    return [item.strip().split('(')[0] for item in hsts_raw.split(',')]


def get_vm_of_host(check_esx_path, vcenter, host, user, password):
    print("Listing host", host)
    list_vm_cmd = [check_esx_path, '-D', vcenter, '-H', host,
                   '-u', user, '-p', password,
                   '-l', 'runtime', '-s', 'list']
    output = Popen(list_vm_cmd, stdout=PIPE, text=True).communicate()
    parts = output[0].split(':')
    if len(parts) < 2:
        return None

    vms_raw = parts[1].split('|')[0]
    return [item.strip().split('(')[0] for item in vms_raw.split(',')]


def create_all_links(res, rules):
    links = []
    for host, vms in res.items():
        for vm in vms:
            host_name = _apply_rules(host, rules)
            vm_name = _apply_rules(vm, rules)
            links.append((('host', host_name), ('host', vm_name)))
    return links


def write_output(links, path):
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as handle:
            json.dump(links, handle)
        shutil.move(path + '.tmp', path)
        print("File %s wrote" % path)
    except OSError as exp:
        sys.exit("Error writing the file %s: %s" % (path, exp))


def main(check_esx_path, vcenter, user, password, output, rules):
    rules = _split_rules(rules)
    res = {}
    hosts = get_vmware_hosts(check_esx_path, vcenter, user, password)

    for host in hosts:
        lst = get_vm_of_host(check_esx_path, vcenter, host, user, password)
        if lst:
            res[host] = lst

    links = create_all_links(res, rules)
    print("Created %d links" % len(links))
    write_output(links, output)
    print("Finished!")


if __name__ == "__main__":
    parser = optparse.OptionParser(
        version="Shinken VMware links dumping script version %s" % VERSION)
    parser.add_option("-o", "--output",
                      help="Path of the generated mapping file.")
    parser.add_option("-x", "--esx3-path", dest='check_esx_path',
                      default='/usr/local/nagios/libexec/check_esx3.pl',
                      help="Full path of the check_esx3.pl script (default: %default)")
    parser.add_option("-V", "--vcenter", '--Vcenter',
                      help="The IP/DNS address of your Vcenter host.")
    parser.add_option("-u", "--user",
                      help="User name to connect to this Vcenter")
    parser.add_option("-p", "--password",
                      help="The password of this user")
    parser.add_option('-r', '--rules', default='',
                      help="Rules of name transformation. Valid names are: "
                      "`lower`: to lower names, "
                      "`nofqdn`: keep only the first name (server.mydomain.com -> server)."
                      "You can use several rules like `lower|nofqdn`")

    opts, args = parser.parse_args()
    if args:
        parser.error("does not take any positional arguments")
    if opts.vcenter is None:
        parser.error("missing -V or --Vcenter option for the vcenter IP/DNS address")
    if opts.user is None:
        parser.error("missing -u or --user option for the vcenter username")
    if opts.password is None:
        parser.error("missing -p or --password option for the vcenter password")
    if not os.path.exists(opts.check_esx_path):
        parser.error("the path %s for the check_esx3.pl script is wrong, missing file" % opts.check_esx_path)
    if opts.output is None:
        parser.error("missing -o or --output option for the output mapping file")

    main(**opts.__dict__)
