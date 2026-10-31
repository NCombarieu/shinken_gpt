#!/usr/bin/env python3

from __future__ import absolute_import, print_function

import copy
import datetime  # not used but "sub-"imported by livestatus test.. (to be corrected..)
import os
import re
import shutil
import subprocess
import sys  # not here used but "sub-"imported by livestatus test.. (to be corrected..)
import time

from shinken.modulesctx import modulesctx
from shinken.objects.module import Module
from shinken.modulesmanager import ModulesManager
from shinken.misc.datamanager import datamgr
from shinken.log import logger

from shinken_test import (
    modules_dir,
    ShinkenTest,
    time_hacker,  # not used here but "sub"-imported by lvestatus test (to be corrected)
)

modulesctx.set_modulesdir(modules_dir)


# Special Livestatus module opening since the module rename
livestatus_broker = modulesctx.get_module('livestatus')
LiveStatus_broker = livestatus_broker.LiveStatus_broker
LiveStatus = livestatus_broker.LiveStatus
LiveStatusRegenerator = livestatus_broker.LiveStatusRegenerator
LiveStatusQueryCache = livestatus_broker.LiveStatusQueryCache
LiveStatusClientThread = livestatus_broker.LiveStatusClientThread

Logline = livestatus_broker.Logline
LiveStatusLogStoreMongoDB = modulesctx.get_module('logstore-mongodb').LiveStatusLogStoreMongoDB
LiveStatusLogStoreSqlite = modulesctx.get_module('logstore-sqlite').LiveStatusLogStoreSqlite

livestatus_modconf = Module()
livestatus_modconf.module_name = "livestatus"
livestatus_modconf.module_type = livestatus_broker.properties['type']
livestatus_modconf.properties = livestatus_broker.properties.copy()


class ShinkenModulesTest(ShinkenTest):

    def do_load_modules(self):
        self.modules_manager.load_and_init()
        self.log.log("I correctly loaded the modules: [%s]" % (','.join([inst.get_name() for inst in self.modules_manager.instances])))

    def update_broker(self, dodeepcopy=False):
        # The brok should be manage in the good order
        ids = list(self.sched.brokers['Default-Broker']['broks'].keys())
        ids.sort()
        for brok_id in ids:
            brok = self.sched.brokers['Default-Broker']['broks'][brok_id]
            if dodeepcopy:
                brok = copy.deepcopy(brok)
            brok.prepare()
            self.livestatus_broker.manage_brok(brok)
        self.sched.brokers['Default-Broker']['broks'] = {}

    def init_livestatus(self, modconf=None, dbmodconf=None, needcache=False):
        self.livelogs = 'tmp/livelogs.db' + self.testid

        if modconf is None:
            modconf = Module({'module_name': 'LiveStatus',
                'module_type': 'livestatus',
                'port': str(50000 + os.getpid()),
                'pnp_path': 'tmp/pnp4nagios_test' + self.testid,
                'host': '127.0.0.1',
                'socket': 'live',
                'name': 'test',
            })

        if dbmodconf is None:
            dbmodconf = Module({'module_name': 'LogStore',
                'module_type': 'logstore_sqlite',
                'use_aggressive_sql': "0",
                'database_file': self.livelogs,
                'archive_path': os.path.join(os.path.dirname(self.livelogs), 'archives'),
            })

        modconf.modules = [dbmodconf]
        self.livestatus_broker = LiveStatus_broker(modconf)
        self.livestatus_broker.create_queues()

        self.livestatus_broker.log = logger
        self.livestatus_broker.debug_output = []
        self.livestatus_broker.modules_manager = ModulesManager('livestatus', modules_dir, [])
        self.livestatus_broker.modules_manager.set_modules(self.livestatus_broker.modules)
        self.livestatus_broker.do_load_modules()
        for inst in self.livestatus_broker.modules_manager.instances:
            if inst.properties["type"].startswith('logstore'):
                f = getattr(inst, 'load', None)
                if f and callable(f):
                    f(self.livestatus_broker)
                break
        for s in self.livestatus_broker.debug_output:
            print("errors during load", s)
        del self.livestatus_broker.debug_output
        self.livestatus_broker.rg = LiveStatusRegenerator()
        self.livestatus_broker.datamgr = datamgr
        datamgr.load(self.livestatus_broker.rg)
        self.livestatus_broker.query_cache = LiveStatusQueryCache()
        if not needcache:
            self.livestatus_broker.query_cache.disable()
        self.livestatus_broker.rg.register_cache(self.livestatus_broker.query_cache)

        self.livestatus_broker.init()
        self.livestatus_broker.db = self.livestatus_broker.modules_manager.instances[0]
        self.livestatus_broker.livestatus = LiveStatus(
            self.livestatus_broker.datamgr,
            self.livestatus_broker.query_cache,
            self.livestatus_broker.db,
            self.livestatus_broker.pnp_path,
            self.livestatus_broker.from_q,
        )

        self.livestatus_broker.db.open()
        if hasattr(self.livestatus_broker.db, 'prepare_log_db_table'):
            self.livestatus_broker.db.prepare_log_db_table()


class TestConfig(ShinkenModulesTest):

    def tearDown(self):
        self.livestatus_broker.db.close()
        if os.path.exists(self.livelogs):
            os.remove(self.livelogs)
        if os.path.exists(self.livelogs + "-journal"):
            os.remove(self.livelogs + "-journal")
        if os.path.exists(self.livestatus_broker.pnp_path):
            shutil.rmtree(self.livestatus_broker.pnp_path)
        if os.path.exists('var/shinken.log'):
            os.remove('var/shinken.log')
        if os.path.exists('var/retention.dat'):
            os.remove('var/retention.dat')
        if os.path.exists('var/status.dat'):
            os.remove('var/status.dat')
        self.livestatus_broker = None

    def contains_line(self, text, pattern):
        regex = re.compile(pattern)
        for line in text.splitlines():
            if re.search(regex, line):
                return True
        return False

    def update_broker(self, dodeepcopy=False):
        # The brok should be manage in the good order
        ids = list(self.sched.brokers['Default-Broker']['broks'].keys())
        ids.sort()
        for brok_id in ids:
            brok = self.sched.brokers['Default-Broker']['broks'][brok_id]
            if dodeepcopy:
                brok = copy.deepcopy(brok)
            brok.prepare()
            self.livestatus_broker.manage_brok(brok)
        self.sched.brokers['Default-Broker']['broks'] = {}

    def lines_equal(self, text1, text2):
        # gets two multiline strings and compares the contents
        # lifestatus output may not be in alphabetical order, so this
        # function is used to compare unordered output with unordered
        # expected output
        text1 = text1.replace("200           1", "200           0")
        text2 = text2.replace("200           1", "200           0")
        text1 = text1.rstrip()
        text2 = text2.rstrip()
        sorted1 = "\n".join(sorted(text1.split("\n")))
        sorted2 = "\n".join(sorted(text2.split("\n")))
        len1 = len(text1.split("\n"))
        len2 = len(text2.split("\n"))
        if sorted1 == sorted2 and len1 == len2:
            return True

        # Maybe list members are different. Normalize each comma-separated
        # cell so equivalent nested lists compare directly on Python 3.
        data1 = [
            [sorted(cell.split(',')) for cell in line.split(';')]
            for line in sorted(text1.split("\n"))
            if line
        ]
        data2 = [
            [sorted(cell.split(',')) for cell in line.split(';')]
            for line in sorted(text2.split("\n"))
            if line
        ]
        return data1 == data2

    def show_broks(self, title):
        print()
        print("--- ", title)
        for brok in sorted(self.sched.broks, key=lambda item: item.id):
            if re.compile('^service_').match(brok.type):
                pass
        self.update_broker()
        request = 'GET services\nColumns: service_description is_executing\n'
        response, keepalive = self.livestatus_broker.livestatus.handle_request(request)
        print(response)
