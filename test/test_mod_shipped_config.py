#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""The daemons and modules shipped in etc/ only use modules that exist."""

import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(REPO, 'modules')
ETC = os.path.join(REPO, 'etc')
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from shinken.modulesmanager import ModulesManager  # noqa: E402
from shinken.objects.config import Config  # noqa: E402

DAEMON_DIRS = ('arbiters', 'schedulers', 'brokers', 'receivers', 'pollers', 'reactionners')
DAEMON_TYPES = {'arbiter': 'arbiter', 'scheduler': 'scheduler', 'broker': 'broker',
                'receiver': 'receiver', 'poller': 'poller', 'reactionner': 'reactionner'}


def modules_of(raw):
    value = raw.get('modules', [''])
    if isinstance(value, list):
        value = ','.join(value)
    return [name.strip() for name in value.split(',') if name.strip()]


class TestShippedModulesConfig(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        cfg = os.path.join(self.tmpdir, 'shinken.cfg')
        with open(cfg, 'w') as handle:
            for directory in DAEMON_DIRS + ('modules',):
                handle.write('cfg_dir=%s\n' % os.path.join(ETC, directory))
        conf = Config()
        self.raw = conf.read_config_buf(conf.read_config([cfg]))
        self.modules = dict((m['module_name'][0], m) for m in self.raw['module'])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def module_type_exists(self, module_type, daemon_type):
        manager = ModulesManager(daemon_type, MODULES_DIR, [])
        manager.load()
        wanted = module_type.replace('_', '-')
        return any(m.properties['type'].replace('_', '-') == wanted
                   for m in manager.imported_modules)

    def test_every_referenced_module_exists(self):
        checked = 0
        for daemon_type in DAEMON_TYPES:
            for daemon in self.raw.get(daemon_type, []):
                for name in modules_of(daemon):
                    self.assertIn(name, self.modules,
                                  '%s uses undefined module %s' % (daemon_type, name))
                    module_type = self.modules[name]['module_type'][0]
                    self.assertTrue(self.module_type_exists(module_type, daemon_type),
                                    'no %s module of type %s' % (daemon_type, module_type))
                    checked += 1
        self.assertGreaterEqual(checked, 3)

    def test_livestatus_submodules_exist(self):
        for name in modules_of(self.modules['livestatus']):
            module_type = self.modules[name]['module_type'][0]
            self.assertTrue(self.module_type_exists(module_type, 'livestatus'), name)

    def test_defaults(self):
        scheduler = self.raw['scheduler'][0]
        self.assertEqual(['retention-pickle'], modules_of(scheduler))
        self.assertEqual(['logstore-sqlite'], modules_of(self.modules['livestatus']))
        self.assertEqual('pickle_retention_file',
                         self.modules['retention-pickle']['module_type'][0])
        self.assertEqual('named_pipe', self.modules['named-pipe']['module_type'][0])
        self.assertTrue(self.module_type_exists('named_pipe', 'arbiter'))


if __name__ == '__main__':
    unittest.main()
