#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2014:
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

from six import add_metaclass

from .autoslots import AutoSlots
from .property import StringProp, BoolProp, IntegerProp
from .util import basestring

class DummyCommandCall(object):
    """Ok, slots are fun: you cannot set the __autoslots__
     on the same class you use, fun isn't it? So we define*
     a dummy useless class to get such :)
    """
    pass


# AutoSlots create the __slots__ with properties and
# running_properties names
@add_metaclass(AutoSlots)
class CommandCall(DummyCommandCall):
    """This class is use when a service, contact or host define
    a command with args.
    """

    # __slots__ = ('id', 'call', 'command', 'valid', 'args', 'poller_tag',
    #              'reactionner_tag', 'module_type', '__dict__')
    id = 0
    my_type = 'CommandCall'

    properties = {
        'call':            StringProp(),
        'command':         StringProp(),
        'poller_tag':      StringProp(default='None'),
        'reactionner_tag': StringProp(default='None'),
        'module_type':     StringProp(default='fork'),
        'valid':           BoolProp(default=False),
        'args':            StringProp(default=[]),
        'timeout':         IntegerProp(default=-1),
        'late_relink_done': BoolProp(default=False),
        'enable_environment_macros': BoolProp(default=False),
        'priority':        IntegerProp(default=100),
    }

    def __init__(self, commands, call, poller_tag='None',
                 reactionner_tag='None', enable_environment_macros=0,
                 priority=100):
        self.id = self.__class__.id
        self.__class__.id += 1
        self.call = call
        self.timeout = -1
        self.get_command_and_args()
        self.command = commands.find_by_name(self.command.strip())
        self.late_relink_done = False
        self.valid = self.command is not None
        if self.valid:
            self.poller_tag = poller_tag
            self.reactionner_tag = reactionner_tag
            self.module_type = self.command.module_type
            self.enable_environment_macros = self.command.enable_environment_macros
            self.timeout = int(self.command.timeout)
            if poller_tag == 'None':
                self.poller_tag = self.command.poller_tag
            if reactionner_tag == 'None':
                self.reactionner_tag = self.command.reactionner_tag
            if int(priority) != self.properties["priority"].default:
                self.priority = int(priority)
            else:
                self.priority = int(self.command.priority)

    def get_command_and_args(self):
        """We want to get the command and the args with ! splitting.
        but don't forget to protect against the \! to do not split them
        """
        p_call = self.call.replace('\!', '___PROTECT_EXCLAMATION___')
        tab = p_call.split('!')
        self.command = tab[0]
        self.args = [s.replace('___PROTECT_EXCLAMATION___', '!') for s in tab[1:]]

    def late_linkify_with_command(self, commands):
        if self.late_relink_done:
            return
        self.late_relink_done = True
        self.command = commands.find_by_name(self.command)

    def is_valid(self):
        return self.valid

    def __str__(self):
        return str(self.__dict__)

    def get_name(self):
        return self.call

    def __getstate__(self):
        """Call by pickle to dataify the comment without object references."""
        cls = self.__class__
        res = {'id': self.id}
        for prop in cls.properties:
            if hasattr(self, prop):
                res[prop] = getattr(self, prop)
        if self.command and not isinstance(self.command, basestring):
            res['command'] = self.command.get_name()
        elif self.command and isinstance(self.command, basestring):
            res['command'] = self.command
        else:
            res['command'] = ''
        return res

    def __setstate__(self, state):
        """Inverted function of getstate."""
        cls = self.__class__
        if isinstance(state, tuple):
            self.__setstate_pre_1_0__(state)
            return
        self.id = state['id']
        for prop in cls.properties:
            if prop in state:
                setattr(self, prop, state[prop])

    def __setstate_pre_1_0__(self, state):
        for d in state:
            for k, v in d.items():
                setattr(self, k, v)
