#!/usr/bin/env python3
"""Setuptools compatibility entry point for Shinken.

System configuration and service-manager integration deliberately live outside
Python package installation. A wheel must install application code and runtime
dependencies without mutating /etc, /var, users/groups, or init scripts.

All metadata, including the package list, is defined in pyproject.toml
(PEP 621) and setup.cfg (scripts). This file only exists for tools that still
call ``setup.py`` directly.
"""

from setuptools import setup

setup()
