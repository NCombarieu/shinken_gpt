"""Tests for libexec/notify_by_email.py against a local SMTP sink."""

import email
import email.policy
import importlib.util
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "libexec" / "notify_by_email.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


smtp_sink = _load("smtp_sink", ROOT / "integration" / "smtp_sink.py")
notify = _load("notify_by_email", SCRIPT)


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, timeout=60, check=False)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def sink(tmp_path):
    with smtp_sink.SMTPSink(tmp_path / "mails") as server:
        yield server


def parse(raw):
    return email.message_from_bytes(raw, policy=email.policy.default)


def test_script_is_python3_executable():
    first_line = SCRIPT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "#!/usr/bin/env python3"
    assert SCRIPT.stat().st_mode & 0o111


def test_service_html_notification(sink):
    proc = run("-n", "service", "-S", "127.0.0.1", "--smtp-port", str(sink.port),
               "-s", "shinken@example.com", "-r", "admin@example.org,ops@example.org",
               "-f", "html", "-u", "http://webui.example.org",
               "-c", "PROBLEM,,web-01,,192.0.2.10,,Sat 31 Oct 12:00:00 CET 2026",
               "-o", "HTTP,,CRITICAL,,CRITICAL - <b>500</b> é,,0d 0h 5m 2s",
               "-d", "Serveur web public", "-i", "Site indisponible", "-a", "Relancer nginx")
    assert proc.returncode == 0, proc.stderr
    assert len(sink.messages) == 1
    mail_from, rcpts, raw = sink.messages[0]
    assert mail_from == "shinken@example.com"
    assert rcpts == ["admin@example.org", "ops@example.org"]
    msg = parse(raw)
    assert msg["Subject"] == "CRITICAL on Host: web-01 about service HTTP since 0d 0h 5m 2s"
    assert msg["From"] == "shinken@example.com"
    assert msg.get_content_type() == "multipart/alternative"
    text = msg.get_body(("plain",)).get_content()
    html_part = msg.get_body(("html",)).get_content()
    assert "Service output: CRITICAL - <b>500</b> é" in text
    assert "Impact: Site indisponible" in text
    assert "http://webui.example.org/service/web-01/HTTP" in text
    # Plugin output must be escaped in the HTML part.
    assert "&lt;b&gt;500&lt;/b&gt; é" in html_part
    assert "<b>500</b>" not in html_part
    # Mail is also written to disk by the sink.
    assert len(list((Path(sink.outdir)).glob("*.eml"))) == 1


def test_host_txt_notification(sink):
    proc = run("-n", "host", "-S", "127.0.0.1", "--smtp-port", str(sink.port),
               "--sender", "shinken@example.com", "-r", "admin@example.org", "-f", "txt",
               "-p", "[lab] ", "-c", "RECOVERY,,db-01,,192.0.2.20,,now",
               "-o", "UP,,0d 0h 1m 0s")
    assert proc.returncode == 0, proc.stderr
    msg = parse(sink.messages[0][2])
    assert msg["Subject"] == "[lab] Host UP alert for db-01 since 0d 0h 1m 0s"
    assert msg.get_content_type() == "text/plain"
    assert "Notification type: RECOVERY" in msg.get_content()


def test_environment_macros_fallback(sink):
    env = {"NAGIOS_NOTIFICATIONTYPE": "PROBLEM", "NAGIOS_HOSTNAME": "env-host",
           "NAGIOS_HOSTADDRESS": "192.0.2.30", "NAGIOS_LONGDATETIME": "now",
           "NAGIOS_HOSTSTATE": "DOWN", "NAGIOS_HOSTDURATION": "1m", "PATH": "/usr/bin:/bin"}
    proc = subprocess.run([sys.executable, str(SCRIPT), "-S", "127.0.0.1", "--smtp-port",
                           str(sink.port), "-s", "shinken@example.com", "-r", "a@example.org"],
                          capture_output=True, text=True, env=env, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    assert parse(sink.messages[0][2])["Subject"] == "Host DOWN alert for env-host since 1m"


def test_authentication_with_password_file(tmp_path):
    secret = tmp_path / "smtp_password"
    secret.write_text("s3cret\n", encoding="utf-8")
    with smtp_sink.SMTPSink(credentials=("relay-user", "s3cret")) as server:
        proc = run("-t", "-S", "127.0.0.1", "--smtp-port", str(server.port),
                   "-s", "shinken@example.com", "-r", "a@example.org",
                   "--smtp-user", "relay-user", "--smtp-password-file", str(secret))
        assert proc.returncode == 0, proc.stderr
        assert len(server.messages) == 1

        secret.write_text("wrong\n", encoding="utf-8")
        proc = run("-t", "-S", "127.0.0.1", "--smtp-port", str(server.port),
                   "-s", "shinken@example.com", "-r", "a@example.org",
                   "--smtp-user", "relay-user", "--smtp-password-file", str(secret))
        assert proc.returncode == notify.EXIT_SEND_FAILED
        assert "SMTPAuthenticationError" in proc.stderr
        assert len(server.messages) == 1


def test_unreachable_relay_fails_with_clear_message():
    port = free_port()
    proc = run("-t", "-S", "127.0.0.1", "--smtp-port", str(port), "--smtp-timeout", "5",
               "-s", "shinken@example.com", "-r", "a@example.org")
    assert proc.returncode == notify.EXIT_SEND_FAILED
    assert "Failed to send notification to a@example.org via 127.0.0.1" in proc.stderr


def test_missing_recipient_and_password_file():
    proc = run("-t", "-S", "127.0.0.1")
    assert proc.returncode == notify.EXIT_USAGE
    assert "No recipient" in proc.stderr
    proc = run("-t", "-S", "127.0.0.1", "-r", "a@example.org", "--smtp-user", "u",
               "--smtp-password-file", "/nonexistent/secret")
    assert proc.returncode == notify.EXIT_USAGE
    assert "cannot read SMTP password file" in proc.stderr


RESOURCE_MACROS = {
    "PLUGINSDIR": str(ROOT / "libexec"),
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "25",
    "MAIL_FROM": "shinken@example.com",
}


def _resource_macros():
    macros = {}
    for cfg in ("paths.cfg", "notifications.cfg"):
        for line in (ROOT / "etc" / "resource.d" / cfg).read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\$(\w+)\$=(.*)$", line.strip())
            if match:
                macros[match.group(1)] = match.group(2)
    return macros


def test_resource_macros_follow_contract():
    macros = _resource_macros()
    assert macros["PLUGINSDIR"] == "/usr/local/lib/shinken/libexec"
    assert macros["LOCALPLUGINSDIR"] == "/usr/local/lib/shinken/plugins-local"
    assert macros["NAGIOSPLUGINSDIR"] == "/usr/lib/nagios/plugins"
    assert macros["USER1"] == "$NAGIOSPLUGINSDIR$"
    for name in ("SMTP_HOST", "SMTP_PORT", "MAIL_FROM"):
        assert name in macros


@pytest.mark.parametrize("cfg", sorted(p.name for p in (ROOT / "etc" / "commands").glob("*.cfg")
                                       if p.name.startswith(("notify-", "detailled-"))
                                       and "email" in p.name))
def test_shipped_email_commands_parse(cfg):
    text = (ROOT / "etc" / "commands" / cfg).read_text(encoding="utf-8")
    command_line = re.search(r"^\s*command_line\s+(.*)$", text, re.M).group(1)
    for name, value in RESOURCE_MACROS.items():
        command_line = command_line.replace("$%s$" % name, value)
    command_line = re.sub(r"\$\w+\$", "x", command_line)
    argv = shlex.split(command_line)
    assert argv[0] == str(SCRIPT)
    opts = notify.build_parser().parse_args(argv[1:])
    assert opts.smtp_server == "smtp.example.com"
    assert opts.smtp_port == 25
    assert opts.sender == "shinken@example.com"
    assert len(opts.commonmacros.split(",,")) == 4
