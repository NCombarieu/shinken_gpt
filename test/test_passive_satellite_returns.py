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

"""The scheduler pulls the results of passive pollers and reactionners.

``get_returns`` answers with a raw pickle (bytes). The scheduler used to
convert it to ``str`` before unpickling, which lost every result.
"""

import pickle

from shinken_test import *
from shinken.check import Check
from shinken.eventhandler import EventHandler


class FakeCon(object):
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, path, args={}, wait='short'):
        self.calls.append(path)
        if path == 'ping':
            return 'pong'
        return self.payload


class TestPassiveSatelliteReturns(ShinkenTest):

    def _link(self, payload):
        con = FakeCon(payload)
        return con, {'instance_id': 0, 'name': 'passive-sat', 'passive': True,
                     'con': con, 'poller_tags': ['None'], 'reactionner_tags': ['None']}

    def test_poller_results_are_unpickled_from_bytes(self):
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")
        chk = Check('done', 'check_dummy é', svc, time.time())
        chk.output = 'OK - données reçues'
        con, link = self._link(pickle.dumps([chk], pickle.HIGHEST_PROTOCOL))
        self.sched.pollers = {0: link}
        self.sched.reactionners = {}
        self.sched.waiting_results = []

        self.sched.get_actions_from_passives_satellites()

        self.assertEqual(['ping', 'get_returns'], con.calls)
        self.assertEqual(1, len(self.sched.waiting_results))
        res = self.sched.waiting_results[0]
        self.assertEqual('OK - données reçues', res.output)
        self.assertEqual(1, res.check_type)  # flagged as passive

    def test_reactionner_results_are_unpickled_from_bytes(self):
        host = self.sched.hosts.find_by_name("test_host_0")
        ev = EventHandler('handler', ref=host)
        con, link = self._link(pickle.dumps([ev]))
        self.sched.pollers = {}
        self.sched.reactionners = {0: link}
        self.sched.waiting_results = []
        self.sched.get_actions_from_passives_satellites()
        self.assertEqual(1, len(self.sched.waiting_results))

    def test_malicious_payload_is_dropped(self):
        payload = b"cos\nsystem\n(S'true'\ntR."
        con, link = self._link(payload)
        self.sched.pollers = {0: link}
        self.sched.reactionners = {}
        self.sched.waiting_results = []
        self.sched.get_actions_from_passives_satellites()
        self.assertEqual([], self.sched.waiting_results)


if __name__ == '__main__':
    unittest.main()
