#!/usr/bin/env python3
"""Small dependency-free status UI for the Shinken broker.

This is intentionally not a compatibility copy of the historical WebUI or
Livestatus modules. It consumes broker events directly and exposes a compact
HTML dashboard plus a JSON status endpoint using only the Python standard
library.
"""

from __future__ import annotations

import html
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from shinken.basemodule import BaseModule
from shinken.log import logger

properties = {
    "daemons": ["broker"],
    "type": "status_webui",
    "external": False,
}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def get_instance(mod_conf):
    return StatusWebUI(mod_conf)


class StatusWebUI(BaseModule):
    """In-process broker module exposing current host/service state."""

    def __init__(self, mod_conf):
        super().__init__(mod_conf)
        self.bind_host = str(getattr(mod_conf, "host", "127.0.0.1"))
        self.port = int(getattr(mod_conf, "port", 8080))
        self._lock = threading.RLock()
        self._hosts: dict[str, dict[str, Any]] = {}
        self._services: dict[str, dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=200)
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self.started_at = time.time()

    def init(self):
        module = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ShinkenStatus/1"

            def log_message(self, fmt, *args):
                logger.debug("[status-webui] " + fmt, *args)

            def do_GET(self):
                if self.path == "/healthz":
                    self._send(200, b"ok\n", "text/plain; charset=utf-8")
                    return
                if self.path == "/api/status":
                    payload = json.dumps(module.snapshot(), sort_keys=True).encode("utf-8")
                    self._send(200, payload, "application/json; charset=utf-8")
                    return
                if self.path == "/" or self.path.startswith("/?"):
                    payload = module.render_html().encode("utf-8")
                    self._send(200, payload, "text/html; charset=utf-8")
                    return
                self._send(404, b"not found\n", "text/plain; charset=utf-8")

            def _send(self, status, payload, content_type):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
                self.end_headers()
                self.wfile.write(payload)

        self._server = ThreadingHTTPServer((self.bind_host, self.port), Handler)
        self._server.daemon_threads = True
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="shinken-status-webui",
            daemon=True,
        )
        self._server_thread.start()
        logger.info("[status-webui] listening on http://%s:%s", self.bind_host, self.port)

    def manage_brok(self, brok):
        data = _json_safe(dict(brok.data))
        brok_type = str(brok.type)
        event = {
            "type": brok_type,
            "timestamp": time.time(),
            "data": data,
        }
        with self._lock:
            self._events.append(event)
            if "host" in brok_type and "status" in brok_type:
                name = data.get("host_name") or data.get("name")
                if name:
                    self._hosts[str(name)] = data
            if "service" in brok_type and "status" in brok_type:
                host_name = data.get("host_name", "")
                description = data.get("service_description") or data.get("description") or data.get("name")
                if description:
                    key = f"{host_name}/{description}"
                    self._services[key] = data

    def snapshot(self):
        with self._lock:
            return {
                "generated_at": time.time(),
                "uptime": time.time() - self.started_at,
                "hosts": dict(self._hosts),
                "services": dict(self._services),
                "recent_events": list(self._events),
            }

    @staticmethod
    def _state(data):
        return data.get("state", data.get("state_id", data.get("current_state", "?")))

    @staticmethod
    def _output(data):
        return data.get("output", data.get("plugin_output", data.get("long_output", "")))

    def render_html(self):
        snapshot = self.snapshot()

        def row(name, data):
            state = html.escape(str(self._state(data)))
            output = html.escape(str(self._output(data)))
            return f"<tr><td>{html.escape(name)}</td><td>{state}</td><td>{output}</td></tr>"

        host_rows = "".join(row(name, data) for name, data in sorted(snapshot["hosts"].items()))
        service_rows = "".join(row(name, data) for name, data in sorted(snapshot["services"].items()))
        if not host_rows:
            host_rows = '<tr><td colspan="3">No host status received yet</td></tr>'
        if not service_rows:
            service_rows = '<tr><td colspan="3">No service status received yet</td></tr>'

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shinken Status</title>
<style>
body {{ font: 15px system-ui, sans-serif; margin: 0; background: #111827; color: #e5e7eb; }}
main {{ max-width: 1200px; margin: auto; padding: 2rem; }}
h1 {{ margin-bottom: .25rem; }} .muted {{ color: #9ca3af; }}
section {{ background: #1f2937; margin-top: 1.5rem; padding: 1rem; border-radius: .75rem; }}
table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: .6rem; text-align: left; border-bottom: 1px solid #374151; }}
code {{ color: #93c5fd; }}
</style>
</head>
<body><main>
<h1>Shinken Status</h1>
<p class="muted">Modern dependency-free broker view · JSON: <code>/api/status</code></p>
<section><h2>Hosts ({len(snapshot['hosts'])})</h2><table><thead><tr><th>Host</th><th>State</th><th>Output</th></tr></thead><tbody>{host_rows}</tbody></table></section>
<section><h2>Services ({len(snapshot['services'])})</h2><table><thead><tr><th>Service</th><th>State</th><th>Output</th></tr></thead><tbody>{service_rows}</tbody></table></section>
</main></body></html>"""
