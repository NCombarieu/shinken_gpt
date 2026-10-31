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

"""Round trip of the scheduler retention data.

The data built by ``Scheduler.get_retention_data()`` is pickled, loaded back
and given to ``Scheduler.restore_retention_data()`` on a freshly configured
scheduler. Downtimes, acknowledgements and comments must be effective after
the restoration (no notification during a restored downtime).
"""

import pickle

from shinken_test import *


class TestRetentionRoundTrip(ShinkenTest):

    def _objects(self):
        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = []
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")
        svc.checks_in_progress = []
        svc.act_depend_of = []
        return host, svc

    def test_downtime_ack_comment_survive_restart(self):
        host, svc = self._objects()
        now = time.time()

        # Host in a fixed downtime for 10 minutes
        self.sched.run_external_command(
            "[%d] SCHEDULE_HOST_DOWNTIME;test_host_0;%d;%d;1;0;600;admin;maintenance"
            % (now, now, now + 600))
        # Service in a HARD CRITICAL state, then acknowledged
        self.scheduler_loop(3, [[host, 0, 'UP'], [svc, 2, 'CRITICAL']])
        self.sched.run_external_command(
            "[%d] ACKNOWLEDGE_SVC_PROBLEM;test_host_0;test_ok_0;2;1;1;admin;working on it"
            % now)
        # And a plain comment on the service
        self.sched.run_external_command(
            "[%d] ADD_SVC_COMMENT;test_host_0;test_ok_0;1;admin;some comment" % now)
        self.scheduler_loop(1, [])

        self.assertEqual(1, host.scheduled_downtime_depth)
        self.assertTrue(svc.problem_has_been_acknowledged)

        blob = pickle.dumps(self.sched.get_retention_data(), pickle.HIGHEST_PROTOCOL)

        # "Restart": a brand new scheduler with the same configuration
        self.setUp()
        host, svc = self._objects()
        self.assertEqual(0, host.scheduled_downtime_depth)
        self.assertFalse(svc.problem_has_been_acknowledged)

        self.sched.restore_retention_data(pickle.loads(blob))

        # Downtime is effective
        self.assertEqual(1, len(host.downtimes))
        self.assertIn(host.downtimes[0], list(self.sched.downtimes.values()))
        self.assertEqual(1, host.scheduled_downtime_depth)
        self.assertTrue(host.in_scheduled_downtime)
        # Acknowledgement is effective
        self.assertIsNotNone(svc.acknowledgement)
        self.assertIs(svc, svc.acknowledgement.ref)
        self.assertTrue(svc.problem_has_been_acknowledged)
        self.assertEqual('CRITICAL', svc.state)
        self.assertEqual('HARD', svc.state_type)
        # Comments are re-attached and registered in the scheduler
        texts = [c.comment for c in svc.comments]
        self.assertIn('some comment', texts)
        for c in svc.comments:
            self.assertIs(svc, c.ref)
            self.assertIn(c, list(self.sched.comments.values()))
        # New objects do not reuse restored ids
        from shinken.downtime import Downtime
        self.assertGreater(Downtime.id, host.downtimes[0].id)

        # The host goes HARD DOWN during the restored downtime: no
        # notification must be raised
        self.clear_logs()
        self.clear_actions()
        self.scheduler_loop(3, [[host, 2, 'DOWN']])
        self.assertEqual('HARD', host.state_type)
        self.assert_no_log_match('HOST NOTIFICATION')

    def test_restore_unknown_objects_is_ignored(self):
        host, svc = self._objects()
        data = {'hosts': {'no_such_host': {}},
                'services': {('no_such_host', 'nope'): {}}}
        self.sched.restore_retention_data(data)
        self.assertEqual(0, host.scheduled_downtime_depth)


if __name__ == '__main__':
    unittest.main()
