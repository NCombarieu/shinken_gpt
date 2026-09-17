===================================
Shinken (Python 3 / Podman fork)
===================================

This is a fork of `Shinken <https://github.com/naparuba/shinken>`_, a
Nagios-compatible monitoring framework written in Python. The upstream
project stayed on Python 2; this fork (branch ``modernize/podman-python3``)
ports the core, its six daemons, and a real Livestatus module to
**Python 3.11+**, and runs entirely as **Podman containers**.

Shinken stays backwards-compatible with the Nagios configuration format
and plugins.

Documentation
=============

Full documentation lives in `doc/ <doc/README.md>`_:

**Getting started:**

* `DEVELOPMENT.md <DEVELOPMENT.md>`_ — set up dev environment, run tests, contribute
* `doc/installation.md <doc/installation.md>`_ — clone, build, run in containers
* `doc/architecture.md <doc/ARCHITECTURE.md>`_ — system design, daemons, communication

**Operations & Configuration:**

* `doc/configuration.md <doc/configuration.md>`_ — hosts, services, templates,
  container-specific networking
* `doc/exploitation.md <doc/exploitation.md>`_ — day-to-day operations
  (reload, force check, acknowledge, downtime)
* `doc/database.md <doc/DATABASE.md>`_ — monitoring logs storage (SQLite, MySQL, Oracle)
* `doc/metrics.md <doc/METRICS.md>`_ — experimental metrics integration status (InfluxDB + Grafana)
* `doc/logging.md <doc/LOGGING.md>`_ — structured JSON logging for aggregation
* `doc/livestatus-thruk.md <doc/livestatus-thruk.md>`_ — integrating Thruk
  web UI via Livestatus
* `doc/quickstart-metrics.md <doc/QUICKSTART-METRICS.md>`_ — metrics availability and limitations

**Reference:**

* `doc/presentation.md <doc/presentation.md>`_ — what Shinken is, what this
  fork changes
* `doc/depannage.md <doc/depannage.md>`_ — real bugs found and fixed in this fork
* `DEPLOYMENT.md <DEPLOYMENT.md>`_ — chronological deployment journal for a specific server

Quick start
===========

.. code-block:: bash

  git clone git@github.com:NCombarieu/shinken_gpt.git
  cd shinken_gpt
  git checkout modernize/podman-python3
  sudo pip install podman-compose   # if not already available
  podman-compose build
  podman-compose up -d

See `doc/installation.md <doc/installation.md>`_ for prerequisites and
verification steps.

Upstream
========

The original project: https://github.com/naparuba/shinken

Bugs specific to this fork's Python 3 / container port should be filed
against ``NCombarieu/shinken_gpt``, not upstream.
