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

"""Reading external commands from the nagios.cmd named pipe."""

import os
import shutil
import stat
import tempfile
import unittest

import shinken_test  # noqa: F401  (sets up sys.path)
from shinken.external_command import ExternalCommand, ExternalCommandManager


@unittest.skipUnless(hasattr(os, 'mkfifo'), 'named pipes are POSIX only')
class TestExternalCommandPipe(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, 'nagios.cmd')
        self.ecm = ExternalCommandManager(None, 'applyer')
        self.ecm.pipe_path = self.path
        self.writer = None

    def tearDown(self):
        if self.writer is not None:
            os.close(self.writer)
        if isinstance(self.ecm.fifo, int):
            try:
                os.close(self.ecm.fifo)
            except OSError:
                pass

    def _open(self):
        fd = self.ecm.open()
        self.assertIsNotNone(fd)
        self.writer = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        return fd

    def test_pipe_is_created_with_expected_mode(self):
        with open(self.path, 'w') as f:  # stale regular file is replaced
            f.write('x')
        self._open()
        st = os.stat(self.path)
        self.assertTrue(stat.S_ISFIFO(st.st_mode))
        self.assertEqual(0o660, stat.S_IMODE(st.st_mode))

    def test_commands_are_read_as_text(self):
        self._open()
        self.assertEqual([], self.ecm.get())  # nothing written yet
        os.write(self.writer, '[1700000000] ADD_HOST_COMMENT;srv;1;admin;été\n'
                              '[1700000001] DISABLE_HOST_CHECK;srv\r\n\n'.encode('utf-8'))
        cmds = self.ecm.get()
        self.assertTrue(all(isinstance(c, ExternalCommand) for c in cmds))
        self.assertEqual(['[1700000000] ADD_HOST_COMMENT;srv;1;admin;été',
                          '[1700000001] DISABLE_HOST_CHECK;srv'],
                         [c.cmd_line for c in cmds])
        # Invalid UTF-8 is replaced, not fatal
        os.write(self.writer, b'[1700000002] ADD_HOST_COMMENT;srv;1;admin;\xe9t\xe9\n')
        self.assertEqual(['[1700000002] ADD_HOST_COMMENT;srv;1;admin;�t�'],
                         [c.cmd_line for c in self.ecm.get()])

    def test_command_split_by_a_full_read(self):
        self._open()
        size = ExternalCommandManager.PIPE_READ_SIZE
        first = b'[1700000000] DISABLE_HOST_CHECK;' + b'a' * (size - 40) + b'\n'
        second = b'[1700000001] ENABLE_HOST_CHECK;srv-split\n'
        data = first + second
        os.write(self.writer, data)
        cmds = self.ecm.get() + self.ecm.get()
        self.assertEqual([first[:-1].decode(), second[:-1].decode()],
                         [c.cmd_line for c in cmds])

    def test_reopen_after_writer_closed(self):
        self._open()
        os.write(self.writer, b'[1700000000] DISABLE_HOST_CHECK;srv\n')
        os.close(self.writer)
        self.writer = None
        self.assertEqual(1, len(self.ecm.get()))
        self.assertEqual([], self.ecm.get())  # EOF: descriptor closed
        self._open()  # re-open, the FIFO is kept
        os.write(self.writer, b'[1700000001] ENABLE_HOST_CHECK;srv\n')
        self.assertEqual(['[1700000001] ENABLE_HOST_CHECK;srv'],
                         [c.cmd_line for c in self.ecm.get()])

    def test_creation_error_is_logged_not_raised(self):
        self.ecm.pipe_path = os.path.join(self.tmp, 'missing-dir', 'nagios.cmd')
        self.assertIsNone(self.ecm.open())


if __name__ == '__main__':
    unittest.main()
