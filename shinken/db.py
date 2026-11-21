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


class DB(object):
    """DB is a generic class for SQL Database"""

    def __init__(self, table_prefix=''):
        self.table_prefix = table_prefix

    def stringify(self, val):
        """Return a SQL-escaped text representation of a value."""
        if isinstance(val, bytes):
            val = val.decode('utf8', 'ignore')
        elif not isinstance(val, str):
            val = str(val)
        return val.replace("'", "''")

    def create_insert_query(self, table, data):
        """Create a INSERT query in table with all data of data (a dict)"""
        query = "INSERT INTO %s " % (self.table_prefix + table)
        props_str = ' ('
        values_str = ' ('
        i = 0
        for prop in data:
            i += 1
            val = data[prop]
            if isinstance(val, bool):
                val = 1 if val else 0
            val = self.stringify(val)
            if i == 1:
                props_str += "%s " % prop
                values_str += "'%s' " % val
            else:
                props_str += ", %s " % prop
                values_str += ", '%s' " % val
        props_str += ' )'
        values_str += ' )'
        return query + props_str + ' VALUES' + values_str

    def create_update_query(self, table, data, where_data):
        """Create an update query and use where_data for the WHERE clause."""
        query = "UPDATE %s set " % (self.table_prefix + table)
        query_follow = ''
        i = 0
        for prop in data:
            if prop not in where_data:
                i += 1
                val = data[prop]
                if isinstance(val, bool):
                    val = 1 if val else 0
                val = self.stringify(val)
                if i == 1:
                    query_follow += "%s='%s' " % (prop, val)
                else:
                    query_follow += ", %s='%s' " % (prop, val)

        where_clause = " WHERE "
        i = 0
        for prop in where_data:
            i += 1
            val = where_data[prop]
            if isinstance(val, bool):
                val = 1 if val else 0
            val = self.stringify(val)
            if i == 1:
                where_clause += "%s='%s' " % (prop, val)
            else:
                where_clause += "and %s='%s' " % (prop, val)
        return query + query_follow + where_clause

    def fetchone(self):
        """Just get an entry"""
        return self.db_cursor.fetchone()

    def fetchall(self):
        """Get all entry"""
        return self.db_cursor.fetchall()
