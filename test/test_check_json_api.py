"""Tests for containers/plugins/check_json_api (HTTP JSON API plugin)."""

import http.server
import importlib.machinery
import importlib.util
import json
import os
import threading

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "containers", "plugins", "check_json_api")


def load_plugin():
    loader = importlib.machinery.SourceFileLoader("check_json_api", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


plugin = load_plugin()

DOCUMENT = {"status": "UP", "queue": {"pending": 42}, "checks": [{"state": "ok"}], "ratio": "0.5"}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/echo-auth")
            self.end_headers()
            return
        if self.path == "/echo-auth":
            return self.reply(200, {"auth": self.headers.get("Authorization", "none")})
        if self.path == "/health":
            if self.headers.get("Authorization", "Bearer s3cr3t") != "Bearer s3cr3t":
                return self.reply(401, {"error": "denied"})
            return self.reply(200, DOCUMENT)
        if self.path == "/text":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"not json")
            return
        self.reply(404, {"error": "not found"})

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()
    server.server_close()


def run(capsys, *args):
    with pytest.raises(SystemExit) as exit_info:
        plugin.main(list(args))
    return exit_info.value.code, capsys.readouterr().out


@pytest.mark.parametrize("spec, value, alert", [
    ("10", 5, False), ("10", 11, True), ("10", -1, True),
    ("10:", 9, True), ("10:", 10, False),
    ("~:50", 51, True), ("~:50", -1000, False),
    ("10:20", 15, False), ("10:20", 21, True),
    ("@10:20", 15, True), ("@10:20", 21, False),
])
def test_nagios_ranges(spec, value, alert):
    assert plugin.Range(spec).alert(value) is alert


def test_extract_paths():
    assert plugin.extract(DOCUMENT, "queue.pending") == 42
    assert plugin.extract(DOCUMENT, "checks[0].state") == "ok"
    assert plugin.extract(DOCUMENT, "") == DOCUMENT
    for missing in ("nope", "checks[3].state", "status.x"):
        with pytest.raises(KeyError):
            plugin.extract(DOCUMENT, missing)


@pytest.mark.parametrize("args, code, text", [
    (["-p", "status", "-e", "UP"], 0, "status = UP"),
    (["-p", "status", "-e", "DOWN"], 2, "expected DOWN"),
    (["-p", "queue.pending", "-w", "30", "-c", "100"], 1, "warning 30"),
    (["-p", "queue.pending", "-w", "30", "-c", "40"], 2, "critical 40"),
    (["-p", "queue.pending", "-w", "100", "-c", "500"], 0, "queue.pending=42;100;500"),
    (["-p", "ratio", "-w", "1"], 0, "ratio = 0.5"),
    (["-p", "checks[0].state", "-e", "ok"], 0, "checks[0].state = ok"),
    (["-p", "nope"], 3, "not found"),
    (["-p", "status", "-w", "1"], 3, "is not a number"),
])
def test_health_endpoint(base_url, capsys, args, code, text):
    got, out = run(capsys, "-u", base_url + "/health", *args)
    assert got == code, out
    assert text in out


def test_http_error_is_critical(base_url, capsys):
    code, out = run(capsys, "-u", base_url + "/missing")
    assert code == 2 and "HTTP 404" in out


def test_expected_status(base_url, capsys):
    code, out = run(capsys, "-u", base_url + "/missing", "-s", "404", "-p", "error", "-e", "not found")
    assert code == 0, out


def test_not_json_is_unknown(base_url, capsys):
    code, out = run(capsys, "-u", base_url + "/text")
    assert code == 3 and "not JSON" in out


def test_connection_refused_is_critical(capsys):
    code, out = run(capsys, "-u", "http://127.0.0.1:1/")
    assert code == 2


def test_bearer_token_file(base_url, capsys, tmp_path):
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.write_text("s3cr3t\n")
    bad.write_text("wrong")
    assert run(capsys, "-u", base_url + "/health", "-p", "status", "-e", "UP",
               "--token-file", str(good))[0] == 0
    code, out = run(capsys, "-u", base_url + "/health", "--token-file", str(bad))
    assert code == 2 and "HTTP 401" in out
    code, out = run(capsys, "-u", base_url + "/health", "--token-file", str(tmp_path / "none"))
    assert code == 3 and "cannot read token file" in out


def test_bad_arguments_are_unknown(capsys):
    assert run(capsys)[0] == 3
    assert run(capsys, "-u", "http://x/", "-w", "abc")[0] == 3


def test_token_is_not_sent_to_redirect_target(base_url, capsys, tmp_path):
    token = tmp_path / "token"
    token.write_text("s3cr3t")
    code, out = run(capsys, "-u", base_url + "/redirect", "-p", "auth", "-e", "none",
                    "--token-file", str(token))
    assert code == 0, out
