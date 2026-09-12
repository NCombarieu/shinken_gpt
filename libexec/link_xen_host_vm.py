#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# /usr/local/shinken/libexec/link_xen_host_vm.py
# This file is proposed for Shinken to link vm and xenserver.
# Devers Renaud rdevers@chavers.org
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
import shutil
import sys

import XenAPI

VERSION = '0.1'


def _split_rules(rules):
    return [r.strip() for r in rules.split('|')]


def _apply_rules(name, rules):
    if 'nofqdn' in rules:
        name = name.split(' ', 1)[0]
        name = name.split('.', 1)[0]
    if 'lower' in rules:
        name = name.lower()
    return name


def create_all_links(res, rules):
    links = []
    for host, vms in res.items():
        for vm in vms:
            host_name = _apply_rules(host, rules)
            vm_name = _apply_rules(vm, rules)
            links.append((('host', host_name), ('host', vm_name)))
    return links


def write_output(path, links):
    try:
        with open(path + '.tmp', 'w', encoding='utf-8') as handle:
            json.dump(links, handle)
        shutil.move(path + '.tmp', path)
        print("File %s wrote" % path)
    except OSError as exp:
        sys.exit("Error writing the file %s: %s" % (path, exp))


def con_poolmaster(xs, user, password):
    try:
        session = XenAPI.Session("http://%s" % xs)
        session.xenapi.login_with_password(user, password)
        return session
    except XenAPI.Failure as exc:
        if exc.details[0] == "HOST_IS_SLAVE":
            host = exc.details[1]
            session = XenAPI.Session("http://%s" % host)
            session.xenapi.login_with_password(user, password)
            return session
        print("Error: pool con:", xs, exc)
    except Exception as exc:
        print("Error: pool con:", xs, exc)
    return None


def main(output, user, password, rules, xenserver):
    res = {}
    for xs in xenserver:
        session = None
        try:
            session = con_poolmaster(xs, user, password)
            if session is None:
                continue
            for vm in session.xenapi.VM.get_all():
                record = session.xenapi.VM.get_record(vm)
                if record["is_a_template"] or record["is_control_domain"]:
                    continue
                vhost = session.xenapi.VM.get_resident_on(vm)
                if vhost == "OpaqueRef:NULL":
                    continue
                host = session.xenapi.host.get_hostname(vhost)
                vm_name = session.xenapi.VM.get_name_label(vm)
                res.setdefault(host, []).append(vm_name)
        except Exception as exc:
            print("Error querying XenServer %s: %s" % (xs, exc))
        finally:
            if session is not None:
                try:
                    session.xenapi.session.logout()
                except Exception:
                    pass

    links = create_all_links(res, _split_rules(rules))
    print("Created %d links" % len(links))
    write_output(output, links)
    print("Finished!")


if __name__ == "__main__":
    parser = optparse.OptionParser(
        version="Shinken XenServer/XCP links dumping script version %s" % VERSION)
    parser.add_option("-o", "--output",
                      default='/tmp/xen_mapping_file.json',
                      help="Path of the generated mapping file.")
    parser.add_option("-u", "--user",
                      help="User name to connect to this XenServer pool")
    parser.add_option("-p", "--password",
                      help="The password of this user")
    parser.add_option('-r', '--rules', default='',
                      help="Rules of name transformation. Valid names are: "
                      "`lower`: to lower names, "
                      "`nofqdn`: keep only the first name (server.mydomain.com -> server)."
                      "You can use several rules like `lower|nofqdn`")
    parser.add_option('-x', '--xenserver', action="append",
                      help="multiple ip/fqdn of your XenServer/XCP pool master (or member). "
                      "ex: -x poolmaster1 -x poolmaster2 -x poolmaster3")

    opts, args = parser.parse_args()
    if args:
        parser.error("does not take any positional arguments")
    if opts.user is None:
        parser.error("missing -u or --user option for the pool master username")
    if opts.password is None:
        parser.error("missing -p or --password option for the pool master password")
    if opts.output is None:
        parser.error("missing -o or --output option for the output mapping file")
    if opts.xenserver is None:
        parser.error("missing -x or --xenserver option for pool master list")

    main(**opts.__dict__)
