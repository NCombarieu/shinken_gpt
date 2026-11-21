# -*- coding: utf-8 ; mode: python -*-
#
# Copyright (C) 2012:
#    Hartmut Goebel <h.goebel@crazy-compilers.com>
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

Helper module for importing the shinken library from the (uninstalled)
test-suite.

If importing shinken fails, try to load from parent directory to
support running the test-suite without installation.

This does not manipulate sys.path, but uses lower-level Python modules
for looking up and loading the module `shinken` from the directory one
level above this module.
"""

from __future__ import absolute_import
import os
import sys
import importlib.util

try:
    import shinken
except ImportError:
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent_dir)
    try:
        spec = importlib.util.find_spec('shinken')
        if spec is None:
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules['shinken'] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

