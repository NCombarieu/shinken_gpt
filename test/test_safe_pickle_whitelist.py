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

"""Strict whitelist of the restricted unpickler.

Only the Shinken classes really exchanged between daemons may be
unpickled (fix of the remote code execution of Shinken 2.4.4). Any other
global, including functions living in Shinken modules, must be refused.
"""

import base64
import os
import pickle
import subprocess
import zlib

from shinken_test import *
from shinken.safepickle import SafeUnpickler
from shinken.check import Check
from shinken.notification import Notification
from shinken.eventhandler import EventHandler
from shinken.brok import Brok
from shinken.external_command import ExternalCommand
from shinken.downtime import Downtime
from shinken.comment import Comment


class Evil(object):
    """Pickles as a call to ``func(*args)``."""

    def __init__(self, func, *args):
        self.func = func
        self.args = args

    def __reduce__(self):
        return (self.func, self.args)


def proto0_call(module, name, arg):
    return ("c%s\n%s\n(S'%s'\ntR." % (module, name, arg)).encode('ascii')


class TestSafePickleWhitelist(ShinkenTest):

    def _refused(self, payload):
        with self.assertRaises((ValueError, pickle.UnpicklingError)):
            SafeUnpickler.loads(payload)

    def test_malicious_globals_are_refused(self):
        marker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'safe_pickle_marker_should_not_exist')
        cmd = 'touch %s' % marker
        payloads = [
            proto0_call('os', 'system', cmd),
            proto0_call('posix', 'system', cmd),
            proto0_call('subprocess', 'check_output', cmd),
            proto0_call('builtins', 'eval', '1+1'),
            proto0_call('__builtin__', 'eval', '1+1'),
            proto0_call('builtins', 'exec', 'pass'),
            proto0_call('builtins', '__import__', 'os'),
            proto0_call('builtins', 'getattr', 'x'),
            proto0_call('importlib', 'import_module', 'os'),
            proto0_call('shinken.misc.importlib', 'import_module', 'os'),
            proto0_call('shinken.util', 'safe_print', 'x'),
            proto0_call('shinken.objects.config', 'os', 'x'),
            proto0_call('copyreg', '__newobj__', 'x'),
            proto0_call('bottle', 'template', 'x'),
            b"cshinken.misc.importlib\nimport_module\n.",
        ]
        for proto in (0, 2, pickle.HIGHEST_PROTOCOL):
            payloads.append(pickle.dumps(Evil(os.system, cmd), proto))
            payloads.append(pickle.dumps(Evil(subprocess.Popen, cmd), proto))
            payloads.append(pickle.dumps(Evil(eval, '1+1'), proto))
            payloads.append(pickle.dumps(Evil(__import__, 'os'), proto))
        for payload in payloads:
            self._refused(payload)
        self.assertFalse(os.path.exists(marker))

    def test_legitimate_objects_are_accepted(self):
        host = self.sched.hosts.find_by_name("test_host_0")
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")
        objs = [
            Check('queue', 'check_ping', svc, time.time()),
            Notification('PROBLEM', 'scheduled', 'notify-service', 'cmd', svc, None,
                         time.time()),
            EventHandler('handler', ref=host),
            Brok('log', {'log': 'été'}),
            ExternalCommand('[%d] DISABLE_HOST_CHECK;test_host_0' % time.time()),
            set([1, 2]), frozenset(['a']), {'k': [1.5, None, True, b'\x00\xff']},
        ]
        # Objects with __slots__ cannot be pickled with protocols 0 and 1
        for proto in (2, pickle.HIGHEST_PROTOCOL):
            for obj in objs:
                back = SafeUnpickler.loads(pickle.dumps(obj, proto))
                self.assertIs(type(obj), type(back))
        for obj in (set([1]), frozenset([2]), {'a': b'\xff'}):
            back = SafeUnpickler.loads(pickle.dumps(obj, 0))
            self.assertIs(type(obj), type(back))
        # str payloads (protocol 0 through text streams) are accepted
        self.assertEqual({'a': 1}, SafeUnpickler.loads(pickle.dumps({'a': 1}, 0).decode('latin-1')))

    def test_retention_objects_are_accepted(self):
        now = time.time()
        self.sched.run_external_command(
            "[%d] SCHEDULE_HOST_DOWNTIME;test_host_0;%d;%d;1;0;600;admin;maintenance"
            % (now, now, now + 600))
        self.scheduler_loop(1, [])
        data = self.sched.get_retention_data()
        back = SafeUnpickler.loads(pickle.dumps(data, pickle.HIGHEST_PROTOCOL))
        dts = back['hosts']['test_host_0']['downtimes']
        self.assertEqual(1, len(dts))
        self.assertIsInstance(dts[0], Downtime)
        comments = back['hosts']['test_host_0']['comments']
        self.assertTrue(all(isinstance(c, Comment) for c in comments))
        self.assertEqual(1, len(comments))

    def test_configuration_and_scheduler_exchanges(self):
        # Realm configurations sent by the arbiter to the schedulers
        for realm in self.conf.realms:
            for conf in realm.confs.values():
                for proto in (0, pickle.HIGHEST_PROTOCOL):
                    SafeUnpickler.loads(pickle.dumps(conf, proto))
        # Whole configuration sent to the spare arbiters
        SafeUnpickler.loads(pickle.dumps(self.conf, pickle.HIGHEST_PROTOCOL))
        # Checks/actions/broks as sent over HTTP (base64(zlib(pickle)))
        self.scheduler_loop(2, [])
        for objs in (list(self.sched.checks.values()), list(self.sched.actions.values()),
                     list(self.sched.broks.values()) if isinstance(self.sched.broks, dict)
                     else list(self.sched.broks)):
            raw = base64.b64encode(zlib.compress(pickle.dumps(objs), 2))
            back = SafeUnpickler.loads(zlib.decompress(base64.b64decode(raw)))
            self.assertEqual(len(objs), len(back))


if __name__ == '__main__':
    unittest.main()
