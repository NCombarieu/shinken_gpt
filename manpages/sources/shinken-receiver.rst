================
shinken-receiver
================

-----------------------
Shinken receiver daemon
-----------------------

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

  **shinken-receiver** [-dr] [-c *CONFIGFILE*] [--debugfile *DEBUGFILE*]

DESCRIPTION
===========

Shinken receiver daemon.

The **shinken-receiver** daemon manages passive information and serves as a buffer that will be read from by the shinken-arbiter to dispatch data.

OPTIONS
=======

  -c INI-CONFIG-FILE, --config=INI-CONFIG-FILE  Config file
  -d, --daemon                                  Run in daemon mode
  -r, --replace                                 Replace previous running receiver
  -h, --help                                    Show this help message
  --version                                     Show program's version number 
  --debugfile=DEBUGFILE                         Enable debug logging to *DEBUGFILE*
  -p PROFILE, --profile=PROFILE                 Dump a profile file. Need the python cProfile librairy
  --verbose                                 Log at INFO level on the console
  --debug                                   Log at DEBUG level on the console
  --json-logs                               Emit one JSON object per log line (for log aggregation)
  --logfile=FILE                            Also write the logs to *FILE*
