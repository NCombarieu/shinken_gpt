#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests of the named-pipe (nagios.cmd) module."""

import os
import queue
import shutil
import stat
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(REPO, 'modules')
if REPO not in sys.path:
    sys.path.insert(0, REPO)
if MODULES_DIR not in sys.path:
    sys.path.append(MODULES_DIR)

from shinken.external_command import ExternalCommand  # noqa: E402
from shinken.modulesmanager import ModulesManager  # noqa: E402
from shinken.objects.config import Config  # noqa: E402
from shinken.objects.module import Module  # noqa: E402

import named_pipe.module as pipe_mod  # noqa: E402


def real_time():
    """The legacy test helpers (shinken_test.TimeHacker) fake time.time()
    and time.sleep() process-wide; external processes need the real clock.
    Switch every loaded hacker to real time and return them."""
    hackers = []
    # Restore in reverse import order: a later hacker saved the fake clock
    # of an earlier one as its "original".
    for name, module in reversed(list(sys.modules.items())):
        hacker = getattr(module, 'time_hacker', None) if name.endswith('shinken_test') else None
        if hacker is not None and hacker not in hackers:
            hacker.set_real_time()
            hackers.append(hacker)
    return hackers


def make_module(path):
    modconf = Module({'module_name': 'named-pipe', 'module_type': 'named_pipe',
                      'command_file': path})
    modconf.properties = pipe_mod.properties.copy()
    return pipe_mod.get_instance(modconf)


class TestCommandBuffer(unittest.TestCase):

    def test_split_fragments_and_decode(self):
        buf = pipe_mod.CommandBuffer()
        self.assertEqual([], buf.feed(b'[1] DISABLE_NOTIF'))
        self.assertEqual(['[1] DISABLE_NOTIFICATIONS', '[2] ACK;h\xf4te'],
                         buf.feed(b'ICATIONS\n\n[2] ACK;h\xc3\xb4te\r\n[3] ADD'))
        self.assertEqual(['[3] ADD_SVC_COMMENT;h;s;1;admin;r\xe9seau'],
                         buf.feed(b'_SVC_COMMENT;h;s;1;admin;r\xe9seau\n'))
        self.assertEqual(b'', buf.pending)

    def test_endless_line_is_dropped(self):
        buf = pipe_mod.CommandBuffer()
        buf.feed(b'x' * (pipe_mod.MAX_LINE_LENGTH + 1))
        self.assertEqual(b'', buf.pending)


class TestNamedPipe(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'rw', 'nagios.cmd')
        self.module = make_module(self.path)
        self.module.from_q = queue.Queue()

    def tearDown(self):
        self.module.do_stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write(self, data):
        fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)

    def received(self):
        commands = []
        while not self.module.from_q.empty():
            commands.append(self.module.from_q.get())
        return commands

    def test_fifo_creation(self):
        self.assertIsNotNone(self.module.open())
        mode = os.stat(self.path).st_mode
        self.assertTrue(stat.S_ISFIFO(mode))
        self.assertEqual(0o660, stat.S_IMODE(mode))

    def test_replaces_a_regular_file(self):
        os.makedirs(os.path.dirname(self.path))
        open(self.path, 'w').close()
        self.module.open()
        self.assertTrue(stat.S_ISFIFO(os.stat(self.path).st_mode))

    def test_commands_are_queued(self):
        self.module.open()
        self.assertEqual(0, self.module.do_loop_turn(timeout=0))
        self.write(b'[1700000000] DISABLE_NOTIFICATIONS\n'
                   b'[1700000000] ADD_HOST_COMMENT;h1;1;admin;\xc3\xa9t\xc3\xa9\n[17000')
        self.assertEqual(2, self.module.do_loop_turn(timeout=1))
        # the writer closed the pipe: the next writer is still read
        self.write(b'00000] ENABLE_NOTIFICATIONS\n')
        self.assertEqual(1, self.module.do_loop_turn(timeout=1))
        commands = self.received()
        self.assertTrue(all(isinstance(c, ExternalCommand) for c in commands))
        self.assertEqual(['[1700000000] DISABLE_NOTIFICATIONS',
                          '[1700000000] ADD_HOST_COMMENT;h1;1;admin;été',
                          '[1700000000] ENABLE_NOTIFICATIONS'],
                         [c.cmd_line for c in commands])

    def test_stop_removes_the_fifo(self):
        self.module.open()
        self.module.do_stop()
        self.assertFalse(os.path.exists(self.path))


class TestNamedPipeProcess(unittest.TestCase):
    """Run the module as an external process, like the arbiter does."""

    def setUp(self):
        self.time_hackers = real_time()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for hacker in reversed(self.time_hackers):
            hacker.set_my_time()

    def test_external_process(self):
        path = os.path.join(self.tmpdir, 'nagios.cmd')
        module = make_module(path)
        module.create_queues()
        module.start()
        try:
            deadline = time.monotonic() + 20
            while not os.path.exists(path):
                self.assertLess(time.monotonic(), deadline, 'FIFO not created')
                time.sleep(0.1)
            with open(path, 'w') as pipe:
                pipe.write('[1700000000] SCHEDULE_FORCED_HOST_CHECK;h1;1700000000\n')
            command = module.from_q.get(timeout=10)
            self.assertEqual('[1700000000] SCHEDULE_FORCED_HOST_CHECK;h1;1700000000',
                             command.cmd_line)
        finally:
            module.stop_process()


class TestCommandFileDirective(unittest.TestCase):
    """command_file in shinken.cfg instantiates the module on the arbiter."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_autogenerated_module(self):
        cfg = os.path.join(self.tmpdir, 'shinken.cfg')
        with open(cfg, 'w') as handle:
            handle.write('command_file=%s/nagios.cmd\n'
                         'define arbiter {\n arbiter_name arbiter-master\n'
                         ' address localhost\n port 7770\n}\n' % self.tmpdir)
        conf = Config()
        raw_objects = conf.read_config_buf(conf.read_config([cfg]))
        conf.create_objects_for_type(raw_objects, 'arbiter')
        conf.create_objects_for_type(raw_objects, 'module')
        conf.early_arbiter_linking()
        arbiter = list(conf.arbiters)[0]
        self.assertEqual(['named_pipe'], [m.module_type for m in arbiter.modules])

        manager = ModulesManager('arbiter', MODULES_DIR, [])
        manager.set_modules(arbiter.modules)
        manager.load_and_init()
        self.assertEqual(1, len(manager.instances))
        self.assertIsInstance(manager.instances[0], pipe_mod.NamedPipe)
        self.assertEqual(os.path.join(self.tmpdir, 'nagios.cmd'), manager.instances[0].pipe_path)


if __name__ == '__main__':
    unittest.main()
