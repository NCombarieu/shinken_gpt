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

"""Workers of a daemon killed with SIGKILL must not survive it.

Orphan workers used to keep the copy of the daemon listening socket, so
the restarted poller failed with PortNotFree.
"""

import os
import signal
import socket
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAKE_DAEMON = r'''
import sys, threading, time
from multiprocessing import Queue
from shinken.http_daemon import HTTPDaemon
from shinken.worker import Worker

port = int(sys.argv[1])
daemon = HTTPDaemon('127.0.0.1', port, 'cheroot', False, None, None, None, False, 2)
threading.Thread(target=daemon.run, daemon=True).start()
deadline = time.time() + 20
while getattr(daemon.srv.srv, 'socket', None) is None and time.time() < deadline:
    time.sleep(0.05)
w = Worker(1, Queue(), Queue(), 1, mortal=False, loaded_into='test', http_daemon=daemon)
w.start()
print(w._process.pid, flush=True)
time.sleep(600)
'''


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie is dead enough: check its state when /proc is available
    try:
        with open('/proc/%d/stat' % pid) as fd:
            return fd.read().split(')')[-1].split()[0] != 'Z'
    except OSError:
        return True


def port_is_free(port):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


@unittest.skipUnless(hasattr(os, 'fork'), 'POSIX only')
class TestWorkerOrphans(unittest.TestCase):

    def test_workers_die_with_killed_daemon(self):
        port = free_port()
        env = dict(os.environ)
        env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
        parent = subprocess.Popen([sys.executable, '-c', FAKE_DAEMON, str(port)],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=env, cwd=ROOT)
        worker_pid = None
        try:
            line = parent.stdout.readline()
            worker_pid = int(line.strip())
            self.assertTrue(pid_alive(worker_pid))
            self.assertFalse(port_is_free(port))

            parent.send_signal(signal.SIGKILL)
            parent.wait(timeout=10)

            deadline = time.time() + 15
            while time.time() < deadline and (pid_alive(worker_pid) or not port_is_free(port)):
                time.sleep(0.1)
            self.assertFalse(pid_alive(worker_pid), 'worker survived its daemon')
            self.assertTrue(port_is_free(port), 'daemon port still bound')
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait()
            if worker_pid is not None and pid_alive(worker_pid):
                os.kill(worker_pid, signal.SIGKILL)
            parent.stdout.close()


if __name__ == '__main__':
    unittest.main()
