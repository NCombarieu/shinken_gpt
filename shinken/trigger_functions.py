#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2014:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
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

import time
import re

from shinken.misc.perfdata import PerfDatas
from shinken.log import logger

objs = {'hosts': [], 'services': []}
trigger_functions = {}


class declared(object):
    """Decorator to add a function to the trigger environment."""
    def __init__(self, f):
        self.f = f
        n = getattr(f, '__name__', 'no name')
        trigger_functions[n] = f

    def __call__(self, *args):
        logger.debug("Calling %s with arguments %s", self.f.__name__, args)
        return self.f(*args)

@declared
def up(obj, output):
    set_value(obj, output, None, 0)

@declared
def down(obj, output):
    set_value(obj, output, None, 1)

@declared
def ok(obj, output):
    set_value(obj, output, None, 0)

@declared
def warning(obj, output):
    set_value(obj, output, None, 1)

@declared
def critical(obj, output):
    set_value(obj, output, None, 2)

@declared
def unknown(obj, output):
    set_value(obj, output, None, 3)

@declared
def set_value(obj_ref, output=None, perfdata=None, return_code=None):
    obj = get_object(obj_ref)
    if not obj:
        return
    output = output or obj.output
    perfdata = perfdata or obj.perf_data
    if return_code is None:
        return_code = obj.state_id
    logger.debug("[trigger] Setting %s %s %s for object %s", output, perfdata, return_code, obj.get_full_name())
    if perfdata:
        output = output + ' | ' + perfdata
    now = time.time()
    check_id = obj.launch_check(now, force=True)
    for check in obj.checks_in_progress:
        if check.id == check_id:
            check.exit_status = return_code
            check.get_outputs(output, obj.max_plugins_output_length)
            check.status = 'waitconsume'
            check.check_time = now
            check.from_trigger = True

@declared
def perf(obj_ref, metric_name):
    obj = get_object(obj_ref)
    p = PerfDatas(obj.perf_data)
    if metric_name in p:
        return p[metric_name].value
    return None

@declared
def get_custom(obj_ref, cname, default=None):
    obj = get_objects(obj_ref)
    if not obj:
        return default
    cname = cname.upper().strip()
    if not cname.startswith('_'):
        cname = '_' + cname
    return obj.customs.get(cname, default)

@declared
def perfs(objs_ref, metric_name):
    return [perf(obj, metric_name) for obj in get_objects(objs_ref)]

@declared
def allperfs(obj_ref):
    obj = get_object(obj_ref)
    p = PerfDatas(obj.perf_data)
    return {metric.name: p[metric.name] for metric in p}

@declared
def get_object(ref):
    if not isinstance(ref, str):
        return ref
    if '/' not in ref:
        return objs['hosts'].find_by_name(ref)
    host_name, service_name = ref.split('/', 1)
    return objs['services'].find_srv_by_name_and_hostname(host_name, service_name)

@declared
def get_objects(ref):
    if not isinstance(ref, str):
        return ref
    if '*' not in ref:
        return get_object(ref)

    hname = ''
    sdesc = ''
    if '/' not in ref:
        hname = ref
    else:
        hname, sdesc = ref.split('/', 1)
    logger.debug("[trigger get_objects] Look for %s %s", hname, sdesc)
    hosts = []
    services = []

    if '*' not in hname:
        host = objs['hosts'].find_by_name(hname)
        if host:
            hosts.append(host)
    else:
        pattern = re.compile(hname.replace('*', '.*'))
        for host in objs['hosts']:
            if pattern.search(host.get_name()):
                hosts.append(host)

    if not sdesc:
        return hosts

    for host in hosts:
        if '*' not in sdesc:
            service = host.find_service_by_name(sdesc)
            if service:
                services.append(service)
        else:
            pattern = re.compile(sdesc.replace('*', '.*'))
            for service in host.services:
                if pattern.search(service.service_description):
                    services.append(service)
    return services
