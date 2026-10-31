#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""The status-webui /healthz endpoint reflects the real broker state."""

import os
import socket
import sys
import time
import unittest
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(REPO, 'modules')
if REPO not in sys.path:
    sys.path.insert(0, REPO)
if MODULES_DIR not in sys.path:
    sys.path.append(MODULES_DIR)

from shinken.brok import Brok  # noqa: E402
from shinken.objects.module import Module  # noqa: E402

import status_webui.module as webui_mod  # noqa: E402


def free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestHealthz(unittest.TestCase):

    def setUp(self):
        self.port = free_port()
        conf = Module({'module_name': 'status-webui', 'module_type': 'status_webui',
                       'host': '127.0.0.1', 'port': str(self.port),
                       'health_max_brok_age': '60'})
        conf.properties = webui_mod.properties.copy()
        self.module = webui_mod.get_instance(conf)
        self.module.init()

    def tearDown(self):
        self.module._server.shutdown()
        self.module._server.server_close()

    def get(self, path='/healthz'):
        url = 'http://127.0.0.1:%d%s' % (self.port, path)
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    def brok(self, brok_type, data=None):
        brok = Brok(brok_type, data or {})
        brok.prepare()
        self.module.manage_brok(brok)

    def test_unhealthy_before_configuration(self):
        status, body = self.get()
        self.assertEqual(503, status)
        self.assertIn('no configuration', body)
        # broks unrelated to a configuration are not enough
        self.brok('log', {'log': '[0] INFO: hello'})
        self.assertEqual(503, self.get()[0])

    def test_healthy_with_configuration_and_recent_broks(self):
        self.brok('program_status', {'instance_id': 0})
        self.brok('initial_broks_done', {'instance_id': 0})
        self.assertEqual((200, 'ok\n'), self.get())

    def test_unhealthy_when_broks_stop(self):
        self.brok('initial_broks_done', {'instance_id': 0})
        healthy, reason = self.module.health(now=time.time() + 61)
        self.assertFalse(healthy)
        self.assertIn('no brok received', reason)
        self.assertTrue(self.module.health()[0])

    def test_unhealthy_when_server_thread_died(self):
        self.brok('initial_broks_done', {'instance_id': 0})

        class DeadThread(object):
            def is_alive(self):
                return False

        self.module._server_thread = DeadThread()
        self.assertEqual(503, self.get()[0])


if __name__ == '__main__':
    unittest.main()
