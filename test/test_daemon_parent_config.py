#!/usr/bin/env python
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

"""Graceful reload: the new daemon reads its configuration on stdin.

The parent writes a binary pickle; it must be read as bytes.
"""

import io
import pickle
import sys
import unittest

import shinken_test  # noqa: F401  (sets up sys.path)
from shinken.daemon import Daemon


class TestDaemonParentConfig(unittest.TestCase):

    def test_binary_pickle_is_read_from_stdin(self):
        conf = {'a': [1, 'é', b'\x80\xff'], 'b': set([1, 2])}
        payload = pickle.dumps(conf, pickle.HIGHEST_PROTOCOL)
        stdin = io.TextIOWrapper(io.BytesIO(payload), encoding='utf-8')

        daemon = Daemon.__new__(Daemon)
        daemon.is_switched_process = lambda: True
        daemon.wait_parent_exit = lambda: None
        daemon.new_conf = None

        saved = sys.stdin
        sys.stdin = stdin
        try:
            daemon.load_parent_config()
        finally:
            sys.stdin = saved
        self.assertEqual(conf, daemon.new_conf)


if __name__ == '__main__':
    unittest.main()
