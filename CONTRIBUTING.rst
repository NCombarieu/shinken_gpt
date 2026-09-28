Contributing
============

This fork's own documentation lives in `doc/ <doc/README.md>`_ — read
`doc/presentation.md <doc/presentation.md>`_ and
`doc/depannage.md <doc/depannage.md>`_ before touching the daemon core or
the Livestatus module: several non-obvious Python 2 → 3 porting traps
(pickle security, module aliasing, module-forking deadlocks) are documented
there with the exact fix already applied.

For the general shape of a Shinken contribution (config object model,
daemon responsibilities), the upstream project's conventions still mostly
apply: https://github.com/naparuba/shinken
