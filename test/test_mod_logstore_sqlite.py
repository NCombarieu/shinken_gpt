#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests of the logstore-sqlite Livestatus sub-module."""

import datetime
import json
import os
import queue
import shutil
import sqlite3
import sys
import tempfile
import time

from shinken_test import ShinkenTest, unittest

from shinken.brok import Brok
from shinken.misc.datamanager import datamgr
from shinken.objects.module import Module

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES_DIR = os.path.join(REPO, 'modules')
if MODULES_DIR not in sys.path:
    sys.path.append(MODULES_DIR)

import livestatus.module as livestatus_mod  # noqa: E402
import logstore_sqlite.module as sqlite_mod  # noqa: E402


def make_store(directory, **params):
    conf = {'module_name': 'logstore-sqlite', 'module_type': 'logstore_sqlite',
            'database_file': os.path.join(directory, 'livestatus.db'),
            'archive_path': os.path.join(directory, 'archives'),
            'max_logs_age': '3m'}
    conf.update(params)
    modconf = Module(conf)
    modconf.properties = sqlite_mod.properties.copy()
    store = sqlite_mod.get_instance(modconf)
    store.open()
    store.prepare_log_db_table()
    return store


def log_brok(line):
    return Brok('log', {'log': line + '\n'})


class TestHelpers(unittest.TestCase):

    def test_parse_max_logs_age(self):
        self.assertEqual(7, sqlite_mod.parse_max_logs_age('7'))
        self.assertEqual(7, sqlite_mod.parse_max_logs_age('7d'))
        self.assertEqual(14, sqlite_mod.parse_max_logs_age('2w'))
        self.assertEqual(93, sqlite_mod.parse_max_logs_age('3m'))
        self.assertEqual(365, sqlite_mod.parse_max_logs_age('1y'))
        self.assertEqual(0, sqlite_mod.parse_max_logs_age('0'))
        self.assertEqual(sqlite_mod.DEFAULT_MAX_LOGS_AGE, sqlite_mod.parse_max_logs_age('soon'))

    def test_time_bounds_are_extracted(self):
        stack = sqlite_mod.SqlFilterStack()
        stack.put(sqlite_mod.make_sql_filter('>=', 'time', 100))
        stack.put(sqlite_mod.make_sql_filter('<', 'time', '200'))
        stack.put(sqlite_mod.make_sql_filter('=', 'class', 1))
        node = stack.result()
        self.assertEqual((100, 199), (node.low, node.high))
        self.assertTrue(node.exact)
        self.assertEqual(0, len(stack))

    def test_or_with_unbounded_member_has_no_time_bound(self):
        stack = sqlite_mod.SqlFilterStack()
        stack.put(sqlite_mod.make_sql_filter('>=', 'time', 100))
        stack.put(sqlite_mod.make_sql_filter('=', 'host_name', 'h1'))
        stack.or_elements(2)
        node = stack.result()
        self.assertIsNone(node.low)
        self.assertIn(' OR ', node.clause)

    def test_negated_superset_is_always_true(self):
        stack = sqlite_mod.SqlFilterStack()
        stack.put(sqlite_mod.make_sql_filter('~', 'plugin_output', 'boom'))
        self.assertFalse(stack._stack[-1].exact)
        stack.not_elements()
        self.assertEqual('1 = 1', stack.result().clause)
        # an exact filter can be negated
        stack.put(sqlite_mod.make_sql_filter('=', 'state', 2))
        stack.not_elements()
        self.assertEqual('(NOT state = ?)', stack.result().clause)

    def test_untranslatable_filters(self):
        for args in (('~', 'message', '^SERVICE'), ('>=', 'current_host_contacts', 'admin'),
                     ('=', 'state', 'abc'), ('!~', 'host_name', 'x')):
            self.assertEqual('1 = 1', sqlite_mod.make_sql_filter(*args).clause, args)


class TestLogstoreSqliteLivestatus(ShinkenTest):
    """Store log broks and answer GET log queries like Thruk sends them."""

    aggressive = '0'

    def setUp(self):
        self.setup_with_file('etc/shinken_1r_1h_1s.cfg')
        self.tmpdir = tempfile.mkdtemp()
        self.store = make_store(self.tmpdir, use_aggressive_sql=self.aggressive)
        # Regenerate the monitored objects like the broker does.
        self.rg = livestatus_mod.LiveStatusRegenerator()
        cache = livestatus_mod.LiveStatusQueryCache()
        cache.disable()
        self.rg.register_cache(cache)
        datamgr.load(self.rg)
        self.sched.brokers['Default-Broker'] = {'broks': [], 'has_full_broks': False}
        self.sched.fill_initial_broks('Default-Broker')
        for brok in self.sched.brokers.pop('Default-Broker')['broks']:
            brok.prepare()
            self.rg.manage_brok(brok)
        self.livestatus = livestatus_mod.LiveStatus(datamgr, cache, self.store, '', queue.Queue())

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def query(self, request):
        output, _ = self.livestatus.handle_request(request)
        return ''.join(part.decode() if isinstance(part, bytes) else part for part in output)

    def feed(self, now):
        lines = [
            '[%d] SERVICE ALERT: test_host_0;test_ok_0;CRITICAL;HARD;3;Échec de la sonde' % (now - 30),
            '[%d] HOST ALERT: test_host_0;DOWN;HARD;3;Hôte injoignable' % (now - 20),
            '[%d] SERVICE NOTIFICATION: test_contact;test_host_0;test_ok_0;CRITICAL;notify-service;boom' % (now - 10),
            '[%d] EXTERNAL COMMAND: DISABLE_NOTIFICATIONS' % (now - 5),
            '[%d] INFO: [scheduler-master] not a monitoring line' % now,
            '[%d] HOST ALERT: test_host_0;UP;HARD;1;old line' % (now - 4000),
        ]
        for line in lines:
            self.store.manage_brok(log_brok(line))
        self.store.commit()

    def test_get_log_thruk_like(self):
        now = int(time.time())
        self.feed(now)
        # Event log page: time range + classes
        out = self.query(
            'GET log\nColumns: class time type state host_name service_description plugin_output\n'
            'Filter: time >= %d\nFilter: time <= %d\n'
            'Filter: class = 1\nFilter: class = 3\nOr: 2\nOutputFormat: json\n\n' % (now - 3600, now))
        rows = json.loads(out)
        self.assertEqual([1, 1, 3], [r[0] for r in rows])
        self.assertEqual(['SERVICE ALERT', 'HOST ALERT', 'SERVICE NOTIFICATION'],
                         [r[2] for r in rows])
        self.assertEqual('Échec de la sonde', rows[0][6])
        self.assertEqual('Hôte injoignable', rows[1][6])
        self.assertEqual([2, 1, 2], [r[3] for r in rows])
        self.assertEqual('boom', rows[2][6])

    def test_get_log_host_filter_and_regex(self):
        now = int(time.time())
        self.feed(now)
        out = self.query(
            'GET log\nColumns: type plugin_output current_host_name\n'
            'Filter: time >= %d\nFilter: host_name = test_host_0\n'
            'Filter: plugin_output ~ ^H\nOutputFormat: json\n\n' % (now - 3600))
        self.assertEqual([['HOST ALERT', 'Hôte injoignable', 'test_host_0']], json.loads(out))
        # Negation of a regex must not lose lines in SQL
        out = self.query(
            'GET log\nColumns: type\nFilter: time >= %d\nFilter: type ~ ALERT\nNegate:\n'
            'OutputFormat: json\n\n' % (now - 3600))
        self.assertEqual([['SERVICE NOTIFICATION'], ['EXTERNAL COMMAND']], json.loads(out))

    def test_stats_and_limit(self):
        now = int(time.time())
        self.feed(now)
        out = self.query('GET log\nFilter: time >= %d\nStats: class = 1\nStats: class = 3\n'
                         'OutputFormat: json\n\n' % (now - 3600))
        self.assertEqual([[2, 1]], json.loads(out))
        out = self.query('GET log\nColumns: time\nFilter: time >= %d\nLimit: 2\n'
                         'OutputFormat: json\n\n' % (now - 3600))
        self.assertEqual(2, len(json.loads(out)))

    def test_filters_do_not_leak_between_queries(self):
        now = int(time.time())
        self.feed(now)
        # A dangling filter (as left by a cached query) must be dropped.
        self.store.add_filter('=', 'host_name', 'nobody')
        out = self.query('GET log\nColumns: type\nFilter: time >= %d\nOutputFormat: json\n\n'
                         % (now - 3600))
        self.assertEqual(4, len(json.loads(out)))


class TestLogstoreSqliteLivestatusAggressive(TestLogstoreSqliteLivestatus):
    aggressive = '1'


class TestLogstoreSqliteFiles(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def count(self, path):
        conn = sqlite3.connect(path)
        try:
            return conn.execute('SELECT COUNT(*) FROM logs').fetchone()[0]
        finally:
            conn.close()

    def test_archive_and_purge(self):
        store = make_store(self.tmpdir, max_logs_age='30d')
        now = time.time()
        for days in (40, 2, 1, 0):
            stamp = int(now - days * 86400)
            store.manage_brok(log_brok('[%d] HOST ALERT: h;DOWN;HARD;1;%d days ago' % (stamp, days)))
        store.commit()
        os.makedirs(store.archive_path)
        old_day = datetime.date.today() - datetime.timedelta(days=60)
        expired = os.path.join(store.archive_path, 'livestatus-%s.db' % old_day.isoformat())
        open(expired, 'w').close()

        store.log_db_do_archive(now)

        self.assertFalse(os.path.exists(expired))
        archives = store.list_archives()
        self.assertEqual(2, len(archives))
        self.assertEqual([1, 1], [self.count(path) for _, path in archives])
        today_start = sqlite_mod._local_midnight(now)
        remaining = store.execute('SELECT time FROM logs')
        self.assertTrue(all(row[0] >= today_start for row in remaining))

        # Queries read the relevant archives and the current database.
        store.add_filter('>=', 'time', int(now - 3 * 86400))
        lines = list(store.get_live_data_log())
        self.assertEqual(['2 days ago', '1 days ago', '0 days ago'],
                         [line.plugin_output for line in lines])
        store.add_filter('>=', 'time', int(now - 3600))
        self.assertEqual(['0 days ago'], [l.plugin_output for l in store.get_live_data_log()])
        store.close()

    def test_reads_python2_database_with_latin1_text(self):
        path = os.path.join(self.tmpdir, 'livestatus.db')
        store = make_store(self.tmpdir)
        now = int(time.time())
        conn = sqlite3.connect(path)
        message = ('[%d] HOST ALERT: h;DOWN;HARD;1;h\xf4te' % now).encode('latin-1')
        conn.execute("INSERT INTO logs VALUES (1, 1, 1, '', '', '', 'h', 1, CAST(? AS TEXT), '', "
                     "CAST(? AS TEXT), '', 1, 'HARD', ?, 'HOST ALERT')",
                     (message, 'h\xf4te'.encode('latin-1'), now))
        conn.commit()
        conn.close()
        lines = list(store.get_live_data_log())
        self.assertEqual(['h\xf4te'], [line.plugin_output for line in lines])
        store.close()

    def test_read_only_store_does_not_write(self):
        store = make_store(self.tmpdir, read_only='1')
        store.manage_brok(log_brok('[%d] HOST ALERT: h;DOWN;HARD;1;x' % time.time()))
        self.assertEqual([], list(store.get_live_data_log()))
        store.close()


if __name__ == '__main__':
    unittest.main()
