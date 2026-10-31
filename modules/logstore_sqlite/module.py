#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2012:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
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

"""SQLite log store for the Livestatus broker module.

This is a Python 3 port of the historical ``mod-logstore-sqlite`` module.
It is loaded as a sub-module of ``livestatus`` and:

* stores every monitoring log line (alerts, notifications, state changes,
  external commands...) received as a ``log`` brok in a SQLite database;
* moves, once a day, the lines of the previous days into one archive
  database per day (``<archive_path>/<name>-YYYY-MM-DD.db``);
* deletes the lines and archives older than ``max_logs_age``;
* answers the ``GET log`` Livestatus queries (used by Thruk for event logs,
  alert history, notifications and availability reports).

The table layout is the one of the Python 2 module, so databases and
archives produced by Shinken 2.4 can be reused as is.

Filtering is done in two steps: an SQL ``WHERE`` clause preselects the
candidate lines, then Livestatus applies the exact ``Filter:`` semantics
in Python. The SQL clause is therefore built to always select a *superset*
of the expected lines: filters which cannot be translated faithfully to SQL
(regular expressions, unknown columns...) are replaced by an always-true
condition. By default (``use_aggressive_sql 0``) only the time range is
given to SQLite, which is enough for the time-bounded queries sent by Thruk.
"""

import datetime
import os
import re
import sqlite3
import sys
import time
from urllib.parse import quote

from shinken.basemodule import BaseModule
from shinken.log import logger

properties = {
    'daemons': ['livestatus'],
    'type': 'logstore_sqlite',
    'external': False,
    'phases': ['running'],
}

DEFAULT_DATABASE_FILE = '/var/lib/shinken/livestatus.db'
DEFAULT_MAX_LOGS_AGE = 365  # days, when the parameter cannot be parsed
JOURNAL_MODES = ('delete', 'truncate', 'persist', 'memory', 'wal', 'off')

# Table layout, identical to the Python 2 module (order matters: rows are
# inserted with "INSERT INTO logs VALUES (...)" and archived with SELECT *).
COLUMNS = ('logobject', 'attempt', 'class', 'command_name', 'comment',
           'contact_name', 'host_name', 'lineno', 'message', 'options',
           'plugin_output', 'service_description', 'state', 'state_type',
           'time', 'type')
INT_COLUMNS = frozenset(('logobject', 'attempt', 'class', 'lineno', 'state', 'time'))
TEXT_COLUMNS = frozenset(COLUMNS) - INT_COLUMNS

_REGEX_META = re.compile(r'[.^$*+?{}\[\]\\|()]')
_ARCHIVE_DATE = re.compile(r'-(\d{4})-(\d{2})-(\d{2})\.db$')


def get_instance(plugin):
    """Called by the modules manager to build the module instance."""
    logger.info("[Logstore SQLite] Get a SQLite log store for plugin %s", plugin.get_name())
    return LiveStatusLogStoreSqlite(plugin)


def parse_max_logs_age(value):
    """Convert a ``max_logs_age`` value to a number of days.

    Accepted formats: ``<n>`` or ``<n>d`` (days), ``<n>w`` (weeks),
    ``<n>m`` (months, 31 days) and ``<n>y`` (years, 365 days).
    ``0`` disables the purge (lines are kept forever).
    """
    match = re.match(r'^\s*(\d+)\s*([dwmy]?)\s*$', str(value))
    if match is None:
        logger.warning("[Logstore SQLite] Wrong format for max_logs_age %r: must be "
                       "<number>[d|w|m|y]; using %d days", value, DEFAULT_MAX_LOGS_AGE)
        return DEFAULT_MAX_LOGS_AGE
    number, unit = int(match.group(1)), match.group(2)
    return number * {'': 1, 'd': 1, 'w': 7, 'm': 31, 'y': 365}[unit]


def _decode_text(raw):
    """sqlite3 text factory tolerant to non UTF-8 text.

    Databases written by the Python 2 module may contain latin-1 plugin
    outputs: decode them instead of failing the whole query.
    """
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def _escape_like(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _local_midnight(timestamp):
    """Unix timestamp of the local midnight starting the day of ``timestamp``."""
    day = datetime.date.fromtimestamp(timestamp)
    return int(time.mktime(datetime.datetime(day.year, day.month, day.day).timetuple()))


def _next_midnight(midnight):
    day = datetime.date.fromtimestamp(midnight) + datetime.timedelta(days=1)
    return int(time.mktime(datetime.datetime(day.year, day.month, day.day).timetuple()))


class LiveStatusLogStoreError(Exception):
    """Raised when the SQLite database cannot be used."""


class SqlFilter(object):
    """One node of the SQL filter tree built from Livestatus filters.

    :ivar clause: SQL condition (with ``?`` placeholders)
    :ivar values: values for the placeholders
    :ivar exact: True when ``clause`` selects exactly the lines matching
        the Livestatus filter; False when it only selects a superset (such a
        clause must never be negated)
    :ivar low: smallest acceptable ``time`` value, or None
    :ivar high: greatest acceptable ``time`` value, or None
    """

    __slots__ = ('clause', 'values', 'exact', 'low', 'high')

    def __init__(self, clause, values=(), exact=True, low=None, high=None):
        self.clause = clause
        self.values = tuple(values)
        self.exact = exact
        self.low = low
        self.high = high

    @classmethod
    def always_true(cls, exact=False):
        return cls('1 = 1', (), exact)

    def __repr__(self):
        return '<SqlFilter %s %r exact=%s time=[%s, %s]>' % (
            self.clause, self.values, self.exact, self.low, self.high)


def _combine(filters, operator):
    """AND/OR the given SqlFilter nodes together."""
    if len(filters) == 1:
        return filters[0]
    clause = '(' + (' %s ' % operator).join(f.clause for f in filters) + ')'
    values = sum((f.values for f in filters), ())
    exact = all(f.exact for f in filters)
    lows = [f.low for f in filters]
    highs = [f.high for f in filters]
    if operator == 'AND':
        low = max([l for l in lows if l is not None], default=None)
        high = min([h for h in highs if h is not None], default=None)
    else:
        low = None if None in lows else min(lows)
        high = None if None in highs else max(highs)
    return SqlFilter(clause, values, exact, low, high)


def make_sql_filter(operator, attribute, reference):
    """Translate one Livestatus ``Filter:`` line into a SqlFilter node."""
    column = attribute
    if column == 'logclass':
        column = 'class'
    if column not in COLUMNS:
        return SqlFilter.always_true()

    if column in INT_COLUMNS:
        try:
            value = int(reference)
        except (TypeError, ValueError):
            return SqlFilter.always_true()
        if operator not in ('=', '!=', '<', '>', '<=', '>='):
            return SqlFilter.always_true()
        node = SqlFilter('%s %s ?' % (column, operator), (value,))
        if column == 'time':
            if operator in ('=', '>='):
                node.low = value
            elif operator == '>':
                node.low = value + 1
            if operator in ('=', '<='):
                node.high = value
            elif operator == '<':
                node.high = value - 1
        return node

    reference = '' if reference is None else str(reference)
    if operator == '=':
        return SqlFilter('%s = ?' % column, (reference,))
    if operator == '!=':
        return SqlFilter('%s != ?' % column, (reference,))
    if operator == '=~' and reference.isascii():
        # LIKE without wildcard is an ASCII case-insensitive equality.
        return SqlFilter("%s LIKE ? ESCAPE '\\'" % column, (_escape_like(reference),), exact=False)
    if operator in ('~', '~~') and not _REGEX_META.search(reference):
        # A regex without meta-character is a plain substring search.
        # LIKE ignores ASCII case, so it is a superset of both operators,
        # except for case-insensitive search of non ASCII text.
        if operator == '~' or reference.isascii():
            return SqlFilter("%s LIKE ? ESCAPE '\\'" % column,
                             ('%' + _escape_like(reference) + '%',), exact=False)
    return SqlFilter.always_true()


class SqlFilterStack(object):
    """Stack of SqlFilter nodes mirroring the Livestatus filter stack."""

    def __init__(self):
        self._stack = []

    def __len__(self):
        return len(self._stack)

    def clear(self):
        del self._stack[:]

    def put(self, node):
        self._stack.append(node)

    def pop(self):
        """Pop the top node, or an always-true one when the stack is empty
        (same behaviour as the Python filter stack of Livestatus)."""
        if self._stack:
            return self._stack.pop()
        return SqlFilter.always_true(exact=True)

    def and_elements(self, num):
        num = int(num)
        if num > 1:
            self.put(_combine([self.pop() for _ in range(num)], 'AND'))

    def or_elements(self, num):
        num = int(num)
        if num > 1:
            self.put(_combine([self.pop() for _ in range(num)], 'OR'))

    def not_elements(self):
        node = self.pop()
        if node.exact:
            self.put(SqlFilter('(NOT %s)' % node.clause, node.values, True))
        else:
            # NOT(superset) would be a subset: we cannot preselect anything.
            self.put(SqlFilter.always_true())

    def result(self):
        """AND all the remaining nodes (Livestatus implicit AND) and empty
        the stack."""
        nodes = self._stack[:] or [SqlFilter.always_true(exact=True)]
        self.clear()
        return _combine(nodes, 'AND')


class LiveStatusLogStoreSqlite(BaseModule):
    """Livestatus log store keeping the monitoring logs in SQLite.

    Configuration parameters (all optional):

    ``database_file``
        current database (default ``/var/lib/shinken/livestatus.db``)
    ``archive_path``
        directory of the daily archives (default ``<dir of database_file>/archives``)
    ``max_logs_age``
        retention, ``<n>[d|w|m|y]`` (default ``1y``); ``0`` keeps everything
    ``use_aggressive_sql``
        ``1`` to also give the non-time filters to SQLite (default ``0``)
    ``read_only``
        ``1`` to only read the database (another broker writes it)
    ``journal_mode``
        SQLite journal mode (default ``wal``)
    """

    CURSOR_ARRAYSIZE = 1024

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.plugins = []
        self.app = None
        self.database_file = getattr(modconf, 'database_file', DEFAULT_DATABASE_FILE)
        self.archive_path = getattr(modconf, 'archive_path', '') or os.path.join(
            os.path.dirname(os.path.abspath(self.database_file)), 'archives')
        self.max_logs_age = parse_max_logs_age(getattr(modconf, 'max_logs_age', '1y'))
        self.use_aggressive_sql = str(getattr(modconf, 'use_aggressive_sql', '0')) == '1'
        self.read_only = str(getattr(modconf, 'read_only', '0')) == '1'
        journal_mode = str(getattr(modconf, 'journal_mode', 'wal')).lower()
        if journal_mode not in JOURNAL_MODES:
            logger.warning("[Logstore SQLite] Unknown journal_mode %r, using 'wal'", journal_mode)
            journal_mode = 'wal'
        self.journal_mode = journal_mode
        self.dbconn = None
        self.next_log_db_commit = 0
        self.next_log_db_rotate = 0
        self.sql_filter_stack = SqlFilterStack()
        self._logline_cls = None
        self._logclass_invalid = -1

    # ------------------------------------------------------------------
    # Livestatus integration
    # ------------------------------------------------------------------
    def load(self, app):
        """Called by the Livestatus module with itself as ``app``."""
        self.app = app

    def init(self):
        pass

    def _livestatus(self):
        """Return the ``Logline`` class and ``LOGCLASS_INVALID`` of the
        Livestatus module this store is attached to.

        The very same class object must be used: the Livestatus mapping
        decorates it with the ``lsm_*`` column accessors.
        """
        if self._logline_cls is None:
            source = None
            if self.app is not None:
                source = sys.modules.get(type(self.app).__module__)
            if source is None or not hasattr(source, 'Logline'):
                from shinken.modulesctx import modulesctx
                source = modulesctx.get_module('livestatus')
            self._logline_cls = source.Logline
            self._logclass_invalid = source.LOGCLASS_INVALID
        return self._logline_cls

    # ------------------------------------------------------------------
    # Database handling
    # ------------------------------------------------------------------
    def _connect(self, path, read_only=False):
        if read_only:
            uri = 'file:%s?mode=ro' % quote(os.path.abspath(path))
            conn = sqlite3.connect(uri, uri=True, timeout=30)
        else:
            conn = sqlite3.connect(path, timeout=30)
        conn.text_factory = _decode_text
        return conn

    def open(self):
        """Open (or re-open) the current database.

        Called once per thread: Livestatus client threads work on a copy of
        this object and open their own connection.
        """
        if self.dbconn is not None:
            try:
                self.dbconn.close()
            except sqlite3.Error:
                pass
            self.dbconn = None
        directory = os.path.dirname(os.path.abspath(self.database_file))
        if not self.read_only and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        try:
            self.dbconn = self._connect(self.database_file)
        except sqlite3.Error as err:
            raise LiveStatusLogStoreError('cannot open %s: %s' % (self.database_file, err))
        self.sql_filter_stack = SqlFilterStack()
        now = time.time()
        self.next_log_db_commit = now
        self.next_log_db_rotate = now
        logger.debug("[Logstore SQLite] Opened %s", self.database_file)

    def close(self):
        if self.dbconn is not None:
            try:
                self.dbconn.commit()
            finally:
                self.dbconn.close()
                self.dbconn = None

    def execute(self, cmd, values=()):
        """Execute a statement on the current database; SELECTs return all rows."""
        try:
            cursor = self.dbconn.execute(cmd, values)
            if cmd.lstrip().upper().startswith(('SELECT', 'PRAGMA')):
                return cursor.fetchall()
            return cursor.rowcount
        except sqlite3.Error as err:
            logger.error("[Logstore SQLite] SQL error on %s: %s", cmd, err)
            raise LiveStatusLogStoreError(err)

    def commit(self):
        """Commit, retrying for up to 60s while the database is locked."""
        start = time.time()
        while True:
            try:
                self.dbconn.commit()
                return
            except sqlite3.OperationalError:
                if time.time() - start > 60:
                    raise
                time.sleep(.01)

    @staticmethod
    def _create_table(conn, schema='main'):
        conn.execute("""CREATE TABLE IF NOT EXISTS %s.logs (
                logobject INT,
                attempt INT,
                class INT,
                command_name VARCHAR(64),
                comment VARCHAR(256),
                contact_name VARCHAR(64),
                host_name VARCHAR(64),
                lineno INT,
                message VARCHAR(512),
                options VARCHAR(512),
                plugin_output VARCHAR(256),
                service_description VARCHAR(64),
                state INT,
                state_type VARCHAR(10),
                time INT,
                type VARCHAR(64)
        )""" % schema)
        conn.execute("CREATE INDEX IF NOT EXISTS %s.logs_time ON logs (time)" % schema)
        conn.execute("CREATE INDEX IF NOT EXISTS %s.logs_host_name ON logs (host_name)" % schema)

    def prepare_log_db_table(self):
        """Create the ``logs`` table and its indexes if needed."""
        if self.read_only:
            return
        try:
            self._create_table(self.dbconn)
            self.dbconn.execute("PRAGMA journal_mode=%s" % self.journal_mode)
            self.commit()
        except sqlite3.Error as err:
            raise LiveStatusLogStoreError('cannot prepare %s: %s' % (self.database_file, err))

    def commit_and_rotate_log_db(self):
        """Periodic housekeeping, called by the Livestatus main loop.

        Commits the pending inserts (at most once per second) and, every
        day at 00:05, archives the lines of the previous days and purges
        the expired ones. We wait until 00:05 because in a distributed
        setup lines dated from yesterday may still arrive after midnight.
        """
        if self.read_only or self.dbconn is None:
            return
        now = time.time()
        if self.next_log_db_commit <= now:
            self.commit()
            self.next_log_db_commit = now + 1
        if self.next_log_db_rotate <= now:
            logger.info("[Logstore SQLite] Archiving the log database")
            self.log_db_do_archive()
            today0005 = _local_midnight(now) + 5 * 60
            if now < today0005:
                self.next_log_db_rotate = today0005
            else:
                self.next_log_db_rotate = _next_midnight(_local_midnight(now)) + 5 * 60
            logger.info("[Logstore SQLite] Next archiving at %s",
                        time.asctime(time.localtime(self.next_log_db_rotate)))

    def archive_file(self, day_start):
        """Path of the archive database holding the day starting at ``day_start``."""
        base = os.path.splitext(os.path.basename(self.database_file))[0]
        day = datetime.date.fromtimestamp(day_start)
        return os.path.join(self.archive_path, '%s-%s.db' % (base, day.strftime('%Y-%m-%d')))

    def list_archives(self):
        """Return ``[(date, path)]`` of the existing archives, oldest first."""
        base = os.path.splitext(os.path.basename(self.database_file))[0]
        result = []
        try:
            names = os.listdir(self.archive_path)
        except OSError:
            return result
        for name in names:
            if not name.startswith(base + '-'):
                continue
            match = _ARCHIVE_DATE.search(name)
            if match and name == '%s-%s-%s-%s.db' % ((base,) + match.groups()):
                try:
                    day = datetime.date(*(int(g) for g in match.groups()))
                except ValueError:
                    continue
                result.append((day, os.path.join(self.archive_path, name)))
        result.sort()
        return result

    def log_db_do_archive(self, now=None):
        """Move the lines of the previous days to daily archives and purge.

        * lines older than ``max_logs_age`` are deleted;
        * every other line dated before today 00:00 is moved to the archive
          of its day;
        * archives older than ``max_logs_age`` are removed.
        """
        if self.read_only:
            return
        now = time.time() if now is None else now
        today = _local_midnight(now)
        cutoff = None
        if self.max_logs_age > 0:
            cutoff_day = datetime.date.fromtimestamp(today) - datetime.timedelta(days=self.max_logs_age)
            cutoff = int(time.mktime(datetime.datetime(
                cutoff_day.year, cutoff_day.month, cutoff_day.day).timetuple()))
        moved = 0
        try:
            self.commit()
            if cutoff is not None:
                moved += self.execute("DELETE FROM logs WHERE time < ?", (cutoff,))
                self.commit()
            while True:
                row = self.execute("SELECT MIN(time) FROM logs WHERE time < ?", (today,))
                mintime = row[0][0] if row else None
                if mintime is None:
                    break
                start = _local_midnight(mintime)
                stop = _next_midnight(start)
                archive = self.archive_file(start)
                os.makedirs(self.archive_path, exist_ok=True)
                logger.info("[Logstore SQLite] Moving logs from %s to %s",
                            time.strftime('%Y-%m-%d', time.localtime(start)), archive)
                self.dbconn.execute("ATTACH DATABASE ? AS archive", (archive,))
                try:
                    self._create_table(self.dbconn, 'archive')
                    self.dbconn.execute("INSERT INTO archive.logs SELECT * FROM logs "
                                        "WHERE time >= ? AND time < ?", (start, stop))
                    moved += self.dbconn.execute("DELETE FROM logs WHERE time >= ? AND time < ?",
                                                 (start, stop)).rowcount
                    self.commit()
                except Exception:
                    self.dbconn.rollback()
                    raise
                finally:
                    self.dbconn.execute("DETACH DATABASE archive")
            if moved:
                self.dbconn.execute('VACUUM')
        except (sqlite3.Error, OSError, LiveStatusLogStoreError) as err:
            logger.error("[Logstore SQLite] Archiving failed: %s", err)
            try:
                self.dbconn.rollback()
            except sqlite3.Error:
                pass
        if cutoff is not None:
            cutoff_date = datetime.date.fromtimestamp(cutoff)
            for day, path in self.list_archives():
                if day < cutoff_date:
                    logger.info("[Logstore SQLite] Removing expired archive %s", path)
                    try:
                        os.remove(path)
                    except OSError as err:
                        logger.error("[Logstore SQLite] Cannot remove %s: %s", path, err)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def manage_log_brok(self, brok):
        """Store the monitoring log line carried by a ``log`` brok."""
        if self.read_only:
            return
        line = brok.data['log']
        logline_cls = self._livestatus()
        try:
            logline = logline_cls(line=line)
        except Exception as err:
            logger.debug("[Logstore SQLite] Unparsable log line %r: %s", line, err)
            return
        if logline.logclass == self._logclass_invalid:
            return
        try:
            self.dbconn.execute('INSERT INTO logs VALUES (%s)' % ', '.join('?' * len(COLUMNS)),
                                logline.as_tuple())
        except sqlite3.Error as err:
            logger.error("[Logstore SQLite] Cannot store a log line: %s", err)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------
    def reset_filters(self):
        """Forget the filters of a previous query."""
        self.sql_filter_stack.clear()

    def add_filter(self, operator, attribute, reference):
        self.sql_filter_stack.put(make_sql_filter(operator, attribute, reference))

    def add_filter_and(self, andnum):
        self.sql_filter_stack.and_elements(andnum)

    def add_filter_or(self, ornum):
        self.sql_filter_stack.or_elements(ornum)

    def add_filter_not(self):
        self.sql_filter_stack.not_elements()

    def build_where(self):
        """Return ``(clause, values, low, high)`` for the pending filters and
        reset the filter stack."""
        node = self.sql_filter_stack.result()
        if self.use_aggressive_sql:
            clause, values = node.clause, node.values
        else:
            parts, values = [], []
            if node.low is not None:
                parts.append('time >= ?')
                values.append(node.low)
            if node.high is not None:
                parts.append('time <= ?')
                values.append(node.high)
            clause = ' AND '.join(parts) or '1 = 1'
        return clause, tuple(values), node.low, node.high

    def relevant_archives(self, low, high):
        """Archives which may hold lines between ``low`` and ``high``."""
        first = datetime.date.fromtimestamp(low) if low is not None else None
        last = datetime.date.fromtimestamp(high) if high is not None else None
        return [path for day, path in self.list_archives()
                if (first is None or day >= first) and (last is None or day <= last)]

    def _select(self, conn, clause, values):
        logline_cls = self._livestatus()
        cursor = conn.execute('SELECT * FROM logs WHERE %s ORDER BY time, lineno' % clause, values)
        cursor.arraysize = self.CURSOR_ARRAYSIZE
        description = cursor.description
        while True:
            rows = cursor.fetchmany()
            if not rows:
                break
            for row in rows:
                yield logline_cls(sqlite_cursor=description, sqlite_row=row)

    def get_live_data_log(self):
        """Yield the log lines matching the pending filters (a superset of
        them: Livestatus applies the exact filters afterwards), oldest first."""
        clause, values, low, high = self.build_where()
        for archive in self.relevant_archives(low, high):
            try:
                conn = self._connect(archive, read_only=True)
            except sqlite3.Error as err:
                logger.error("[Logstore SQLite] Cannot open archive %s: %s", archive, err)
                continue
            try:
                for line in self._select(conn, clause, values):
                    yield line
            except sqlite3.Error as err:
                logger.error("[Logstore SQLite] Cannot read archive %s: %s", archive, err)
            finally:
                conn.close()
        if self.dbconn is not None:
            try:
                for line in self._select(self.dbconn, clause, values):
                    yield line
            except sqlite3.Error as err:
                logger.error("[Logstore SQLite] Cannot read %s: %s", self.database_file, err)
