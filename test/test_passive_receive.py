"""Tests for containers/shinken-passive-receive (passive results over SSH)."""

import importlib.machinery
import importlib.util
import io
import json
import os
import socketserver
import threading
import time

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "containers", "shinken-passive-receive")


def load_receiver():
    loader = importlib.machinery.SourceFileLoader("shinken_passive_receive", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


receiver = load_receiver()


class FakeLivestatus(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, hosts, services):
        self.hosts = hosts          # {host: accept_passive}
        self.services = services    # {(host, service): accept_passive}
        self.commands = []
        super().__init__(("127.0.0.1", 0), FakeLivestatusHandler)


class FakeLivestatusHandler(socketserver.StreamRequestHandler):
    def handle(self):
        request = self.rfile.read().decode("utf-8")
        lines = request.splitlines()
        if lines and lines[0].startswith("COMMAND "):
            self.server.commands.extend(l[len("COMMAND "):] for l in lines if l)
            return
        filt = next(l for l in lines if l.startswith("Filter: "))
        name = filt.split(" = ", 1)[1]
        if lines[0] == "GET hosts":
            rows = [[name, int(self.server.hosts[name])]] if name in self.server.hosts else []
        else:
            rows = [[svc, int(ok)] for (host, svc), ok in self.server.services.items() if host == name]
        self.wfile.write(json.dumps(rows).encode("utf-8"))


@pytest.fixture
def livestatus(monkeypatch):
    server = FakeLivestatus(
        hosts={"srv-web01": True, "srv-db01": True},
        services={("srv-web01", "Backup"): True, ("srv-web01", "Disk"): False},
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("SHINKEN_LIVESTATUS", "127.0.0.1:%d" % server.server_address[1])
    monkeypatch.setenv("SHINKEN_PASSIVE_HOST", "srv-web01")
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    yield server
    server.shutdown()
    server.server_close()


def run(monkeypatch, capsys, data):
    monkeypatch.setattr("sys.stdin", io.StringIO(data))
    code = receiver.main([])
    return code, capsys.readouterr().out


def sent(server, count):
    """Commands received by the fake Livestatus (its handler runs in a thread)."""
    # monotonic: the legacy Shinken test helpers replace time.time globally.
    deadline = time.monotonic() + 5
    while len(server.commands) < count and time.monotonic() < deadline:
        time.sleep(0.01)
    return server.commands


def test_nsca_service_result_is_forwarded_with_server_timestamp(livestatus, monkeypatch, capsys):
    before = int(time.time())
    code, out = run(monkeypatch, capsys, "srv-web01\tBackup\t1\tWARNING - 30h old|age=30h\n")
    assert code == 0, out
    assert "forwarded=1 rejected=0" in out
    (cmd,) = sent(livestatus, 1)
    ts, rest = cmd.split("] ", 1)
    assert int(ts[1:]) >= before
    assert rest == "PROCESS_SERVICE_CHECK_RESULT;srv-web01;Backup;1;WARNING - 30h old|age=30h"


def test_client_timestamp_is_replaced(livestatus, monkeypatch, capsys):
    code, out = run(monkeypatch, capsys,
                    "[1] PROCESS_SERVICE_CHECK_RESULT;srv-web01;Backup;0;OK - done\n")
    assert code == 0, out
    assert not sent(livestatus, 1)[0].startswith("[1] ")


def test_host_result(livestatus, monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, "srv-web01\t0\tUP - pushed\n")
    assert code == 0, out
    assert sent(livestatus, 1)[0].endswith("PROCESS_HOST_CHECK_RESULT;srv-web01;0;UP - pushed")


@pytest.mark.parametrize("line, reason", [
    ("srv-db01\tBackup\t0\tOK", "may only send results for srv-web01"),
    ("srv-web01\tNope\t0\tOK", "is not defined"),
    ("srv-web01\tDisk\t0\tOK", "does not accept passive checks"),
    ("srv-web01\tBackup\tOK\tOK", "return code must be"),
    ("srv-web01\tBackup\t4\tOK", "return code must be"),
    ("srv-web01\tBa;ckup\t0\tOK", "invalid service name"),
    ("srv-web01\tBackup\t0\t", "empty output"),
    ("[1] DISABLE_NOTIFICATIONS", "only PROCESS_SERVICE_CHECK_RESULT"),
    ("[1] RESTART_PROGRAM;", "only PROCESS_SERVICE_CHECK_RESULT"),
    ("just garbage", "expected host"),
])
def test_rejections(livestatus, monkeypatch, capsys, line, reason):
    code, out = run(monkeypatch, capsys, line + "\n")
    assert code == 1
    assert reason in out
    assert livestatus.commands == []


def test_control_characters_are_stripped_from_output(livestatus, monkeypatch, capsys):
    code, out = run(monkeypatch, capsys, "srv-web01\tBackup\t0\tOK\x1b[31m red\x07\n")
    assert code == 0, out
    assert sent(livestatus, 1)[0].endswith(";0;OK[31m red")


def test_partial_batch_forwards_valid_lines(livestatus, monkeypatch, capsys):
    code, out = run(monkeypatch, capsys,
                    "# comment\n\nsrv-web01\tBackup\t0\tOK\nsrv-web01\tNope\t0\tOK\n")
    assert code == 1
    assert "forwarded=1 rejected=1" in out
    assert len(sent(livestatus, 1)) == 1


def test_unbound_key_is_refused(livestatus, monkeypatch, capsys):
    monkeypatch.delenv("SHINKEN_PASSIVE_HOST")
    code, out = run(monkeypatch, capsys, "srv-web01\tBackup\t0\tOK\n")
    assert code == 2
    assert "not bound to a host" in out


def test_remote_command_is_refused(livestatus, monkeypatch, capsys):
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "cat /etc/passwd")
    code, out = run(monkeypatch, capsys, "")
    assert code == 2
    assert livestatus.commands == []


def test_livestatus_down(monkeypatch, capsys):
    monkeypatch.setenv("SHINKEN_LIVESTATUS", "127.0.0.1:1")
    monkeypatch.setenv("SHINKEN_PASSIVE_HOST", "srv-web01")
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    code, out = run(monkeypatch, capsys, "srv-web01\tBackup\t0\tOK\n")
    assert code == 2
    assert "Livestatus unreachable" in out


# --- key -> host binding from the authenticated key (sshd ExposeAuthInfo) ---

KEY_WEB = "AAAAC3NzaC1lZDI1NTE5AAAAIWebKeyBlob"
KEY_NOBIND = "AAAAC3NzaC1lZDI1NTE5AAAAINoBindBlob"


@pytest.fixture
def ssh_files(tmp_path):
    authorized = tmp_path / "authorized_keys"
    authorized.write_text(
        f'environment="SHINKEN_PASSIVE_HOST=srv-web01" ssh-ed25519 {KEY_WEB} srv-web01\n'
        f"ssh-ed25519 {KEY_NOBIND} nobind\n"
    )
    return tmp_path, authorized


def auth_info(directory, blob):
    path = directory / "auth_info"
    path.write_text(f"publickey ssh-ed25519 {blob}\n")
    return str(path)


def test_host_comes_from_authenticated_key(ssh_files):
    directory, authorized = ssh_files
    assert receiver.bound_host_for_key(auth_info(directory, KEY_WEB), str(authorized)) == "srv-web01"
    assert receiver.bound_host_for_key(auth_info(directory, KEY_NOBIND), str(authorized)) is None
    assert receiver.bound_host_for_key(auth_info(directory, "AAAAunknown"), str(authorized)) is None
    assert receiver.bound_host_for_key(str(directory / "missing"), str(authorized)) is None


def test_environment_cannot_override_binding(livestatus, monkeypatch, capsys, ssh_files):
    """A ~/.ssh/environment setting SHINKEN_PASSIVE_HOST must be ignored."""
    directory, authorized = ssh_files
    monkeypatch.setenv("SHINKEN_PASSIVE_HOST", "srv-db01")
    monkeypatch.setenv("SSH_USER_AUTH", auth_info(directory, KEY_WEB))
    monkeypatch.setattr("sys.stdin", io.StringIO("srv-db01\tBackup\t0\tOK\n"))
    code = receiver.main(["--livestatus", os.environ["SHINKEN_LIVESTATUS"],
                          "--authorized-keys", str(authorized)])
    out = capsys.readouterr().out
    assert code == 1 and "may only send results for srv-web01" in out


def test_unbound_authenticated_key_is_refused(livestatus, monkeypatch, capsys, ssh_files):
    directory, authorized = ssh_files
    monkeypatch.setenv("SSH_USER_AUTH", auth_info(directory, KEY_NOBIND))
    monkeypatch.setattr("sys.stdin", io.StringIO("srv-web01\tBackup\t0\tOK\n"))
    code = receiver.main(["--authorized-keys", str(authorized)])
    assert code == 2 and "not bound to a host" in capsys.readouterr().out


@pytest.mark.parametrize("separator", [" ", " ", "\x85", "\x0b", "\x0c", "\x1c", "\x1e"])
def test_line_separators_cannot_inject_commands(livestatus, monkeypatch, capsys, separator):
    data = f"srv-web01\tBackup\t0\tok{separator}COMMAND [1] DISABLE_NOTIFICATIONS\n"
    code, out = run(monkeypatch, capsys, data)
    assert code == 0, out
    (cmd,) = sent(livestatus, 1)
    assert len(cmd.splitlines()) == 1
    assert cmd.endswith(";0;okCOMMAND [1] DISABLE_NOTIFICATIONS")


@pytest.mark.parametrize("name", ["Back up", "Backup\\", "Back\x85up"])
def test_names_with_separators_are_rejected(livestatus, monkeypatch, capsys, name):
    code, out = run(monkeypatch, capsys, f"srv-web01\t{name}\t0\tOK\n")
    assert code == 1 and "invalid service name" in out


def test_send_commands_refuses_multiline():
    with pytest.raises(ValueError):
        receiver.Livestatus("127.0.0.1:1").send_commands(["[1] X;a b"])
