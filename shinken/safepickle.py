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

"""Restricted unpickling of the data exchanged between Shinken daemons.

Daemons exchange pickled objects over HTTP (configuration, checks,
notifications, broks, external commands...). Unpickling untrusted data can
run arbitrary code, so every pickle received from the network must be
loaded with :class:`SafeUnpickler`, which only resolves the globals listed
in :data:`PICKLE_SAFE`: the Shinken classes that are really exchanged and a
couple of harmless builtins. Any other global (``os.system``,
``subprocess.Popen``, ``builtins.eval``, ``importlib.import_module``, a
function of a Shinken module...) is refused with ``ValueError``.

This is the strict, class by class whitelist of Shinken 2.4.4 (fix of the
remote code execution through pickle), adapted to Python 3.
"""

import io
import pickle
import sys

# Python 2 module names that can still show up inside a pickle stream
# (payload produced by Python 2, or protocol 0/1 streams) but no longer
# exist under that name.
_PY2_MODULE_ALIASES = {
    'copy_reg': 'copyreg',
    '__builtin__': 'builtins',
}

# module -> names that may be resolved while unpickling.
# Be sure to whitelist ONLY what really needs to be unpickled, so that a
# crafted payload cannot reach other callables (bottle, os, importlib...).
PICKLE_SAFE = {
    'copy_reg': frozenset(['_reconstructor']),
    'copyreg': frozenset(['_reconstructor']),
    '__builtin__': frozenset(['object', 'set', 'frozenset']),
    'builtins': frozenset(['object', 'set', 'frozenset']),
    # Python 3 pickles bytes as _codecs.encode(str, 'latin1') with the
    # protocols 0 to 2 (used for the realm configurations). Encoding a
    # string with a registered codec cannot run arbitrary code.
    '_codecs': frozenset(['encode']),

    'shinken.acknowledge': frozenset(['Acknowledge']),
    'shinken.basemodule': frozenset(['BaseModule']),
    'shinken.borg': frozenset(['Borg']),
    'shinken.brok': frozenset(['Brok']),
    'shinken.check': frozenset(['Check']),
    'shinken.commandcall': frozenset(['CommandCall', 'DummyCommandCall']),
    'shinken.comment': frozenset(['Comment']),
    'shinken.complexexpression': frozenset(['ComplexExpressionNode']),
    'shinken.contactdowntime': frozenset(['ContactDowntime']),
    'shinken.daterange': frozenset(['Timerange',
                                    'Daterange',
                                    'CalendarDaterange',
                                    'StandardDaterange',
                                    'MonthWeekDayDaterange',
                                    'MonthDateDaterange',
                                    'WeekDayDaterange',
                                    'MonthDayDaterange']),
    'shinken.dependencynode': frozenset(['DependencyNode']),
    'shinken.discovery.discoverymanager': frozenset(['DiscoveredHost']),
    'shinken.downtime': frozenset(['Downtime']),
    'shinken.eventhandler': frozenset(['EventHandler']),
    'shinken.external_command': frozenset(['ExternalCommand']),
    'shinken.graph': frozenset(['Graph']),
    'shinken.message': frozenset(['Message']),
    'shinken.modulesctx': frozenset(['ModulesContext']),
    'shinken.modulesmanager': frozenset(['ModulesManager']),
    'shinken.notification': frozenset(['Notification']),
    'shinken.objects.arbiterlink': frozenset(['ArbiterLink', 'ArbiterLinks']),
    'shinken.objects.brokerlink': frozenset(['BrokerLink', 'BrokerLinks']),
    'shinken.objects.businessimpactmodulation': frozenset(['Businessimpactmodulation',
                                                           'Businessimpactmodulations']),
    'shinken.objects.checkmodulation': frozenset(['CheckModulation', 'CheckModulations']),
    'shinken.objects.command': frozenset(['DummyCommand', 'Command', 'Commands']),
    'shinken.objects.config': frozenset(['Config']),
    'shinken.objects.contact': frozenset(['Contact', 'Contacts']),
    'shinken.objects.contactgroup': frozenset(['Contactgroup', 'Contactgroups']),
    'shinken.objects.discoveryrule': frozenset(['Discoveryrule', 'Discoveryrules']),
    'shinken.objects.discoveryrun': frozenset(['Discoveryrun', 'Discoveryruns']),
    'shinken.objects.escalation': frozenset(['Escalation', 'Escalations']),
    'shinken.objects.host': frozenset(['Host', 'Hosts']),
    'shinken.objects.hostdependency': frozenset(['Hostdependency', 'Hostdependencies']),
    'shinken.objects.hostescalation': frozenset(['Hostescalation', 'Hostescalations']),
    'shinken.objects.hostextinfo': frozenset(['HostExtInfo', 'HostsExtInfo']),
    'shinken.objects.hostgroup': frozenset(['Hostgroup', 'Hostgroups']),
    'shinken.objects.item': frozenset(['Item', 'Items']),
    'shinken.objects.itemgroup': frozenset(['Itemgroup', 'Itemgroups']),
    'shinken.objects.macromodulation': frozenset(['MacroModulation', 'MacroModulations']),
    'shinken.objects.matchingitem': frozenset(['MatchingItem']),
    'shinken.objects.module': frozenset(['Module', 'Modules']),
    'shinken.objects.notificationway': frozenset(['NotificationWay', 'NotificationWays']),
    'shinken.objects.pack': frozenset(['Pack', 'Packs']),
    'shinken.objects.pollerlink': frozenset(['PollerLink', 'PollerLinks']),
    'shinken.objects.reactionnerlink': frozenset(['ReactionnerLink', 'ReactionnerLinks']),
    'shinken.objects.realm': frozenset(['Realm', 'Realms']),
    'shinken.objects.receiverlink': frozenset(['ReceiverLink', 'ReceiverLinks']),
    'shinken.objects.resultmodulation': frozenset(['Resultmodulation', 'Resultmodulations']),
    'shinken.objects.satellitelink': frozenset(['SatelliteLink', 'SatelliteLinks']),
    'shinken.objects.schedulerlink': frozenset(['SchedulerLink', 'SchedulerLinks']),
    'shinken.objects.schedulingitem': frozenset(['SchedulingItem']),
    'shinken.objects.service': frozenset(['Service', 'Services']),
    'shinken.objects.servicedependency': frozenset(['Servicedependency',
                                                    'Servicedependencies']),
    'shinken.objects.serviceescalation': frozenset(['Serviceescalation',
                                                    'Serviceescalations']),
    'shinken.objects.serviceextinfo': frozenset(['ServiceExtInfo', 'ServicesExtInfo']),
    'shinken.objects.servicegroup': frozenset(['Servicegroup', 'Servicegroups']),
    'shinken.objects.timeperiod': frozenset(['Timeperiod', 'Timeperiods']),
    'shinken.objects.trigger': frozenset(['Trigger', 'Triggers']),
}


def find_class(module, name):
    """Resolve a global of a pickle stream if, and only if, it is whitelisted.

    :param str module: module name found in the pickle stream
    :param str name: global name found in the pickle stream
    :raise ValueError: if the module or the name is not in :data:`PICKLE_SAFE`
    :return: the class (or harmless builtin) to use
    """
    allowed_names = PICKLE_SAFE.get(module)
    if allowed_names is None:
        raise ValueError('Attempting to unpickle unsafe module %s' % module)
    if name not in allowed_names:
        raise ValueError('Attempting to unpickle unsafe class %s/%s' % (module, name))
    real_module = _PY2_MODULE_ALIASES.get(module, module)
    __import__(real_module)
    return getattr(sys.modules[real_module], name)


class _RestrictedUnpickler(pickle.Unpickler):
    """``pickle.Unpickler`` that resolves globals with :func:`find_class`."""

    def find_class(self, module, name):
        return find_class(module, name)


class SafeUnpickler(object):
    """Entry point to unpickle data received from another daemon."""

    PICKLE_SAFE = PICKLE_SAFE

    @classmethod
    def find_class(cls, module, name):
        """Compatibility helper for callers using the historical API."""
        return find_class(module, name)

    @classmethod
    def loads(cls, pickle_string):
        """Unpickle ``pickle_string`` with the restricted whitelist.

        :param pickle_string: the pickle, as ``bytes``. A ``str`` is accepted
            for protocol 0 payloads that travelled through text streams; it
            is encoded back with latin-1 (one to one byte mapping).
        :raise ValueError: if the payload references a forbidden global
        :raise pickle.UnpicklingError: if the payload is not a valid pickle
        """
        if isinstance(pickle_string, str):
            pickle_string = pickle_string.encode('latin-1')
        return _RestrictedUnpickler(io.BytesIO(pickle_string)).load()
