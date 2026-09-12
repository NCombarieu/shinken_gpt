#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2009-2014:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
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

#
# This file is used to test reading and processing of config files
#

from __future__ import print_function
from __future__ import absolute_import
from shinken_test import *

from queue import Queue
from shinken.worker import Worker
from shinken.objects.service import Service
from shinken.objects.host import Host
from shinken.objects.contact import Contact
from six.moves import range

modconf = Module()


class TestTimeout(ShinkenTest):
    def setUp(self):
        # we have an external process, so we must un-fake time functions
        self.setup_with_file('etc/shinken_check_timeout.cfg')
        time_hacker.set_real_time()

    def test_notification_timeout(self):
        if os.name == 'nt':
            return

        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")

        # This test drives a worker synchronously in-process. Thread queues are
        # sufficient for the result/control paths and avoid multiprocessing
        # feeder threads that otherwise make this legacy test timing-sensitive.
        from_queue = Queue()
        control_queue = Queue()

        # This testscript plays the role of the reactionner.
        w = Worker(1, Queue(), from_queue, 1)
        w.id = 1
        w.i_am_dying = False

        # We prepare a notification for the worker.
        c = Contact()
        c.contact_name = "mr.schinken"
        n = Notification('PROBLEM', 'scheduled', 'libexec/sleep_command.sh 7', '', svc, '', '', id=1)
        n.status = "queue"
        n.t_to_go = time.time()
        n.contact = c
        n.timeout = 2
        n.env = {}
        n.exit_status = 0
        n.module_type = "fork"
        nn = n.copy_shell()

        # Exercise the same launch/finish path as Worker.work(), but seed the
        # in-process worker directly instead of relying on queue feeder timing.
        w.checks = [nn]
        w.returns_queue = from_queue
        w.c = control_queue
        deadline = time.monotonic() + n.timeout + 5
        while w.checks and time.monotonic() < deadline:
            w.launch_new_checks()
            w.manage_finished_checks()

        # The worker should have finished its job now, either correctly or
        # with a timeout.
        o = from_queue.get(timeout=1)

        self.assertEqual('timeout', o.status)
        self.assertEqual(3, o.exit_status)
        self.assertLess(o.execution_time, n.timeout + 1)

        # Now look what the scheduler says to all this.
        self.sched.actions[n.id] = n
        self.sched.put_results(o)
        self.show_logs()
        self.assert_any_log_match("Contact mr.schinken service notification command 'libexec/sleep_command.sh 7 ' timed out after 2 seconds")

    def test_notification_timeout_on_command(self):
        #
        # Config is not correct because of a wrong relative path
        # in the main config file
        #
        print("Get the hosts and services")
        now = time.time()
        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = []  # ignore the router
        router = self.sched.hosts.find_by_name("test_router_0")
        router.checks_in_progress = []
        router.act_depend_of = []  # ignore the router
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")
        print(svc.checks_in_progress)
        cs = svc.checks_in_progress
        self.assertEqual(1, len(cs))
        c = cs.pop()
        print(c)
        print(c.timeout)
        self.assertEqual(5, c.timeout)


if __name__ == '__main__':
    unittest.main()
