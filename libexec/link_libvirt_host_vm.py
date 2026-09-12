#!/usr/bin/env python3
# Copyright (C) 2012:
#    Thibault Cohen, thibault.cohen@savoirfairelinux.com
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

"""
This program uses libvirt to put host parent-child relations in a JSON file so it
can be loaded in hot_dependencies_arbiter module.
"""

import json
import optparse
import signal
import sys

import libvirt


class TimeoutException(Exception):
    pass


VERSION = '0.1'


def main(uris, output_file, ignore):
    def timeout_handler(signum, frame):
        raise TimeoutException()

    ignored_doms = ignore.split(",") if ignore else []
    relationships = []

    for uri in uris.split(","):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)
        try:
            conn = libvirt.openReadOnly(uri)
        except libvirt.libvirtError as exc:
            print("Libvirt connection error: `%s'" % str(exc).replace("\r", ""))
            print("Let's try next URI")
            continue
        except TimeoutException:
            print("Libvirt request timeout")
            print("Let's try next URI")
            continue
        except Exception as exc:
            print("Unknown error: %s" % exc)
            print("Let's try next URI...")
            continue
        finally:
            signal.alarm(0)

        hypervisor = conn.getHostname()
        # List all VM (stopped and started)
        domains = ([conn.lookupByName(name) for name in conn.listDefinedDomains()] +
                   [conn.lookupByID(vmid) for vmid in conn.listDomainsID()])
        for dom in domains:
            domain_name = dom.name()
            if domain_name in ignored_doms:
                continue
            relationships.append((('host', hypervisor.strip()),
                                  ('host', domain_name.strip())))

        conn.close()

    with open(output_file, 'w', encoding='utf-8') as jsonmappingfile:
        json.dump(list(set(relationships)), jsonmappingfile)


if __name__ == "__main__":
    parser = optparse.OptionParser(
        version="Shinken libvirt mapping to json mapping %s" % VERSION)
    parser.add_option("-o", "--output", dest='output_file',
                      default='/tmp/libvirt_mapping_file.json',
                      help="Path of the generated json mapping file.\n"
                      "Default: /tmp/libvirt_mapping_file.json")
    parser.add_option("-u", "--uris", dest='uris',
                      help="Libvirt URIs separated by comma")
    parser.add_option("-i", "--ignore", dest='ignore',
                      default=None,
                      help="Ignore hosts (separated by comma)\n"
                           "Default: None")

    opts, args = parser.parse_args()
    if args:
        parser.error("does not take any positional arguments")

    if opts.uris is None:
        print("At least one URI is mandatory")
        sys.exit(2)

    main(**vars(opts))
