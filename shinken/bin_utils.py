#!/usr/bin/env python3
"""Common utilities for Shinken daemon entry points.

Provides:
- Command-line option parsing shared across all daemons
- Structured logging setup
- Version and help text
"""

import optparse
import logging
from pathlib import Path
from typing import Optional, Tuple

from shinken.bin import VERSION
from shinken.structured_logging import setup_logging


def add_common_options(parser: optparse.OptionParser) -> None:
    """Add common options to a daemon's option parser.

    Args:
        parser: optparse.OptionParser instance to add options to
    """
    parser.add_option(
        '-d', '--daemon',
        action='store_true',
        dest='is_daemon',
        help='Run in daemon mode (fork to background)'
    )
    parser.add_option(
        '--verbose',
        action='store_true',
        dest='verbose',
        help='Enable verbose output (DEBUG level)'
    )
    parser.add_option(
        '--debug',
        action='store_true',
        dest='debug',
        help='Enable debug output (very verbose)'
    )
    parser.add_option(
        '--json-logs',
        action='store_true',
        dest='json_logs',
        help='Output structured JSON logs (for log aggregation)'
    )
    parser.add_option(
        '--logfile',
        dest='log_file',
        metavar='FILE',
        help='Log file path (default: log to stderr only)'
    )


def setup_logging_from_options(
    daemon_name: str,
    options: optparse.Values,
) -> logging.Logger:
    """Configure logging based on command-line options.

    Args:
        daemon_name: Name of the daemon (e.g., 'shinken-arbiter')
        options: Parsed command-line options

    Returns:
        Configured logger
    """
    # Determine log level from verbosity
    if options.debug:
        level = 'DEBUG'
    elif options.verbose:
        level = 'INFO'
    else:
        level = 'WARNING'

    # Convert log_file to Path if provided
    log_file = None
    if hasattr(options, 'log_file') and options.log_file:
        log_file = Path(options.log_file)

    return setup_logging(
        daemon_name,
        level=level,
        json_format=getattr(options, 'json_logs', False),
        log_file=log_file,
    )
