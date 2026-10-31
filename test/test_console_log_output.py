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

"""Console output of the daemons logs.

Each log line must be printed once (not on both stdout and stderr) and as
text (never as a ``b'...'`` bytes representation).
"""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = r'''
import logging, sys
from shinken.structured_logging import setup_logging
from shinken.log import logger
setup_logging('shinken-test', level='WARNING', json_format=%(json)s)
logger.setLevel('INFO')
logger.info('hello-info %(accent)s')
logging.getLogger('thirdparty').warning('third-party-warning')
'''


def run(json_format):
    env = dict(os.environ)
    env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
    env['PYTHONIOENCODING'] = 'utf-8'
    env.pop('ANSI_COLORS_DISABLED', None)
    code = SCRIPT % {'json': json_format, 'accent': 'été'}
    p = subprocess.run([sys.executable, '-c', code], capture_output=True,
                       env=env, cwd=ROOT, timeout=60)
    return p.stdout.decode('utf-8'), p.stderr.decode('utf-8')


class TestConsoleLogOutput(unittest.TestCase):

    def test_human_output_once_and_as_text(self):
        out, err = run(False)
        lines = [l for l in (out + err).splitlines() if 'hello-info' in l]
        self.assertEqual(1, len(lines), (out, err))
        line = lines[0]
        self.assertIn('hello-info été', line)
        self.assertNotIn("b'", line)
        # Not a terminal: no ANSI escape codes
        self.assertNotIn('\x1b[', line)
        self.assertIn('INFO: [Shinken] hello-info', out)
        # Other libraries still log through the root handler
        self.assertEqual(1, err.count('third-party-warning'), err)

    def test_json_output_once(self):
        out, err = run(True)
        lines = [l for l in (out + err).splitlines() if 'hello-info' in l]
        self.assertEqual(1, len(lines), (out, err))
        entry = json.loads(lines[0])
        self.assertEqual('hello-info été', entry['message'])
        self.assertEqual('Shinken', entry['logger'])


if __name__ == '__main__':
    unittest.main()
