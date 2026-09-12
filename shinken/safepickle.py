# -*- coding: utf-8 -*-

# Copyright (C) 2009-2014:
#     Gabes Jean, naparuba@gmail.com
#     Gerhard Lausser, Gerhard.Lausser@consol.de
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

import io
import sys

try:
    import cPickle as cpickle
except ImportError:
    import pickle as cpickle


# Unpickle while rejecting arbitrary globals so crafted payloads cannot execute
# external code. Based on the historical Graphite/carbon implementation.
class _RestrictedUnpickler(cpickle.Unpickler):
    PICKLE_SAFE = {
        'copy_reg': {'_reconstructor'},
        'copyreg': {'_reconstructor'},
        '__builtin__': {'object', 'set'},
        'builtins': {'object', 'set'},
    }

    def find_class(self, module, name):
        if module.startswith('shinken.'):
            __import__(module)
            return getattr(sys.modules[module], name)

        allowed_names = self.PICKLE_SAFE.get(module)
        if allowed_names is None:
            raise ValueError('Attempting to unpickle unsafe module %s' % module)
        if name not in allowed_names:
            raise ValueError('Attempting to unpickle unsafe class %s/%s' %
                             (module, name))

        __import__(module)
        return getattr(sys.modules[module], name)


class SafeUnpickler(object):
    PICKLE_SAFE = _RestrictedUnpickler.PICKLE_SAFE

    @classmethod
    def find_class(cls, module, name):
        """Compatibility helper for callers using the historical API."""
        if module.startswith('shinken.'):
            __import__(module)
            return getattr(sys.modules[module], name)

        allowed_names = cls.PICKLE_SAFE.get(module)
        if allowed_names is None:
            raise ValueError('Attempting to unpickle unsafe module %s' % module)
        if name not in allowed_names:
            raise ValueError('Attempting to unpickle unsafe class %s/%s' %
                             (module, name))

        __import__(module)
        return getattr(sys.modules[module], name)

    @classmethod
    def loads(cls, pickle_string):
        if isinstance(pickle_string, str):
            # Protocol 0 payloads historically travelled through text streams.
            # latin-1 is a one-to-one mapping for byte values and therefore does
            # not alter the serialized payload.
            pickle_string = pickle_string.encode('latin-1')
        return _RestrictedUnpickler(io.BytesIO(pickle_string)).load()
