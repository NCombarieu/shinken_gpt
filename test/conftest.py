"""Pytest compatibility helpers for the legacy Shinken test suite."""

import sys
import unittest

# The historical suite imports unittest2 throughout. On supported Python 3
# versions the stdlib unittest module provides the required API, so alias it
# during collection instead of carrying the obsolete unittest2 dependency.
sys.modules.setdefault("unittest2", unittest)
