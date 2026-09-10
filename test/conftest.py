"""Pytest compatibility helpers for the legacy Shinken test suite."""

import subprocess
import sys
import types
import unittest

# The historical suite imports unittest2 throughout. On supported Python 3
# versions the stdlib unittest module provides the required API, so alias it
# during collection instead of carrying the obsolete unittest2 dependency.
sys.modules.setdefault("unittest2", unittest)

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
