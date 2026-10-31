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

"""Encoding of the configuration files.

Shinken 2.4 (Python 2) accepted latin-1 configuration files. They must
still load (with a warning naming the file), UTF-8 files must be decoded
as UTF-8, and an unreadable file must be reported with its name.
"""

import os
import shutil
import tempfile
import unittest

import shinken_test  # noqa: F401  (sets up sys.path)
from shinken.log import logger
from shinken.objects.config import Config
from shinken.util import read_text_file


class TestConfigEncoding(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.messages = []
        orig_warning, orig_error = logger.warning, logger.error

        def capture(orig):
            def wrapper(msg, *args, **kwargs):
                self.messages.append(msg % args if args else msg)
                return orig(msg, *args, **kwargs)
            return wrapper
        logger.warning = capture(orig_warning)
        logger.error = capture(orig_error)
        self.addCleanup(setattr, logger, 'warning', orig_warning)
        self.addCleanup(setattr, logger, 'error', orig_error)
        self.addCleanup(shutil.rmtree, self.tmp)

    def _write(self, rel, data):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fd:
            fd.write(data)
        return path

    def test_read_text_file(self):
        utf8 = self._write('a.cfg', 'alias Serveur dédié\r\n'.encode('utf-8'))
        latin = self._write('b.cfg', 'alias Serveur dédié\n'.encode('latin-1'))
        bom = self._write('c.cfg', b'\xef\xbb\xbfalias x\n')
        self.assertEqual('alias Serveur dédié\n', read_text_file(utf8))
        self.assertEqual('alias Serveur dédié\n', read_text_file(latin))
        self.assertEqual('alias x\n', read_text_file(bom))
        self.assertTrue(any(latin in m for m in self.messages))
        self.assertFalse(any(utf8 in m for m in self.messages))

    def test_latin1_files_are_accepted(self):
        main = self._write('shinken.cfg', (
            'cfg_file=objects/one.cfg\n'
            'cfg_dir=dir\n').encode('ascii'))
        self._write('objects/one.cfg', (
            'define host {\n  host_name h1\n  alias Hôte numéro 1\n}\n').encode('latin-1'))
        dir_file = self._write('dir/two.cfg', (
            'define host {\n  host_name h2\n  alias Serveur dédié\n}\n').encode('latin-1'))
        conf = Config()
        buf = conf.read_config([main])
        self.assertTrue(getattr(conf, 'conf_is_correct', True))
        self.assertIn('Hôte numéro 1', buf)
        self.assertIn('Serveur dédié', buf)
        self.assertTrue(any(dir_file in m for m in self.messages))
        raw = conf.read_config_buf(buf)
        aliases = sorted(h['alias'][0] for h in raw['host'])
        self.assertEqual(['Hôte numéro 1', 'Serveur dédié'], aliases)

    def test_pack_files_are_loaded(self):
        # Packs were opened with the 'rU' mode, removed in Python 3.11
        from shinken.objects.pack import Packs
        self._write('packs/linux/linux.pack',
                    '{"name": "linux", "description": "Serveur Linux"}\n'.encode('utf-8'))
        packs = Packs([])
        packs.load_file(os.path.join(self.tmp, 'packs'))
        self.assertEqual(['linux'], [p.pack_name for p in packs])

    def test_unreadable_file_is_named(self):
        missing = os.path.join(self.tmp, 'objects', 'missing.cfg')
        main = self._write('shinken.cfg', ('cfg_file=%s\n' % missing).encode('ascii'))
        conf = Config()
        conf.read_config([main])
        self.assertFalse(conf.conf_is_correct)
        self.assertTrue(any(missing in m for m in self.messages))


if __name__ == '__main__':
    unittest.main()
