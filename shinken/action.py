#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2017:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel-consult.de
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

import os
import time
import shlex
import sys
import subprocess
import signal
import threading

from .log import logger
from .util import string_decode, bytes_to_unicode

__all__ = ('Action',)

valid_exit_status = (0, 1, 2, 3)

only_copy_prop = ('id', 'status', 'command', 't_to_go', 'timeout',
                  'env', 'module_type', 'execution_time', 'u_time', 's_time')

shellchars = ('!', '$', '^', '&', '*', '(', ')', '~', '[', ']',
              '|', '{', '}', ';', '<', '>', '?', '`')


class __Action(object):
    """Common implementation for actions and checks."""
    id = 0

    @staticmethod
    def assume_at_least_id(_id):
        Action.id = max(Action.id, _id)

    def set_type_active(self):
        pass

    def set_type_passive(self):
        pass

    def get_local_environnement(self):
        local_env = os.environ.copy()
        for p in self.env:
            local_env[p] = bytes_to_unicode(self.env[p]).rstrip('\x00')
        return local_env

    def execute(self):
        self.status = 'launched'
        self.check_time = time.time()
        self._execution_start_monotonic = time.monotonic()
        self.wait_time = 0.0001
        self.last_poll = self.check_time
        self.local_env = self.get_local_environnement()
        self.stdoutdata = ''
        self.stderrdata = ''
        self.output = ''
        self.long_output = ''
        self.perf_data = ''
        return self.execute__()

    def _elapsed_execution_time(self):
        start = getattr(self, '_execution_start_monotonic', None)
        if start is not None:
            return max(0.0, time.monotonic() - start)
        return max(0.0, time.time() - self.check_time)

    def _start_output_collector(self):
        """Continuously drain stdout and stderr without blocking the main loop."""
        self._stdout_chunks = []
        self._stderr_chunks = []

        def drain(pipe, chunks):
            try:
                while True:
                    chunk = pipe.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except (OSError, ValueError) as exp:
                logger.debug("Failed while collecting command output: %s", exp)

        self._output_collectors = [
            threading.Thread(target=drain, args=(self.process.stdout, self._stdout_chunks),
                             name='shinken-action-stdout', daemon=True),
            threading.Thread(target=drain, args=(self.process.stderr, self._stderr_chunks),
                             name='shinken-action-stderr', daemon=True),
        ]
        for collector in self._output_collectors:
            collector.start()

    def _finish_output_collector(self):
        for collector in getattr(self, '_output_collectors', ()):
            collector.join(timeout=1)
        self.stdoutdata += bytes_to_unicode(b''.join(getattr(self, '_stdout_chunks', ())))
        self.stderrdata += bytes_to_unicode(b''.join(getattr(self, '_stderr_chunks', ())))
        for attr in ('_output_collectors', '_stdout_chunks', '_stderr_chunks'):
            if hasattr(self, attr):
                delattr(self, attr)

    def get_outputs(self, out, max_plugins_output_length):
        out = out[:max_plugins_output_length]
        out = out.replace(r'\|', '___PROTECT_PIPE___')
        elts = out.split('\n')
        elts_line1 = elts[0].split('|')
        self.output = elts_line1[0].strip().replace('___PROTECT_PIPE___', '|')
        self.perf_data = ''
        if len(elts_line1) > 1:
            self.perf_data = elts_line1[1].strip().replace('___PROTECT_PIPE___', '|')
        long_output = []
        in_perfdata = False
        for line in elts[1:]:
            if in_perfdata:
                self.perf_data += ' ' + line.strip().replace('___PROTECT_PIPE___', '|')
            else:
                line_elts = line.split('|', 1)
                long_output.append(line_elts[0].strip().replace('___PROTECT_PIPE___', '|'))
                if len(line_elts) > 1:
                    in_perfdata = True
                    self.perf_data += ' ' + line_elts[1].strip().replace('___PROTECT_PIPE___', '|')
        self.long_output = '\n'.join(long_output)
        self.output = string_decode(self.output)
        self.long_output = string_decode(self.long_output)
        self.perf_data = string_decode(self.perf_data)

    def check_finished(self, max_plugins_output_length):
        if self.status != 'launched':
            return
        self.last_poll = time.time()
        _, _, child_utime, child_stime, _ = os.times()
        if self.process.poll() is None:
            self.wait_time = min(self.wait_time * 2, 0.1)
            elapsed = self._elapsed_execution_time()
            if elapsed > self.timeout:
                self.kill__()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                self._finish_output_collector()
                if not self.stdoutdata.strip():
                    self.stdoutdata = self.stderrdata
                self.get_outputs(self.stdoutdata, max_plugins_output_length)
                self.status = 'timeout'
                self.execution_time = elapsed
                self.exit_status = 3
                for pipe in (self.process.stdout, self.process.stderr):
                    if pipe and not pipe.closed:
                        pipe.close()
                del self.process
                _, _, n_child_utime, n_child_stime, _ = os.times()
                self.u_time = n_child_utime - child_utime
                self.s_time = n_child_stime - child_stime
                return
            return

        self._finish_output_collector()
        self.exit_status = self.process.returncode
        for pipe in (self.process.stdout, self.process.stderr):
            if pipe and not pipe.closed:
                pipe.close()
        del self.process

        if self.exit_status == -11:
            self.stderrdata += " signaled #11 (SIGSEGV)"
        if not self.stderrdata.strip() and self.exit_status not in valid_exit_status:
            self.stderrdata += "Abnormal termination with code: %r" % (self.exit_status,)

        if ('sh: -c: line 0: unexpected EOF while looking for matching' in self.stderrdata
                or ('sh: -c:' in self.stderrdata and ': Syntax' in self.stderrdata)
                or 'Syntax error: Unterminated quoted string' in self.stderrdata):
            self.stdoutdata = self.stdoutdata + self.stderrdata
            self.exit_status = 3

        if self.exit_status not in valid_exit_status:
            self.exit_status = 3
        if not self.stdoutdata.strip():
            self.stdoutdata = self.stderrdata

        self.get_outputs(self.stdoutdata, max_plugins_output_length)
        del self.stdoutdata
        del self.stderrdata
        self.status = 'done'
        self.execution_time = self._elapsed_execution_time()
        _, _, n_child_utime, n_child_stime, _ = os.times()
        self.u_time = n_child_utime - child_utime
        self.s_time = n_child_stime - child_stime

    def copy_shell__(self, new_i):
        for prop in only_copy_prop:
            setattr(new_i, prop, getattr(self, prop))
        return new_i

    def got_shell_characters(self):
        quote = None
        escaped = False
        for char in bytes_to_unicode(self.command):
            if escaped:
                escaped = False
                continue
            if char == '\\' and quote != "'":
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = None
                elif quote == '"' and char in ('$', '`'):
                    return True
                continue
            if char in ('"', "'"):
                quote = char
                continue
            if char in shellchars:
                return True
        return False


if os.name != 'nt':
    class Action(__Action):
        def execute__(self, force_shell=False):
            force_shell |= self.got_shell_characters()
            self.command = bytes_to_unicode(self.command)
            if force_shell:
                cmd = self.command
            else:
                try:
                    cmd = shlex.split(self.command)
                except ValueError as exp:
                    self.output = 'Not a valid shell command: %s' % exp
                    self.exit_status = 3
                    self.status = 'done'
                    self.execution_time = self._elapsed_execution_time()
                    return
            try:
                self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                close_fds=True, shell=force_shell, env=self.local_env,
                                                preexec_fn=os.setsid)
                self._start_output_collector()
            except OSError as exp:
                logger.error("Fail launching command: %s %s %s", self.command, exp, force_shell)
                if not force_shell and exp.errno == 8:
                    return self.execute__(True)
                self.output = str(exp)
                self.exit_status = 2
                self.status = 'done'
                self.execution_time = self._elapsed_execution_time()
                if exp.errno == 24:
                    return 'toomanyopenfiles'

        def kill__(self):
            os.killpg(self.process.pid, signal.SIGKILL)
else:
    import ctypes
    TerminateProcess = ctypes.windll.kernel32.TerminateProcess

    class Action(__Action):
        def execute__(self):
            self.command = bytes_to_unicode(self.command)
            try:
                cmd = shlex.split(self.command)
            except ValueError as exp:
                self.output = 'Not a valid shell command: %s' % exp
                self.exit_status = 3
                self.status = 'done'
                self.execution_time = self._elapsed_execution_time()
                return
            try:
                self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                env=self.local_env, shell=True)
                self._start_output_collector()
            except OSError as exp:
                logger.info("We kill the process: %s %s", exp, self.command)
                self.status = 'timeout'
                self.execution_time = self._elapsed_execution_time()

        def kill__(self):
            TerminateProcess(int(self.process._handle), -1)
