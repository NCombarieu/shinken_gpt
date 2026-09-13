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

* `doc/presentation.md <doc/presentation.md>`_ — what Shinken is, and what
  this fork changes
* `doc/installation.md <doc/installation.md>`_ — clone, build, run
* `doc/configuration.md <doc/configuration.md>`_ — hosts, services,
  templates, and the container-specific networking gotchas
* `doc/livestatus-thruk.md <doc/livestatus-thruk.md>`_ — wiring up a real
  web UI (Thruk) via the Livestatus module
* `doc/exploitation.md <doc/exploitation.md>`_ — day-to-day operations
  (reload, force check, acknowledge, downtime)
* `doc/depannage.md <doc/depannage.md>`_ — real bugs already found and
  fixed in this fork

``DEPLOYMENT.md`` at the repo root is a chronological deployment journal
for one specific server, kept for its detailed troubleshooting history —
``doc/`` is the up-to-date reference.

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
