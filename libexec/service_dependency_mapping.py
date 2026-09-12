#!/usr/bin/env python3
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
Build a service-dependency mapping from a running arbiter and pack config.
"""

import json
import optparse
import shutil
import sys

from shinken.objects.arbiterlink import ArbiterLink
from shinken.objects.config import Config


VERSION = '0.2'


class ShinkenAdmin:

    def __init__(self):
        self.arb = None
        self.conf = None
        self.addr = 'localhost'
        self.port = '7770'
        self.arb_name = 'arbiter-master'

    def do_connect(self, verbose=False):
        """Connect to an arbiter daemon."""
        if verbose:
            print("Connection to %s:%s" % (self.addr, self.port))
        ArbiterLink.use_ssl = False
        self.arb = ArbiterLink({
            'arbiter_name': self.arb_name,
            'address': self.addr,
            'port': self.port,
        })
        self.arb.fill_default()
        self.arb.pythonize()
        self.arb.update_infos()
        if not self.arb.reachable:
            sys.exit("Connection to the arbiter got a problem")
        print("Connection OK")

    def getconf(self, config):
        """Get hosts and service dependencies from the arbiter/config."""
        conf = Config()
        conf.read_config_silent = 1

        properties = ['host_name', 'use', 'act_depend_of']
        hosts = self.arb.get_objects_properties('hosts', properties)

        svcdep_buf = conf.read_config([config])
        svc_dep = conf.read_config_buf(svcdep_buf)['servicedependency']
        return hosts, svc_dep

    def load_svc_mapping(self, hosts, svc_dep, verbose=False):
        """Build tuples representing service dependencies."""
        result = []
        for dep in svc_dep:
            parent_host_name = self.split_and_merge(dep['host_name'])
            try:
                dependent_host_name = self.split_and_merge(
                    dep['dependent_host_name']
                )
            except KeyError:
                dependent_host_name = parent_host_name

            if verbose:
                print()
                print('Service dependency host_name', parent_host_name)
                print(
                    'Service dependency dependent_host_name',
                    dependent_host_name,
                )

            dep['service_description'] = self.split_and_merge(
                dep['service_description']
            )
            dep['dependent_service_description'] = self.split_and_merge(
                dep['dependent_service_description']
            )

            parent_svc_tuples = []
            dependent_svc_tuples = []
            for parent_svc in dep['service_description']:
                parent_svc_tuples += [
                    [
                        ('service', host[0] + "," + parent_svc)
                        for host in hosts
                        if host_name in host[1]
                    ]
                    for host_name in parent_host_name
                ]
            for dependent_svc in dep['dependent_service_description']:
                dependent_svc_tuples += [
                    [
                        ('service', host[0] + "," + dependent_svc)
                        for host in hosts
                        if host_name in host[1]
                    ]
                    for host_name in dependent_host_name
                ]

            dependent_tuples = self.split_and_merge(
                dependent_svc_tuples, split=False
            )

            if verbose:
                print(
                    'Parent service dependencies tuples list',
                    parent_svc_tuples,
                )
                print(
                    'Dependent service dependencies tuples list',
                    dependent_svc_tuples,
                )

            for parent_tuples in parent_svc_tuples:
                result.append(
                    self.make_all_dep_tuples(
                        hosts, parent_tuples, dependent_tuples
                    )
                )

        if verbose:
            print()
            print("Result:", result)
        return result

    def make_all_dep_tuples(
        self, hosts, parent_tuples=None, dependent_tuples=None
    ):
        """Build all dependency tuples for the supplied parent/dependents."""
        if parent_tuples is None:
            parent_tuples = [()]
        if dependent_tuples is None:
            dependent_tuples = [[()]]

        result = []
        for parent_tuple in parent_tuples:
            parent = {
                'host_name': self.get_dependency_tuple_host_name(parent_tuple),
                'svc_desc': self.get_dependency_tuple_service_description(
                    parent_tuple
                ),
            }
            for dependent_tuple in dependent_tuples:
                dependent = {
                    'host_name': self.get_dependency_tuple_host_name(
                        dependent_tuple
                    ),
                    'svc_desc': self.get_dependency_tuple_service_description(
                        dependent_tuple
                    ),
                }
                dependent['host_object'] = next(
                    host for host in hosts
                    if host[0] == dependent['host_name']
                )
                result = self.make_dep_tuple(
                    parent,
                    dependent,
                    parent_tuple,
                    dependent_tuple,
                    result,
                )
        return result

    def make_dep_tuple(
        self, parent, dependent, parent_tuple, dependent_tuple, result
    ):
        """Match a host dependency and return its service tuple."""
        try:
            dependent_host_parent = self.get_host_dependency(
                dependent['host_object']
            )
            if parent['host_name'] == dependent_host_parent:
                result = (parent_tuple, dependent_tuple)
        except IndexError:
            if parent['host_name'] == dependent['host_name']:
                result = (parent_tuple, dependent_tuple)
        return result

    def get_host_dependency(self, dependent_host):
        """Return the parent host name from a host dependency."""
        return dependent_host[2][0][0].host_name

    def get_dependency_tuple_host_name(self, dependency_tuple):
        """Return the host-name part of a dependency tuple."""
        return dependency_tuple[1].split(',')[0]

    def get_dependency_tuple_service_description(self, dependency_tuple):
        """Return the service-description part of a dependency tuple."""
        return dependency_tuple[1].split(',')[1]

    def split_and_merge(self, values, split=True):
        """Split comma-separated values and flatten the result."""
        result = []
        for value in values:
            if split:
                result += value.split(',')
            else:
                result += value
        return result

    def clean_empty_value(self, result):
        """Drop empty mappings produced by unused config packs."""
        return [value for value in result if value != []]

    def main(self, output_file, config, verbose):
        self.do_connect(verbose)

        hosts, svc_dep = self.getconf(config)
        if verbose:
            print("Hosts:", hosts)
            print("Service Dep:", svc_dep)

        result = self.load_svc_mapping(hosts, svc_dep, verbose)
        result = self.clean_empty_value(result)

        temp_file = output_file + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as stream:
                json.dump(result, stream)
            shutil.move(temp_file, output_file)
            print("File %s written" % output_file)
        except OSError as exp:
            sys.exit("Error writing the file %s: %s" % (output_file, exp))


if __name__ == "__main__":
    parser = optparse.OptionParser(
        version=(
            "Shinken service hot dependency according to packs (or custom) "
            "definition to json mapping %s" % VERSION
        )
    )
    parser.add_option(
        "-o",
        "--output",
        dest='output_file',
        default='/tmp/shinken_service_dependency:mapping.json',
        help="Path of the generated json mapping file.",
    )
    parser.add_option(
        '-c', '--config', dest='config', help='Shinken main config file.'
    )
    parser.add_option(
        '-v',
        '--verbose',
        action='store_true',
        dest='verbose',
        help='More verbosity. Used to debug',
    )

    opts, args = parser.parse_args()
    if args:
        parser.error("does not take any positional arguments")

    ShinkenAdmin().main(**vars(opts))
