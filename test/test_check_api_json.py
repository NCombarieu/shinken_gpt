"""Tests for libexec/check_api_json.py against a local HTTP server."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "libexec" / "check_api_json.py"

DOCUMENT = {
    "status": "ok",
    "queue": {"depth": 42},
    "nodes": [{"name": "a", "state": "up"}, {"name": "b", "state": "down"}],
    "quota": {"remaining": 5},
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            if self.headers.get("Authorization") not in (None, "Bearer s3cret"):
                self.send_response(403)
                self.end_headers()
                return
            body = json.dumps(DOCUMENT).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/html":
            body = b"<html>not json</html>"
            self.send_response(200)
        elif self.path == "/private":
            if self.headers.get("Authorization") != "Bearer s3cret":
                self.send_response(401)
                self.end_headers()
                return
            body = b'{"ok": true}'
            self.send_response(200)
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def base_url():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def run(*args):
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, timeout=30, check=False)
    return proc.returncode, proc.stdout.strip()


def test_expected_value_ok(base_url):
    code, out = run("-u", base_url + "/health", "-k", "status", "-e", "ok")
    assert code == 0, out
    assert out.startswith("API OK - status='ok'")
    assert "| time=" in out


def test_expected_value_mismatch_is_critical(base_url):
    code, out = run("-u", base_url + "/health", "-k", "nodes.1.state", "-e", "up")
    assert code == 2, out
    assert "attendu 'up'" in out


def test_upper_thresholds(base_url):
    assert run("-u", base_url + "/health", "-k", "queue.depth", "-w", "50", "-c", "100")[0] == 0
    assert run("-u", base_url + "/health", "-k", "queue.depth", "-w", "40", "-c", "100")[0] == 1
    code, out = run("-u", base_url + "/health", "-k", "queue.depth", "-w", "10", "-c", "40")
    assert code == 2
    assert "'queue.depth'=42;10;40" in out


def test_minimum_thresholds(base_url):
    assert run("-u", base_url + "/health", "-k", "quota.remaining", "--min",
               "-w", "3", "-c", "1")[0] == 0
    assert run("-u", base_url + "/health", "-k", "quota.remaining", "--min",
               "-w", "10", "-c", "1")[0] == 1
    assert run("-u", base_url + "/health", "-k", "quota.remaining", "--min",
               "-w", "10", "-c", "5")[0] == 2


def test_missing_field_is_unknown(base_url):
    code, out = run("-u", base_url + "/health", "-k", "absent.field")
    assert code == 3
    assert "absent" in out


def test_non_numeric_value_with_threshold_is_unknown(base_url):
    assert run("-u", base_url + "/health", "-k", "status", "-w", "1")[0] == 3


def test_http_error_is_critical(base_url):
    code, out = run("-u", base_url + "/missing", "-k", "x")
    assert code == 2
    assert "HTTP 404" in out


def test_non_json_is_critical(base_url):
    code, out = run("-u", base_url + "/html", "-k", "x")
    assert code == 2
    assert "non JSON" in out


def test_token_file_is_sent(base_url, tmp_path):
    assert run("-u", base_url + "/private", "-k", "ok")[0] == 2
    token = tmp_path / "token"
    token.write_text("s3cret\n")
    code, out = run("-u", base_url + "/private", "-k", "ok", "-e", "True",
                    "--token-file", str(token))
    assert code == 0, out


def test_unreadable_token_file_is_unknown(base_url, tmp_path):
    code, _ = run("-u", base_url + "/private", "-k", "ok",
                  "--token-file", str(tmp_path / "nope"))
    assert code == 3


def test_unreachable_is_critical():
    code, out = run("-u", "http://127.0.0.1:9/", "-k", "x", "-t", "2")
    assert code == 2
    assert "injoignable" in out
