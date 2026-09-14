#!/usr/bin/env python3
"""Setuptools compatibility entry point for Shinken.

System configuration and service-manager integration deliberately live outside
Python package installation. A wheel must install application code and runtime
dependencies without mutating /etc, /var, users/groups, or init scripts.

All metadata is defined in pyproject.toml via PEP 621.
This file exists only for backward compatibility with older build tools.
"""

from setuptools import find_packages, setup

setup(packages=find_packages())
