#!/usr/bin/env python3
"""Structured logging configuration for Shinken daemons.

Provides JSON-formatted logging for better parsing, aggregation, and debugging.
Falls back to human-readable format for interactive use.

Usage:
    from shinken.structured_logging import setup_logging
    setup_logging('shinken-arbiter', level='INFO', json_format=True)
"""

import json
import logging
import sys
from logging import Formatter, StreamHandler, FileHandler
from pathlib import Path
from typing import Optional


class StructuredFormatter(Formatter):
    """Format log records as JSON for structured logging."""

    def __init__(self, daemon_name: str) -> None:
        self.daemon_name = daemon_name
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Convert a log record to JSON."""
        log_entry = {
            'timestamp': self.formatTime(record),
            'daemon': self.daemon_name,
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry, default=str)


class HumanFormatter(Formatter):
    """Format log records for human-readable output."""

    def __init__(self, daemon_name: str) -> None:
        self.daemon_name = daemon_name
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as readable text."""
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
        else:
            exc_text = ''

        msg = (
            f"[{record.levelname:8}] {record.name:20} "
            f"({record.module}:{record.funcName}:{record.lineno}) "
            f"{record.getMessage()}"
        )

        if exc_text:
            msg += f"\n{exc_text}"

        return msg


def setup_logging(
    daemon_name: str,
    level: str = 'INFO',
    json_format: bool = False,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Configure logging for a Shinken daemon.

    Args:
        daemon_name: Name of the daemon (e.g., 'shinken-arbiter')
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        json_format: If True, output JSON-formatted logs; otherwise human-readable
        log_file: Optional file path for file-based logging

    Returns:
        Configured root logger
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    formatter_class = StructuredFormatter if json_format else HumanFormatter
    formatter = formatter_class(daemon_name)

    # Console (stderr) handler — always enabled
    console_handler = StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler — if log file specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce verbosity of chatty libraries
    logging.getLogger('Pyro5').setLevel(logging.WARNING)
    logging.getLogger('bottle').setLevel(logging.WARNING)

    return root_logger


class LogContext:
    """Context manager for adding extra fields to log records.

    Usage:
        with LogContext(host_id='web-01', service_id='HTTP'):
            logger.info("Check executed")  # Will include host_id and service_id
    """

    def __init__(self, **fields) -> None:
        self.fields = fields
        self._token = None

    def __enter__(self):
        # Add fields to the logging context (thread-local)
        adapter = logging.LoggerAdapter(
            logging.getLogger(),
            extra=self.fields,
        )
        return adapter

    def __exit__(self, *args):
        pass


def create_daemon_logger(
    daemon_name: str,
    level: str = 'INFO',
) -> logging.Logger:
    """Create a logger for a specific daemon module.

    Args:
        daemon_name: Logger name (e.g., 'shinken.daemons.arbiterdaemon')
        level: Logging level

    Returns:
        Configured logger
    """
    logger = logging.getLogger(daemon_name)
    logger.setLevel(getattr(logging, level.upper()))
    return logger
