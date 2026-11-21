#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2012:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

"""Scheduler retention module storing the state in a pickle file.

Python 3 port of the historical ``pickle-retention-file-scheduler`` module.
The scheduler calls:

* ``hook_save_retention`` every ``retention_update_interval`` minutes and
  when it stops: the data returned by ``Scheduler.get_retention_data()``
  (states, outputs, acknowledgements, downtimes, comments, notifications in
  progress...) is pickled to ``path``. The file is written atomically
  (temporary file in the same directory, fsync, then rename), so a crash
  never leaves a truncated retention file behind;
* ``hook_load_retention`` when it starts: the file is read back and handed
  to ``Scheduler.restore_retention_data()``.

Reading goes through the restricted unpickler of Shinken (only the classes
allowed by :mod:`shinken.safepickle` can be built). Files written by
Shinken 2.4 on Python 2 are supported: their byte strings are decoded as
UTF-8, falling back to latin-1 for each string that is not valid UTF-8, so
accented outputs and comments are preserved.
"""

import io
import os
import pickle
import tempfile

from shinken.basemodule import BaseModule
from shinken.log import logger
from shinken.safepickle import SafeUnpickler

properties = {
    'daemons': ['scheduler'],
    'type': 'pickle_retention_file',
    'external': False,
    'phases': ['retention'],
}

DEFAULT_PATH = '/var/lib/shinken/retention.dat'
# Protocol 2 is the highest one Python 2 can read: keep it by default so
# that a retention file can still be read after a rollback to Shinken 2.4.
DEFAULT_PROTOCOL = 2

# Python 2 module names that may appear in pickles written by Python 2.
_PY2_MODULE_ALIASES = {
    'copy_reg': 'copyreg',
    '__builtin__': 'builtins',
}


def get_instance(plugin):
    """Called by the modules manager to build the module instance."""
    logger.debug("[PickleRetention] Get a pickle retention module for plugin %s",
                 plugin.get_name())
    return PickleRetentionFile(plugin)


def _safe_find_class(module, name):
    """Resolve a pickled global through the Shinken whitelist."""
    return SafeUnpickler.find_class(_PY2_MODULE_ALIASES.get(module, module), name)


class _RestrictedUnpickler(pickle.Unpickler):
    """Fast (C) unpickler restricted to the Shinken whitelist."""

    def find_class(self, module, name):
        return _safe_find_class(module, name)


class _Py2RestrictedUnpickler(pickle._Unpickler):
    """Pure Python unpickler for Python 2 retention files.

    Python 2 ``str`` values are pickled as raw bytes (``STRING``,
    ``BINSTRING`` and ``SHORT_BINSTRING`` opcodes) without any encoding
    information. Each of them is decoded as UTF-8 when possible (Shinken
    configurations and plugin outputs are usually UTF-8), and as latin-1
    otherwise: the decision is made string by string, so one latin-1 output
    does not corrupt the accents of all the other strings of the file.
    """

    def __init__(self, file):
        super().__init__(file, encoding='utf-8')

    def _decode_string(self, value):
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            return value.decode('latin-1')

    def find_class(self, module, name):
        return _safe_find_class(module, name)


def load_retention_bytes(data):
    """Unpickle retention data written by Shinken (Python 3 or Python 2).

    The fast C unpickler is tried first; it handles every file written by
    Python 3 and the Python 2 files containing only UTF-8 text. Python 2
    files with other encodings are read again with the per-string decoder.
    """
    try:
        return _RestrictedUnpickler(io.BytesIO(data), encoding='utf-8').load()
    except UnicodeDecodeError:
        logger.info("[PickleRetention] Retention data has non UTF-8 strings (Python 2 file?), "
                    "decoding them as latin-1")
    if not hasattr(pickle._Unpickler, '_decode_string'):
        # Very old interpreter without the hook: whole-file latin-1 fallback.
        return _RestrictedUnpickler(io.BytesIO(data), encoding='latin-1').load()
    return _Py2RestrictedUnpickler(io.BytesIO(data)).load()


class PickleRetentionFile(BaseModule):
    """Scheduler module saving/loading the retention data in a pickle file.

    Parameters: ``path`` (default ``/var/lib/shinken/retention.dat``) and
    ``pickle_protocol`` (default 2, readable by Shinken 2.4 / Python 2).
    """

    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        self.path = getattr(modconf, 'path', DEFAULT_PATH) or DEFAULT_PATH
        try:
            self.protocol = int(getattr(modconf, 'pickle_protocol', DEFAULT_PROTOCOL))
        except (TypeError, ValueError):
            self.protocol = DEFAULT_PROTOCOL
        if not 2 <= self.protocol <= pickle.HIGHEST_PROTOCOL:
            logger.warning("[PickleRetention] Invalid pickle_protocol %s, using %d",
                           self.protocol, DEFAULT_PROTOCOL)
            self.protocol = DEFAULT_PROTOCOL

    def init(self):
        logger.info("[PickleRetention] Retention file: %s", self.path)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def hook_save_retention(self, daemon):
        """Called by the scheduler to save its retention data."""
        self.update_retention_objects(daemon)

    def write_retention_file(self, all_data):
        """Atomically replace ``self.path`` with the pickled ``all_data``."""
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix='.%s.' % os.path.basename(self.path),
                                        suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as tmp_file:
                pickle.dump(all_data, tmp_file, protocol=self.protocol)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, self.path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    def update_retention_objects(self, sched):
        """Save ``sched.get_retention_data()``; return True on success."""
        logger.debug("[PickleRetention] Updating the retention file")
        try:
            all_data = sched.get_retention_data()
            self.write_retention_file(all_data)
        except (OSError, pickle.PicklingError, TypeError, AttributeError) as exp:
            logger.error("[PickleRetention] Retention file %s creation failed: %s",
                         self.path, exp)
            return False
        logger.info("[PickleRetention] Retention file %s updated", self.path)
        return True

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def hook_load_retention(self, daemon):
        """Called by the scheduler at startup to restore its state."""
        return self.load_retention_objects(daemon)

    def read_retention_file(self):
        """Return the unpickled content of ``self.path`` (or None if absent)."""
        try:
            with open(self.path, 'rb') as retention_file:
                data = retention_file.read()
        except FileNotFoundError:
            return None
        return load_retention_bytes(data)

    def load_retention_objects(self, sched):
        """Load the retention file into ``sched``; return True on success."""
        logger.debug("[PickleRetention] Reading retention file %s", self.path)
        try:
            all_data = self.read_retention_file()
        except Exception as exp:
            logger.error("[PickleRetention] Cannot read retention file %s: %s (%s). "
                         "Starting without retention data.",
                         self.path, exp, type(exp).__name__)
            return False
        if all_data is None:
            logger.info("[PickleRetention] No retention file %s yet, nothing to load",
                        self.path)
            return False
        if not isinstance(all_data, dict) or 'hosts' not in all_data \
                or 'services' not in all_data:
            logger.error("[PickleRetention] Retention file %s has an unexpected format, "
                         "ignoring it", self.path)
            return False

        sched.restore_retention_data(all_data)
        logger.info("[PickleRetention] Retention data loaded from %s (%d hosts, %d services)",
                    self.path, len(all_data['hosts']), len(all_data['services']))
        return True
