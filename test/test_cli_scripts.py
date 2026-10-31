"""Smoke tests for the bin/ and libexec/ scripts that have no .py suffix."""

import subprocess
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _python_scripts():
    for folder in ("bin", "libexec"):
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            first = path.read_bytes().split(b"\n", 1)[0]
            if path.suffix == ".py" or (not path.suffix and b"python" in first):
                yield path


@pytest.mark.parametrize("path", list(_python_scripts()), ids=lambda p: str(p.relative_to(ROOT)))
def test_script_compiles_without_warning(path):
    source = path.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        compile(source, str(path), "exec")


# Scripts run as-is (libexec is not rewritten by pip); daemon launchers are
# rewritten by pip at install time and are checked elsewhere.
def _shebang_checked():
    for path in _python_scripts():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("libexec/") or rel in (
                "bin/shinken", "bin/shinken-discovery", "bin/shinken-healthcheck"):
            yield path


@pytest.mark.parametrize("path", list(_shebang_checked()),
                         ids=lambda p: str(p.relative_to(ROOT)))
def test_script_has_python3_shebang(path):
    first = path.read_bytes().split(b"\n", 1)[0]
    assert first == b"#!/usr/bin/env python3"


def _run(*args, cwd=None):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,
                          timeout=60, check=False, cwd=cwd)


def test_shinken_cli_help_and_list(tmp_path):
    ini = tmp_path / "shinken.ini"
    proc = _run(str(ROOT / "bin" / "shinken"), "--help")
    assert proc.returncode == 0, proc.stderr
    assert "--list" in proc.stdout
    proc = _run(str(ROOT / "bin" / "shinken"), "--init", "-c", str(ini))
    assert proc.returncode == 0, proc.stderr
    assert "[paths]" in ini.read_text(encoding="utf-8")
    proc = _run(str(ROOT / "bin" / "shinken"), "--list", "-c", str(ini))
    assert proc.returncode == 0, proc.stderr
    for keyword in ("install", "search", "inventory", "doc-serve"):
        assert keyword in proc.stdout
    proc = _run(str(ROOT / "bin" / "shinken"), "-c", str(ini), "no-such-command")
    assert proc.returncode != 0


def test_shinken_discovery_help(tmp_path):
    proc = _run(str(ROOT / "bin" / "shinken-discovery"), "--help", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "--cfg-input" in proc.stdout


def _load_healthcheck():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        "shinken_healthcheck", str(ROOT / "bin" / "shinken-healthcheck"))
    spec = importlib.util.spec_from_loader("shinken_healthcheck", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_healthcheck_detects_role_from_container_cmdline(tmp_path, monkeypatch):
    healthcheck = _load_healthcheck()
    monkeypatch.delenv("SHINKEN_ROLE", raising=False)
    cmdline = tmp_path / "cmdline"
    cmdline.write_bytes(b"/usr/bin/tini\0--\0/usr/local/bin/shinken-entrypoint\0poller\0")
    assert healthcheck.detect_role(str(cmdline)) == "poller"
    cmdline.write_bytes(b"/usr/bin/python3\0/usr/local/bin/shinken-broker\0-c\0x\0")
    assert healthcheck.detect_role(str(cmdline)) == "broker"
    cmdline.write_bytes(b"/bin/sh\0")
    assert healthcheck.detect_role(str(cmdline)) is None
    monkeypatch.setenv("SHINKEN_ROLE", "arbiter")
    assert healthcheck.detect_role(str(cmdline)) == "arbiter"


def test_healthcheck_probe_reflects_daemon_state():
    import http.server
    import threading

    class Pong(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b'"pong"' if self.path == "/ping" else b"nope"
            self.send_response(200 if self.path == "/ping" else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pong)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    script = str(ROOT / "bin" / "shinken-healthcheck")
    try:
        proc = _run(script, "--daemon", "scheduler", "--daemon-port", str(port))
        assert proc.returncode == 0, proc.stdout
        assert proc.stdout.startswith("OK - scheduler")
        # Livestatus required but absent: unhealthy.
        proc = _run(script, "--daemon", "broker", "--daemon-port", str(port),
                    "--livestatus", "--port", str(port), "--timeout", "2")
        assert proc.returncode == 1
        assert "livestatus" in proc.stdout
    finally:
        server.shutdown()
        server.server_close()
    proc = _run(script, "--daemon", "scheduler", "--daemon-port", str(port), "--timeout", "2")
    assert proc.returncode == 1
    assert proc.stdout.startswith("CRITICAL - scheduler")


def test_modernization_audit_fails_on_syntax_error(tmp_path, capsys):
    import importlib.util
    import json

    spec = importlib.util.spec_from_file_location(
        "modernization_audit", ROOT / "integration" / "modernization_audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "tool").write_text("#!/usr/bin/env python3\nprint 'py2'\n")
    (tmp_path / "libexec").mkdir()
    (tmp_path / "libexec" / "ok.py").write_text("import re\nre.compile('\\d')\n")
    audit.ROOT = tmp_path
    assert audit.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["syntax_errors"][0]["path"] == "bin/tool"
    assert report["counts"]["syntax_warnings"] == 1
    (tmp_path / "bin" / "tool").write_text("#!/usr/bin/env python3\nprint('py3')\n")
    assert audit.main() == 0
