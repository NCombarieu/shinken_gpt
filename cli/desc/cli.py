#!/usr/bin/env python3

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

import os
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

from shinken.log import logger
from shinken.objects import Host

# Will be populated by the shinken CLI command
CONFIG = None


def serve(port):
    port = int(port)
    logger.info("Serving documentation at port %s", port)
    doc_dir = CONFIG['paths']['doc']
    html_dir = os.path.join(doc_dir, 'build', 'html')
    os.chdir(html_dir)
    try:
        with TCPServer(("", port), SimpleHTTPRequestHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as exp:
        logger.error(exp)


def do_desc(cls='host'):
    del cls
    properties = Host.properties
    for name in sorted(properties):
        prop = properties[name]
        if prop.has_default:
            print(name, '(%s)' % prop.default)
        else:
            print(name)


exports = {
    do_desc: {
        'keywords': ['desc'],
        'args': [
            {'name': '--cls', 'default': 'host', 'description': 'Object type to describe'},
        ],
        'description': 'List this object type properties'
    },
}
