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

"""The bin/shinken-<daemon> launchers run from a source checkout.

They must find the ``shinken`` package of the checkout without
``pip install``, whatever the current directory.
"""

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAEMONS = ('arbiter', 'broker', 'poller', 'reactionner', 'receiver', 'scheduler')


class TestBinLaunchers(unittest.TestCase):

    def _run(self, script):
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        # Run from an unrelated directory without PYTHONPATH: unless shinken
        # is installed in this interpreter, the launcher must bootstrap
        # sys.path itself.
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, script, '--version'],
                                  capture_output=True, cwd=cwd, env=env, timeout=120)

    def test_launchers_run_from_checkout(self):
        for daemon in DAEMONS:
            for name in ('shinken-%s' % daemon, 'shinken-%s.py' % daemon):
                path = os.path.join(ROOT, 'bin', name)
                if not os.path.exists(path):
                    continue
                p = self._run(path)
                out = (p.stdout + p.stderr).decode('utf-8', 'replace')
                self.assertEqual(0, p.returncode, '%s: %s' % (name, out))
                self.assertNotIn('ModuleNotFoundError', out)


if __name__ == '__main__':
    unittest.main()
