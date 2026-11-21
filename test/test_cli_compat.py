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

"""The optparse compatibility layer renders optparse help texts."""

import unittest

import shinken_test  # noqa: F401  (sets up sys.path)
from shinken.cli_compat import optparse


class TestCliCompat(unittest.TestCase):

    def test_help_placeholders(self):
        parser = optparse.OptionParser("%prog [options]", version="%prog 1.0")
        parser.add_option('-w', '--warning', dest='warning', default=80, type='int',
                          help='Warning threshold in %, default: %default')
        parser.add_option('-n', dest='name', help='Name used by %prog')
        text = parser.format_help()
        self.assertIn('Warning threshold in %, default: 80', text)
        self.assertNotIn('%default', text)
        self.assertNotIn('%prog', text)
        opts, args = parser.parse_args(['-w', '90', 'extra'])
        self.assertEqual(90, opts.warning)
        self.assertEqual(['extra'], args)


if __name__ == '__main__':
    unittest.main()
