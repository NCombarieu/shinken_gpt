#!/usr/bin/env python

# -*- coding: utf-8 -*-

# Copyright (C) 2009-2014:
#     Gabes Jean, naparuba@gmail.com
#     Gerhard Lausser, Gerhard.Lausser@consol.de
#     Gregory Starck, g.starck@gmail.com
#     Hartmut Goebel, h.goebel@goebel-consult.de
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

from shinken.log import logger
from shinken.util import strip_and_uniq


"""
Here is a node class for complex_expression(s) and a factory to create them
"""

class ComplexExpressionNode(object):
    def __init__(self):
        self.operand = None
        self.sons = []
        self.configuration_errors = []
        self.not_value = False
        self.leaf = False
        self.content = None

    def __str__(self):
        if not self.leaf:
            return "Op:'%s' Leaf:%s Sons:'[%s] IsNot:%s'" % \
                   (self.operand, self.leaf, ','.join([str(s) for s in self.sons]), self.not_value)
        return 'IS LEAF %s' % self.content

    def resolve_elements(self):
        if self.leaf:
            if not self.content:
                return set()
            return set(self.content)

        not_nodes = [s for s in self.sons if s.not_value]
        positiv_nodes = [s for s in self.sons if not s.not_value]
        if not self.operand:
            self.operand = '|'

        res = set()
        i = 0
        for n in positiv_nodes:
            node_members = n.resolve_elements()
            if self.operand == '|':
                res = res.union(node_members)
            elif self.operand == '&':
                if i == 0:
                    res = node_members
                else:
                    res = res.intersection(node_members)
            i += 1

        for n in not_nodes:
            res = res.difference(n.resolve_elements())
        return res

    def is_valid(self):
        if self.leaf:
            return not self.configuration_errors
        if not self.sons:
            return False
        valid = True
        for son in self.sons:
            if not son.is_valid():
                self.configuration_errors.extend(son.configuration_errors)
                valid = False
        return valid


class ComplexExpressionFactory(object):
    def __init__(self, ctx='hostgroups', grps=None, all_elements=None):
        self.ctx = ctx
        self.grps = grps
        self.all_elements = all_elements

    def eval_cor_pattern(self, pattern):
        pattern = pattern.strip()
        complex_node = any(m in pattern for m in '()+&|,')
        node = ComplexExpressionNode()

        if not complex_node:
            if pattern.startswith('!'):
                node.not_value = True
                pattern = pattern[1:]
            node.operand = self.ctx
            node.leaf = True
            obj, error = self.find_object(pattern)
            if obj is not None:
                node.content = obj
            else:
                node.configuration_errors.append(error)
            return node

        in_par = False
        tmp = ''
        stacked_par = 0
        for c in pattern:
            if c == ',' or c == '|':
                if in_par:
                    tmp += c
                else:
                    tmp = tmp.strip()
                    node.operand = '|'
                    if tmp != '':
                        node.sons.append(self.eval_cor_pattern(tmp))
                    tmp = ''
            elif c == '&' or c == '+':
                if in_par:
                    tmp += c
                else:
                    tmp = tmp.strip()
                    node.operand = '&'
                    if tmp != '':
                        node.sons.append(self.eval_cor_pattern(tmp))
                    tmp = ''
            elif c == '(':
                stacked_par += 1
                in_par = True
                tmp = tmp.strip()
                if stacked_par == 1 and tmp != '':
                    logger.error("ERROR : bad expression near: %s" % tmp)
                    continue
                if stacked_par > 1:
                    tmp += c
            elif c == ')':
                stacked_par -= 1
                if stacked_par < 0:
                    logger.error("Error : bad expression near %s: too much ')' " % tmp)
                    continue
                if stacked_par == 0:
                    tmp = tmp.strip()
                    node.sons.append(self.eval_cor_pattern(tmp))
                    in_par = False
                    tmp = ''
                    continue
                tmp += c
            else:
                tmp += c

        tmp = tmp.strip()
        if tmp != '':
            node.sons.append(self.eval_cor_pattern(tmp))
        return node

    def find_object(self, pattern):
        obj = None
        error = None
        pattern = pattern.strip()
        if pattern == '*':
            obj = [h.host_name for h in self.all_elements.items.values()
                   if getattr(h, 'host_name', '') != '' and not h.is_tpl()]
            return obj, error

        if self.ctx == 'hostgroups':
            hg = self.grps.find_by_name(pattern)
            if not hg:
                error = "Error : cannot find the %s of the expression '%s'" % (self.ctx, pattern)
                return hg, error
            elts = strip_and_uniq(hg.get_hosts())
            if '*' in elts:
                elts.extend([h.host_name for h in self.all_elements.items.values()
                             if getattr(h, 'host_name', '') != '' and not h.is_tpl()])
                elts.remove('*')
            return elts, error

        obj = self.grps.find_hosts_that_use_template(pattern)
        return obj, error
