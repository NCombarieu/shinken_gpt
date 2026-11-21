#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Livestatus start-up with and without a usable log store sub-module."""

import json
import os
import shutil
import socket
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

from shinken.brok import Brok
from shinken.external_command import ExternalCommand
from shinken.modulesctx import modulesctx
from shinken.modulesmanager import ModulesManager
from shinken.objects.module import Module


import livestatus.module as livestatus_mod  # noqa: E402
from livestatus.livestatus_client_thread import LiveStatusClientThread  # noqa: E402


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


def free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def livestatus_conf(submodules, port=None):
    conf = Module({'module_name': 'livestatus', 'module_type': 'livestatus',
                   'host': '127.0.0.1', 'port': str(port or free_port())})
    conf.modules = submodules
    return conf


def sqlite_conf(directory):
    return Module({'module_name': 'logstore-sqlite', 'module_type': 'logstore_sqlite',
                   'database_file': os.path.join(directory, 'livestatus.db'),
                   'max_logs_age': '3m'})


def missing_conf():
    return Module({'module_name': 'logstore-missing', 'module_type': 'logstore_missing'})


class TestLogstoreSelection(unittest.TestCase):
    """LiveStatus_broker.setup_logstore() never fails."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def broker(self, submodules, modules_dir=MODULES_DIR):
        conf = livestatus_conf(submodules)
        conf.properties = livestatus_mod.properties.copy()
        broker = livestatus_mod.get_instance(conf)
        broker.modules_manager = ModulesManager('livestatus', modules_dir, [])
        broker.modules_manager.set_modules(broker.modules)
        broker.modules_manager.load_and_init()
        return broker

    def test_configured_sqlite_store(self):
        broker = self.broker([sqlite_conf(self.tmpdir)])
        store = broker.setup_logstore()
        self.assertEqual('LiveStatusLogStoreSqlite', type(store).__name__)
        self.assertIs(broker, store.app)
        broker.open_logstore()
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, 'livestatus.db')))
        store.close()

    def test_missing_store_falls_back_to_null(self):
        broker = self.broker([missing_conf()])
        store = broker.setup_logstore()
        self.assertEqual('LiveStatusLogStoreNull', type(store).__name__)
        self.assertIn(store, broker.modules_manager.instances)
        self.assertEqual([], list(store.get_live_data_log()))

    def test_no_store_configured(self):
        store = self.broker([]).setup_logstore()
        self.assertEqual('LiveStatusLogStoreNull', type(store).__name__)

    def test_old_style_database_file_parameter(self):
        conf = livestatus_conf([])
        conf.database_file = os.path.join(self.tmpdir, 'old.db')
        conf.properties = livestatus_mod.properties.copy()
        broker = livestatus_mod.get_instance(conf)
        broker.modules_manager = ModulesManager('livestatus', MODULES_DIR, [])
        store = broker.setup_logstore()
        self.assertEqual('LiveStatusLogStoreSqlite', type(store).__name__)
        self.assertEqual(conf.database_file, store.database_file)

    def test_null_store_module_missing_too(self):
        empty_dir = os.path.join(self.tmpdir, 'modules')
        os.mkdir(empty_dir)
        store = self.broker([missing_conf()], modules_dir=empty_dir).setup_logstore()
        self.assertIsInstance(store, livestatus_mod.BuiltinNullLogStore)

    def test_unopenable_database_falls_back(self):
        not_a_dir = os.path.join(self.tmpdir, 'file')
        open(not_a_dir, 'w').close()
        broker = self.broker([sqlite_conf(os.path.join(not_a_dir, 'sub'))])
        broker.setup_logstore()
        store = broker.open_logstore()
        self.assertIsInstance(store, livestatus_mod.BuiltinNullLogStore)


class TestClientThreadCommand(unittest.TestCase):
    """A COMMAND request has no output and must not raise (no traceback)."""

    def test_empty_response_is_not_a_wait_query(self):
        thread = LiveStatusClientThread.__new__(LiveStatusClientThread)
        sent = []

        class FakeLivestatus(object):
            def handle_request(self, data):
                return '', False

        thread.livestatus = FakeLivestatus()
        thread.send_response = sent.append
        thread.handle_request('COMMAND [0] DISABLE_NOTIFICATIONS\n')
        self.assertEqual([], sent)


class TestLivestatusProcess(unittest.TestCase):
    """Start the Livestatus external module like the broker does."""

    def setUp(self):
        # The legacy test helpers fake time.time()/time.sleep() process-wide:
        # a real external process needs the real clock.
        self.time_hackers = real_time()
        self.tmpdir = tempfile.mkdtemp()
        self.previous_modules_dir = modulesctx.get_modulesdir()
        modulesctx.set_modulesdir(MODULES_DIR)
        self.inst = None

    def tearDown(self):
        if self.inst is not None:
            self.inst.stop_process()
        modulesctx.set_modulesdir(self.previous_modules_dir)
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for hacker in reversed(self.time_hackers):
            hacker.set_my_time()

    def start(self, submodules):
        self.port = free_port()
        manager = ModulesManager('broker', MODULES_DIR, [livestatus_conf(submodules, self.port)])
        manager.load_and_init()
        self.assertEqual(1, len(manager.instances))
        self.inst = manager.instances[0]
        self.inst.create_queues()
        self.inst.start()

    def query(self, request, timeout=20):
        deadline = time.monotonic() + timeout
        while True:
            try:
                sock = socket.create_connection(('127.0.0.1', self.port), timeout=10)
                break
            except OSError:
                if time.monotonic() > deadline or not self.inst.process.is_alive():
                    self.fail('Livestatus did not open its port (exit code %s)'
                              % self.inst.process.exitcode)
                time.sleep(0.2)
        try:
            sock.sendall(request.encode('utf-8'))
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            sock.close()
        return b''.join(chunks).decode('utf-8')

    def check_running(self, expect_log_lines):
        now = int(time.time())
        self.query('GET status\nColumns: program_version\n\n')
        self.inst.to_q.put([Brok('log', {'log': '[%d] HOST ALERT: h1;DOWN;HARD;1;hôte KO\n' % now})])
        out = ''
        for _ in range(30):
            out = self.query('GET log\nColumns: type plugin_output\nFilter: time >= %d\n'
                             'OutputFormat: json\n\n' % (now - 60))
            if json.loads(out) or not expect_log_lines:
                break
            time.sleep(0.5)
        expected = [['HOST ALERT', 'hôte KO']] if expect_log_lines else []
        self.assertEqual(expected, json.loads(out))
        # External commands are forwarded to the broker.
        self.assertEqual('', self.query('COMMAND [%d] DISABLE_NOTIFICATIONS\n\n' % now))
        command = self.inst.from_q.get(timeout=10)
        self.assertIsInstance(command, ExternalCommand)
        self.assertIn('DISABLE_NOTIFICATIONS', command.cmd_line)
        # Still the same process: no crash/restart loop.
        self.assertTrue(self.inst.process.is_alive())

    def test_with_logstore_sqlite(self):
        self.start([sqlite_conf(self.tmpdir)])
        self.check_running(expect_log_lines=True)

    def test_without_usable_logstore(self):
        self.start([missing_conf()])
        self.check_running(expect_log_lines=False)


if __name__ == '__main__':
    unittest.main()
