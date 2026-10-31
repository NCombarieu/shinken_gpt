==============
shinken-poller
==============

---------------------
Shinken poller daemon
---------------------

:Author:            Michael Leinartas,
                    Arthur Gautier,
                    David Hannequin,
                    Thibault Cohen
:Date:              2026-10-31
:Version:           2.4.3
:Manual section:    8
:Manual group:      Shinken commands


SYNOPSIS
========

  **shinken-poller** [-dr] [-c *CONFIGFILE*] [--debugfile *DEBUGFILE*]

DESCRIPTION
===========

Shinken poller daemon.

The **shinken-poller** daemon is in charge of launching plugins as requested by schedulers. When the check is finished it returns the result to the schedulers.

OPTIONS
=======

  -c INI-CONFIG-FILE, --config=INI-CONFIG-FILE  Config file
  -d, --daemon                                  Run in daemon mode
  -r, --replace                                 Replace previous running poller
  -h, --help                                    Show this help message
  --version                                     Show program's version number 
  --debugfile=DEBUGFILE                         Enable debug logging to *DEBUGFILE*
  -p PROFILE, --profile=PROFILE                 Dump a profile file. Need the python cProfile librairy
  --verbose                                 Log at INFO level on the console
  --debug                                   Log at DEBUG level on the console
  --json-logs                               Emit one JSON object per log line (for log aggregation)
  --logfile=FILE                            Also write the logs to *FILE*
