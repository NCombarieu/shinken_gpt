#!/usr/bin/env python3
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

import errno
import inspect
import json
import select
import socket
import threading
import time
import traceback
import zlib

import bottle

try:
    import ssl
except ImportError:
    ssl = None

try:
    from cherrypy import wsgiserver as cheery_wsgiserver
except ImportError:
    cheery_wsgiserver = None
try:
    from OpenSSL import SSL
    from cherrypy.wsgiserver.ssl_pyopenssl import pyOpenSSLAdapter

    class pyOpenSSLAdapterSafe(pyOpenSSLAdapter):
        """CherryPy adapter that explicitly disables obsolete SSL versions."""

        def get_context(self):
            context = pyOpenSSLAdapter.get_context(self)
            context.set_options(SSL.OP_NO_SSLv2 | SSL.OP_NO_SSLv3)
            return context
except ImportError:
    SSL = None
    pyOpenSSLAdapterSafe = None

from .log import logger
from shinken.safepickle import SafeUnpickler
from shinken.stats import statsmgr

# Keep Bottle diagnostics routed through Shinken logging instead of enabling
# framework debug mode globally in production daemons.
bottle.debug(False)


class InvalidWorkDir(Exception):
    pass


class PortNotFree(Exception):
    pass


class CherryPyServer(bottle.ServerAdapter):
    """Bottle adapter backed by Shinken's CherryPy WSGI server."""

    def run(self, handler):  # pragma: no cover
        daemon_thread_pool_size = self.options["daemon_thread_pool_size"]
        server = cheery_wsgiserver.CherryPyWSGIServer(
            (self.host, self.port),
            handler,
            numthreads=daemon_thread_pool_size,
            shutdown_timeout=1,
        )
        logger.info(
            "Initializing a CherryPy backend with %d threads",
            daemon_thread_pool_size,
        )
        use_ssl = self.options["use_ssl"]
        ca_cert = self.options["ca_cert"]
        ssl_cert = self.options["ssl_cert"]
        ssl_key = self.options["ssl_key"]
        if SSL and pyOpenSSLAdapterSafe and use_ssl:
            server.ssl_adapter = pyOpenSSLAdapterSafe(ssl_cert, ssl_key, ca_cert)
        if use_ssl:
            server.ssl_certificate = ssl_cert
            server.ssl_private_key = ssl_key
        return server


class CherryPyBackend:
    def __init__(self, host, port, use_ssl, ca_cert, ssl_key,
                 ssl_cert, hard_ssl_name_check, daemon_thread_pool_size):
        self.port = port
        self.use_ssl = use_ssl
        try:
            self.srv = bottle.run(
                host=host,
                port=port,
                server=CherryPyServer,
                quiet=False,
                use_ssl=use_ssl,
                ca_cert=ca_cert,
                ssl_key=ssl_key,
                ssl_cert=ssl_cert,
                daemon_thread_pool_size=daemon_thread_pool_size,
            )
        except socket.error as exp:
            msg = "Error: Sorry, the port %d is not free: %s" % (self.port, str(exp))
            raise PortNotFree(msg)
        except Exception as exc:
            logger.error("Error: the http port cannot be open: %s", traceback.format_exc())
            raise InvalidWorkDir(exc)

    def get_sockets(self):
        return []

    def stop(self):
        if self.use_ssl:
            return
        try:
            self.srv.stop()
        except Exception as exp:
            logger.warning("Cannot stop the CherryPy backend: %s", exp)

    def run(self):
        try:
            self.srv.start()
        except socket.error as exp:
            msg = "Error: Sorry, the port %d is not free: %s" % (self.port, str(exp))
            raise PortNotFree(msg)
        finally:
            try:
                self.srv.stop()
            except Exception:
                pass


class HTTPDaemon:
    def __init__(self, host, port, http_backend, use_ssl, ca_cert,
                 ssl_key, ssl_cert, hard_ssl_name_check, daemon_thread_pool_size):
        self.port = port
        self.host = host
        self.srv = None
        if self.port == 0:
            return

        self.use_ssl = use_ssl
        self.registered_fun = {}
        self.registered_fun_names = []
        self.registered_fun_defaults = {}

        protocol = "https" if use_ssl else "http"
        self.uri = "%s://%s:%s" % (protocol, self.host, self.port)
        logger.info("Opening HTTP socket at %s", self.uri)

        self.srv = CherryPyBackend(
            host,
            port,
            use_ssl,
            ca_cert,
            ssl_key,
            ssl_cert,
            hard_ssl_name_check,
            daemon_thread_pool_size,
        )
        logger.debug("HTTP backend initialized: %s", self.srv)
        self.lock = threading.RLock()

    def get_sockets(self):
        if self.port == 0 or self.srv is None:
            return []
        return self.srv.get_sockets()

    def run(self):
        self.srv.run()

    def register(self, obj):
        methods = inspect.getmembers(obj, predicate=inspect.ismethod)
        merge = [fname for (fname, _function) in methods if fname in self.registered_fun_names]
        if merge:
            methods_in = [
                method.__name__
                for method in obj.__class__.__dict__.values()
                if inspect.isfunction(method)
            ]
            methods = [method for method in methods if method[0] in methods_in]

        for fname, function in methods:
            if fname.startswith("_"):
                continue

            argspec = inspect.getfullargspec(function)
            args = list(argspec.args)
            defaults = argspec.defaults
            if defaults:
                default_args = zip(args[-len(defaults):], defaults)
                self.registered_fun_defaults[fname] = dict(default_args)
            if "self" in args:
                args.remove("self")

            self.registered_fun_names.append(fname)
            self.registered_fun[fname] = function

            def register_callback(callback_name, callback_args, callback, lock):
                def f_wrapper():
                    t0 = time.time()
                    args_time = aqu_lock_time = calling_time = json_time = 0
                    need_lock = getattr(callback, "need_lock", True)

                    values = {}
                    method = getattr(callback, "method", "get").lower()
                    for argument_name in callback_args:
                        value = None
                        if method == "post":
                            value = bottle.request.forms.get(argument_name, None)
                            if value is not None:
                                if isinstance(value, str):
                                    value = value.encode("latin-1")
                                value = zlib.decompress(value)
                                value = SafeUnpickler.loads(value)
                        elif method == "get":
                            value = bottle.request.query.get(argument_name, None)

                        if value is None:
                            default_args = self.registered_fun_defaults.get(callback_name, {})
                            if argument_name not in default_args:
                                raise ValueError("Missing argument %s" % argument_name)
                            value = default_args[argument_name]
                        values[argument_name] = value

                    t1 = time.time()
                    args_time = t1 - t0

                    if need_lock:
                        logger.debug("HTTP: calling lock for %s", callback_name)
                        lock.acquire()

                    t2 = time.time()
                    aqu_lock_time = t2 - t1

                    try:
                        result = callback(**values)
                    finally:
                        if need_lock:
                            lock.release()

                    t3 = time.time()
                    calling_time = t3 - t2

                    payload = json.dumps(result)
                    t4 = time.time()
                    json_time = t4 - t3

                    global_time = t4 - t0
                    logger.debug(
                        "Debug perf: %s [args:%s] [aqu_lock:%s][calling:%s] [json:%s] [global:%s]",
                        callback_name,
                        args_time,
                        aqu_lock_time,
                        calling_time,
                        json_time,
                        global_time,
                    )
                    timings = [
                        ("args", args_time),
                        ("aqulock", aqu_lock_time),
                        ("calling", calling_time),
                        ("json", json_time),
                        ("global", global_time),
                    ]
                    for key, elapsed in timings:
                        statsmgr.timing(
                            "http.%s.%s" % (callback_name, key),
                            elapsed,
                            "perf",
                        )

                    bottle.response.content_type = "application/json"
                    return payload

                bottle.route(
                    "/" + callback_name,
                    callback=f_wrapper,
                    method=getattr(callback, "method", "get").upper(),
                )
                dashed_name = callback_name.replace("_", "-")
                if dashed_name != callback_name:
                    bottle.route(
                        "/" + dashed_name,
                        callback=f_wrapper,
                        method=getattr(callback, "method", "get").upper(),
                    )

            register_callback(fname, args, function, self.lock)

        def slash():
            return "OK"

        bottle.route("/", callback=slash)

    def unregister(self, obj):
        return

    def handleRequests(self, socket_descriptor):
        self.srv.handle_request()

    def shutdown(self):
        if self.srv is not None:
            self.srv.stop()
            self.srv = None

    def get_socks_activity(self, timeout):
        try:
            ins, _, _ = select.select(self.get_sockets(), [], [], timeout)
        except select.error as exc:
            errnum, _ = exc
            if errnum == errno.EINTR:
                return []
            raise
        return ins


# TODO: clean this hack: see usage within basemodule & http_daemon.
daemon_inst = None
