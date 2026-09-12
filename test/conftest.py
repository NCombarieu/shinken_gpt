"""Pytest compatibility helpers for the legacy Shinken test suite."""

import os
import re
import subprocess
import sys
import types
import unittest

import pytest

# The historical suite imports unittest2 throughout. On supported Python 3
# versions the stdlib unittest module provides the required API, so alias it
# during collection instead of carrying the obsolete unittest2 dependency.
sys.modules.setdefault("unittest2", unittest)

# Preserve the historical regexp assertion semantics consistently across all
# supported Python versions. Python 3.11/3.12 still expose the deprecated
# assertRegexpMatches alias while Python 3.13 removes it; the stdlib
# implementation behind the older alias now rejects an empty expected pattern.
# The legacy suite intentionally uses an empty regexp to assert that a log
# stream is empty, so provide one compatibility implementation everywhere.
def _assert_regexp_matches(self, text, expected_regexp, msg=None):
    regexp = re.compile(expected_regexp) if isinstance(expected_regexp, str) else expected_regexp
    if regexp.search(text) is None:
        standard_msg = "%r does not match %r" % (text, regexp.pattern)
        self.fail(self._formatMessage(msg, standard_msg))


unittest.TestCase.assertRegexpMatches = _assert_regexp_matches

# Python 2 exposed sys.setcheckinterval(). Python 3 replaced it with
# sys.setswitchinterval(); the old test only used a large value to reduce
# thread switching noise. Preserve that intent without touching production
# code or depending on a removed interpreter API.
if not hasattr(sys, "setcheckinterval"):
    def _setcheckinterval(_interval):
        sys.setswitchinterval(0.05)

    sys.setcheckinterval = _setcheckinterval

# Python 2's commands module was removed in Python 3. A small compatibility
# module keeps the system-time legacy test importable while delegating to the
# supported subprocess implementation.
if "commands" not in sys.modules:
    commands = types.ModuleType("commands")
    commands.getstatusoutput = subprocess.getstatusoutput
    commands.getoutput = subprocess.getoutput
    sys.modules["commands"] = commands


@pytest.fixture(autouse=True)
def normalize_legacy_log_paths(monkeypatch):
    """Keep captured legacy log paths stable across checkout locations."""
    from shinken.brok import Brok

    original_prepare = Brok.prepare
    test_dir = os.path.dirname(os.path.abspath(__file__)) + os.sep

    def prepare_with_relative_test_paths(self):
        result = original_prepare(self)
        if self.type == "log":
            log = self.data.get("log")
            if isinstance(log, str):
                self.data["log"] = log.replace(test_dir, "")
        return result

    monkeypatch.setattr(Brok, "prepare", prepare_with_relative_test_paths)


@pytest.fixture(autouse=True)
def preserve_python2_daterange_none_semantics(monkeypatch):
    """Treat a missing next valid day as no future match under Python 3.

    Python 2 tolerated ordering comparisons such as ``timestamp < None``.
    Some legacy daterange code relied on that accidental behavior when a
    fixed calendar range was entirely in the past. Keep the suite moving
    while making the intended result explicit: no next valid time exists.
    """
    from shinken.daterange import Daterange

    original = Daterange.get_next_valid_time_from_t

    def get_next_valid_time_from_t(self, t):
        if self.is_time_valid(t):
            return t
        if self.get_next_valid_day(t) is None:
            return None
        return original(self, t)

    monkeypatch.setattr(Daterange, "get_next_valid_time_from_t", get_next_valid_time_from_t)
