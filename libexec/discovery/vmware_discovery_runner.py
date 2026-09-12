#!/usr/bin/env python3
#
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
import optparse
import os
import shutil
from subprocess import PIPE, Popen

VERSION = '0.1'


def search_for_check_esx3():
    """Search for the check_esx3.pl file."""
    my_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(my_dir, 'check_esx3.pl'),
        '/var/lib/nagios/check_esx3.pl',
        '/var/lib/plugins/nagios/check_esx3.pl',
        '/var/lib/shinken/check_esx3.pl',
        '/usr/local/nagios/libexec/check_esx3.pl',
        '/usr/local/shinken/libexec/check_esx3.pl',
        r'c:\shinken\libexec\check_esx3.pl',
    ]
    for path in possible_paths:
        print('Look for', path)
        if os.path.exists(path):
            print('Found a check_esx3.pl at', path)
            return path
    return None


def _split_rules(rules):
    return [rule.strip() for rule in rules.split('|') if rule.strip()]


def _apply_rules(name, rules):
    if 'nofqdn' in rules:
        name = name.split('.', 1)[0]
    if 'lower' in rules:
        name = name.lower()
    return name


def _run(command, *, stderr=PIPE):
    process = Popen(command, stdout=PIPE, stderr=stderr, text=True)
    output = process.communicate()
    if process.returncode == 2:
        print('Error: check_esx3.pl returned an error:', output)
        raise SystemExit(2)
    return process, output


def get_vmware_hosts(check_esx_path, vcenter, user, password):
    list_host_cmd = [
        check_esx_path, '-D', vcenter, '-u', user, '-p', password,
        '-l', 'runtime', '-s', 'listhost',
    ]
    print('Got host list')
    print(' '.join(list_host_cmd))
    process, output = _run(list_host_cmd)
    print('Exit status', process.returncode)

    parts = output[0].split(':')
    if len(parts) < 2:
        return []
    hosts_raw = parts[1].split('|')[0]
    return [entry.strip().split('(')[0] for entry in hosts_raw.split(',') if entry.strip()]


def get_vm_of_host(check_esx_path, vcenter, host, user, password):
    print('Listing host', host)
    list_vm_cmd = [
        check_esx_path, '-D', vcenter, '-H', host,
        '-u', user, '-p', password,
        '-l', 'runtime', '-s', 'list',
    ]
    print(' '.join(list_vm_cmd))
    process, output = _run(list_vm_cmd, stderr=None)
    print('Exit status', process.returncode)

    parts = output[0].split(':')
    if len(parts) < 2:
        return None
    vms_raw = parts[1].split('|')[0]
    return [entry.strip().split('(')[0] for entry in vms_raw.split(',') if entry.strip()]


def print_all_links(result, rules):
    links = []
    for host, vms in result.items():
        host_name = _apply_rules(host, rules)
        print('%s::esxhostname=%s' % (host_name, host_name))
        print('%s::isesxhost=1' % host_name)
        for vm in vms:
            vm_name = _apply_rules(vm, rules)
            print('%s::vmname=%s' % (vm_name, vm_name))
            print('%s::isesxvm=1' % vm_name)
            print('%s::esxhost=%s' % (vm_name, host_name))
    return links


def write_output(result, path):
    try:
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as output_file:
            json.dump(result, output_file)
        shutil.move(tmp_path, path)
        print('File %s written' % path)
    except OSError as exp:
        raise SystemExit('Error writing the file %s: %s' % (path, exp))


def main(check_esx_path, vcenter, user, password, rules):
    rules = _split_rules(rules)
    result = {}
    hosts = get_vmware_hosts(check_esx_path, vcenter, user, password)
    for host in hosts:
        vms = get_vm_of_host(check_esx_path, vcenter, host, user, password)
        if vms:
            result[host] = vms
    print_all_links(result, rules)
    print('Finished!')


if __name__ == '__main__':
    parser = optparse.OptionParser(
        version='Shinken VMware links dumping script version %s' % VERSION,
    )
    parser.add_option('-x', '--esx3-path', dest='check_esx_path',
                      help='Full path of the check_esx3.pl script (default: %default)')
    parser.add_option('-V', '--vcenter', '--Vcenter',
                      help='The IP/DNS address of your Vcenter host.')
    parser.add_option('-u', '--user', help='User name to connect to this Vcenter')
    parser.add_option('-p', '--password', help='The password of this user')
    parser.add_option(
        '-r', '--rules', default='',
        help=('Rules of name transformation. Valid names are: '
              '`lower`: to lower names, `nofqdn`: keep only the first name. '
              'You can use several rules like `lower|nofqdn`'),
    )

    opts, args = parser.parse_args()
    if args:
        parser.error('does not take any positional arguments')
    if opts.vcenter is None:
        parser.error('missing -V or --Vcenter option for the vcenter IP/DNS address')
    if opts.user is None:
        parser.error('missing -u or --user option for the vcenter username')
    if opts.password is None:
        parser.error('missing -p or --password option for the vcenter password')
    if opts.check_esx_path is None:
        opts.check_esx_path = search_for_check_esx3()
        if opts.check_esx_path is None:
            parser.error('Sorry, I cannot find check_esx3.pl, please specify it with -x')
    elif not os.path.exists(opts.check_esx_path):
        parser.error('the path %s for the check_esx3.pl script is wrong, missing file' % opts.check_esx_path)

    main(**opts.__dict__)
