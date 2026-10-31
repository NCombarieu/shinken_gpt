#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests of the retention-pickle scheduler module."""

import os
import pickle
import shutil
import struct
import sys
import tempfile

from shinken_test import ShinkenTest, unittest

from shinken.acknowledge import Acknowledge
from shinken.comment import Comment
from shinken.downtime import Downtime
from shinken.objects.module import Module

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(REPO, 'modules')
if MODULES_DIR not in sys.path:
    sys.path.append(MODULES_DIR)

import retention_pickle.module as retention_mod  # noqa: E402


# ----------------------------------------------------------------------
# Minimal emitter of what CPython 2.7 cPickle.dump(obj, f, protocol=2)
# writes: Python 2 "str" values are raw bytes (SHORT_BINSTRING/BINSTRING),
# objects are GLOBAL + EMPTY_TUPLE + NEWOBJ + BUILD.
# ----------------------------------------------------------------------
class Py2Str(bytes):
    """A Python 2 byte string."""


class Py2Obj(object):
    def __init__(self, module, name, state):
        self.module, self.name, self.state = module, name, state


class Py2Set(list):
    """A Python 2 set (pickled as __builtin__.set([...]))."""


def _emit(obj, out):
    if isinstance(obj, Py2Str):
        if len(obj) < 256:
            out += b'U' + bytes([len(obj)]) + obj
        else:
            out += b'T' + struct.pack('<i', len(obj)) + obj
    elif isinstance(obj, str):
        data = obj.encode('utf-8')
        out += b'X' + struct.pack('<I', len(data)) + data
    elif obj is None:
        out += b'N'
    elif obj is True:
        out += b'\x88'
    elif obj is False:
        out += b'\x89'
    elif isinstance(obj, int):
        out += b'J' + struct.pack('<i', obj)
    elif isinstance(obj, float):
        out += b'G' + struct.pack('>d', obj)
    elif isinstance(obj, Py2Set):
        out += b'c__builtin__\nset\n]('
        for item in obj:
            _emit(item, out)
        out += b'e\x85R'
    elif isinstance(obj, list):
        out += b']('
        for item in obj:
            _emit(item, out)
        out += b'e'
    elif isinstance(obj, tuple):
        out += b'('
        for item in obj:
            _emit(item, out)
        out += b't'
    elif isinstance(obj, dict):
        out += b'}('
        for key, value in obj.items():
            _emit(key, out)
            _emit(value, out)
        out += b'u'
    elif isinstance(obj, Py2Obj):
        out += b'c' + obj.module.encode() + b'\n' + obj.name.encode() + b'\n)\x81'
        _emit(obj.state, out)
        out += b'b'
    else:
        raise TypeError(type(obj))


def py2_dumps(obj):
    out = bytearray(b'\x80\x02')
    _emit(obj, out)
    out += b'.'
    return bytes(out)


S = Py2Str


def py2_retention_sample(latin1_output=False):
    """Retention data like Shinken 2.4 (Python 2) writes it."""
    downtime = Py2Obj('shinken.downtime', 'Downtime', {
        S(b'id'): 7, S(b'activate_me'): [], S(b'entry_time'): 1700000000,
        S(b'fixed'): True, S(b'start_time'): 1700000000, S(b'duration'): 3600,
        S(b'trigger_id'): 0, S(b'end_time'): 2000000000, S(b'real_end_time'): 2000000000,
        S(b'author'): S(b'admin'), S(b'comment'): S('Maintenance prévue'.encode('utf-8')),
        S(b'is_in_effect'): True, S(b'has_been_triggered'): True, S(b'can_be_deleted'): False})
    ack = Py2Obj('shinken.acknowledge', 'Acknowledge', {
        S(b'id'): 3, S(b'sticky'): 2, S(b'notify'): 1, S(b'end_time'): 0,
        S(b'author'): S(b'admin'), S(b'comment'): S('Pris en compte, équipe réseau'.encode('utf-8')),
        S(b'persistent'): True})
    comment = Py2Obj('shinken.comment', 'Comment', {
        S(b'id'): 5, S(b'persistent'): True, S(b'author'): S(b'admin'),
        S(b'comment'): S('Commentaire été'.encode('utf-8')), S(b'comment_type'): 1,
        S(b'entry_type'): 1, S(b'source'): 0, S(b'expires'): False, S(b'expire_time'): 0,
        S(b'can_be_deleted'): False, S(b'entry_time'): 1700000000})
    output = 'CRITICAL - hôte injoignable'
    output = output.encode('latin-1' if latin1_output else 'utf-8')
    host = {
        S(b'state'): S(b'DOWN'), S(b'state_id'): 1, S(b'state_type'): S(b'HARD'),
        S(b'output'): S(output), S(b'long_output'): S(b'x' * 300),
        S(b'problem_has_been_acknowledged'): True, S(b'acknowledgement'): ack,
        S(b'downtimes'): [downtime], S(b'comments'): [comment],
        S(b'notifications_in_progress'): {}, S(b'notified_contacts'): Py2Set([S(b'admin')]),
        S(b'scheduled_downtime_depth'): 1, S(b'last_chk'): 1700000000, S(b'latency'): 0.25,
        S(b'unicode_value'): 'déjà unicode'}
    return {S(b'hosts'): {S(b'test_host_0'): host},
            S(b'services'): {(S(b'test_host_0'), S(b'test_ok_0')): {
                S(b'state'): S(b'OK'), S(b'output'): S('Tout va bien é'.encode('utf-8'))}}}


class FakeScheduler(object):
    def __init__(self, data=None):
        self.data = data
        self.restored = None

    def get_retention_data(self):
        return self.data

    def restore_retention_data(self, data):
        self.restored = data


def make_module(path, **params):
    conf = {'module_name': 'retention-pickle', 'module_type': 'pickle_retention_file',
            'path': path}
    conf.update(params)
    modconf = Module(conf)
    modconf.properties = retention_mod.properties.copy()
    return retention_mod.get_instance(modconf)


class TestRetentionPickleFile(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'sub', 'retention.dat')
        self.module = make_module(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def load(self):
        sched = FakeScheduler()
        result = self.module.hook_load_retention(sched)
        return result, sched.restored

    def test_missing_file(self):
        self.assertEqual((False, None), self.load())

    def test_save_and_load_round_trip(self):
        data = {'hosts': {'h1': {'output': 'Hôte injoignable', 'notified_contacts': {'admin'}}},
                'services': {('h1', 's1'): {'state': 'OK'}}}
        self.assertTrue(self.module.update_retention_objects(FakeScheduler(data)))
        self.assertEqual(['retention.dat'], os.listdir(os.path.dirname(self.path)))
        result, restored = self.load()
        self.assertTrue(result)
        self.assertEqual(data, restored)

    def test_written_file_is_readable_by_python2(self):
        """Protocol 2 by default: no opcode newer than Python 2.7 can read."""
        self.module.update_retention_objects(FakeScheduler({'hosts': {}, 'services': {}}))
        with open(self.path, 'rb') as handle:
            self.assertEqual(b'\x80\x02', handle.read(2))

    def test_failed_save_keeps_previous_file(self):
        good = {'hosts': {'h1': {}}, 'services': {}}
        self.module.update_retention_objects(FakeScheduler(good))
        bad = {'hosts': {'h1': {'callback': lambda: None}}, 'services': {}}
        self.assertFalse(self.module.update_retention_objects(FakeScheduler(bad)))
        self.assertEqual(['retention.dat'], os.listdir(os.path.dirname(self.path)))
        self.assertEqual(good, self.load()[1])

    def test_unsafe_pickle_is_rejected(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'wb') as handle:
            handle.write(b'\x80\x02cos\nsystem\nX\x04\x00\x00\x00true\x85R.')
        self.assertEqual((False, None), self.load())

    def test_garbage_and_unexpected_content(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'wb') as handle:
            handle.write(b'not a pickle')
        self.assertEqual((False, None), self.load())
        with open(self.path, 'wb') as handle:
            pickle.dump(['a', 'list'], handle, protocol=2)
        self.assertEqual((False, None), self.load())

    def check_py2_data(self, data, expected_output):
        self.assertEqual({'test_host_0'}, set(data['hosts']))
        self.assertEqual({('test_host_0', 'test_ok_0')}, set(data['services']))
        host = data['hosts']['test_host_0']
        self.assertEqual('DOWN', host['state'])
        self.assertEqual(expected_output, host['output'])
        self.assertEqual('x' * 300, host['long_output'])
        self.assertEqual('déjà unicode', host['unicode_value'])
        self.assertEqual({'admin'}, host['notified_contacts'])
        downtime = host['downtimes'][0]
        self.assertIsInstance(downtime, Downtime)
        self.assertEqual(7, downtime.id)
        self.assertEqual('Maintenance prévue', downtime.comment)
        self.assertIsInstance(host['acknowledgement'], Acknowledge)
        self.assertEqual('Pris en compte, équipe réseau', host['acknowledgement'].comment)
        self.assertIsInstance(host['comments'][0], Comment)
        self.assertEqual('Commentaire été', host['comments'][0].comment)
        self.assertEqual('Tout va bien é',
                         data['services'][('test_host_0', 'test_ok_0')]['output'])

    def test_reads_python2_master_file_utf8(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'wb') as handle:
            handle.write(py2_dumps(py2_retention_sample()))
        result, data = self.load()
        self.assertTrue(result)
        self.check_py2_data(data, 'CRITICAL - hôte injoignable')

    def test_reads_python2_master_file_mixed_latin1(self):
        """One latin-1 string must not corrupt the UTF-8 accents of the others."""
        raw = py2_dumps(py2_retention_sample(latin1_output=True))
        data = retention_mod.load_retention_bytes(raw)
        self.check_py2_data(data, 'CRITICAL - hôte injoignable')


class TestRetentionPickleScheduler(ShinkenTest):
    """Save the retention data of a real scheduler and read it back."""

    def setUp(self):
        self.setup_with_file('etc/shinken_1r_1h_1s.cfg')
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scheduler_retention_round_trip(self):
        host = self.sched.hosts.find_by_name('test_host_0')
        svc = self.sched.services.find_srv_by_name_and_hostname('test_host_0', 'test_ok_0')
        self.scheduler_loop(2, [[host, 2, 'DOWN | value1=1'], [svc, 2, 'CRITICAL é']])
        module = make_module(os.path.join(self.tmpdir, 'retention.dat'))
        module.hook_save_retention(self.sched)

        fake = FakeScheduler()
        self.assertTrue(module.hook_load_retention(fake))
        self.assertEqual(self.sched.get_retention_data().keys(), fake.restored.keys())
        saved_host = fake.restored['hosts']['test_host_0']
        self.assertEqual(host.state, saved_host['state'])
        self.assertEqual(host.output, saved_host['output'])
        saved_svc = fake.restored['services'][('test_host_0', 'test_ok_0')]
        self.assertEqual('CRITICAL é', saved_svc['output'])


if __name__ == '__main__':
    unittest.main()
