#!/usr/bin/env python3
"""Setuptools compatibility entry point for Shinken.

System configuration and service-manager integration deliberately live outside
Python package installation. A wheel must install application code and runtime
dependencies without mutating /etc, /var, users/groups, or init scripts.
"""

from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent

setup(
    name="Shinken",
    version="2.4.3",
    packages=find_packages(),
    description="Monitoring framework compatible with Nagios configuration and plugins",
    long_description=(ROOT / "README.rst").read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    author="Gabes Jean and Shinken contributors",
    license="AGPL-3.0-or-later",
    url="https://github.com/shinken-monitoring/shinken",
    python_requires=">=3.11",
    install_requires=[
        "Bottle>=0.13.4,<0.14",
        "cheroot>=11.1.2,<12",
        "pycurl>=7.45.2",
        "Pyro5>=5.15",
    ],
    extras_require={
        "setproctitle": ["setproctitle>=1.3"],
    },
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Networking :: Monitoring",
    ],
)
