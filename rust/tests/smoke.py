#!/usr/bin/env python3
"""Black-box contract tests. Python is test tooling, never an engine dependency."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

def object_cfg(kind, **attrs):
    return "define " + kind + " {\n" + "".join(f" {k} {v}\n" for k, v in attrs.items()) + "}\n"

def receive(sock, n):
    out = b""
    while len(out) < n:
        part = sock.recv(n - len(out))
        assert part, f"short Livestatus response ({len(out)}/{n})"
        out += part
    return out

def response(sock):
    header = receive(sock, 16)
    assert header[3:4] == b" " and header[-1:] == b"\n", header
    return int(header[:3]), receive(sock, int(header[4:15]))

def request(sock, query, keep=False):
    sock.sendall((query.rstrip("\n") + "\nOutputFormat: json\nResponseHeader: fixed16\n"
                  + ("KeepAlive: on\n" if keep else "") + "\n").encode())
    status, body = response(sock)
    assert status == 200, (query, status, body)
    return json.loads(body)

def eventually(fn, timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.04)
    raise AssertionError("condition did not become true")

def run_suite(binary):
    with tempfile.TemporaryDirectory(prefix="shinken-rust-") as temp:
        root = Path(temp)
        objects = root / "objects" / "nested"
        objects.mkdir(parents=True)
        main = root / "main.cfg"
        main.write_text("cfg_dir=objects\nresource_file=resource.cfg\ninterval_length=1\n"
                        "service_check_timeout=0.2\nhost_check_timeout=0.2\nmax_plugins_output_length=256\n")
        (root / "resource.cfg").write_text("$USER1$=/bin\n$ROOT$=" + temp + "\n")
        os.symlink(root / "objects", objects / "cycle")
        marker = root / "leaked-child"
        cfg = object_cfg("command", command_name="up", command_line="printf 'UP'")
        cfg += object_cfg("command", command_name="critical", command_line=r"printf 'CRITICAL | load=2\nlong output' \; exit 2")
        cfg += object_cfg("command", command_name="slow", command_line=rf"sleep 0.8 \; printf leaked > {marker}")
        cfg += object_cfg("command", command_name="big", command_line=r"$USER1$/sh -c 'yes X | head -c 4096'")
        cfg += object_cfg("host", name="generic-host", register="0 ; inline comment", check_command="up", max_check_attempts="1", contacts="alice")
        cfg += object_cfg("host", use="generic-host", host_name="edge", address="127.0.0.1", hostgroups="linux")
        cfg += object_cfg("host", use="generic-host", host_name="private", contacts="bob")
        cfg += object_cfg("service", name="generic-service", register="0", check_interval="0.3", retry_interval="0.05", max_check_attempts="2")
        cfg += object_cfg("service", use="generic-service", host_name="edge", service_description="load", check_command="critical")
        cfg += object_cfg("service", use="generic-service", host_name="edge", service_description="timeout", check_command="slow", check_interval="0")
        cfg += object_cfg("service", use="generic-service", host_name="edge", service_description="output", check_command="big", check_interval="0")
        cfg += object_cfg("service", use="generic-service", host_name="edge", service_description="passive", active_checks_enabled="0")
        cfg += object_cfg("service", use="generic-service", host_name="private", service_description="secret", active_checks_enabled="0")
        cfg += object_cfg("servicegroup", servicegroup_name="main", members="edge,load")
        cfg += object_cfg("contact", contact_name="alice", email="alice@example.invalid")
        cfg += object_cfg("contact", contact_name="bob", email="bob@example.invalid")
        (objects / "objects.cfg").write_text(cfg)
        subprocess.run([binary, "config-check", str(main)], check=True, timeout=10)
        once = subprocess.run([binary, "run", str(main), "--once", "--max-concurrent-checks", "2"],
                              text=True, capture_output=True, timeout=10, check=True)
        data = json.loads(once.stdout)
        assert data["hosts"][1][1] == 0, data
        states = {row[1]: row for row in data["services"][1:]}
        assert states["load"][2:4] == [2, 0], states
        assert states["passive"][4] == 0
        assert "timed out" in states["timeout"][-1]
        assert len(states["output"][-1]) <= 256
        time.sleep(0.9)
        assert not marker.exists(), "timed-out plugin descendant survived"

        unix = root / "live.sock"
        retention = root / "state.json"
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        log = root / "daemon.log"
        def start():
            output = log.open("a")
            proc = subprocess.Popen([binary, "run", str(main), "--livestatus-unix", str(unix),
                                     "--livestatus-tcp", f"127.0.0.1:{port}",
                                     "--state-file", str(retention), "--max-concurrent-checks", "2"],
                                    stdout=output, stderr=output)
            output.close()
            def ready():
                assert proc.poll() is None, log.read_text()
                return unix.exists()
            eventually(ready)
            return proc
        def connect(tcp=False):
            sock = socket.socket(socket.AF_INET if tcp else socket.AF_UNIX)
            sock.settimeout(5)
            sock.connect(("127.0.0.1", port) if tcp else str(unix))
            return sock
        def query(text, tcp=False):
            with connect(tcp) as sock:
                return request(sock, text)
        def command(text, success=True):
            with connect() as sock:
                sock.sendall((f"COMMAND [{int(time.time())}] " + text +
                              "\nResponseHeader: fixed16\n\n").encode())
                status, body = response(sock)
                assert (status == 200) == success, (text, status, body)
        proc = start()
        try:
            eventually(lambda: query("GET services\nColumns: state state_type\nFilter: description = load") == [[2, 1]])
            eventually(lambda: query("GET services\nColumns: state\nFilter: description = timeout") == [[3]])
            assert query("GET hosts\nColumns: state\nFilter: name = edge", tcp=True) == [[0]]
            assert query("GET services\nStats: state = 2\nStats: state = 3\nStatsOr: 2")[0][0] >= 2
            assert query("GET hosts\nColumns: name\nAuthUser: alice") == [["edge"]]
            assert query("GET services\nColumns: description\nAuthUser: nobody") == []
            assert query("GET status\nColumns: num_hosts num_services\nAuthUser: alice") == [[1, 4]]
            with connect() as sock:
                assert request(sock, "GET hosts\nColumns: name\nLimit: 1", keep=True)
                assert request(sock, "GET status\nColumns: enable_notifications") == [[0]]
            columns = json.loads((Path(__file__).parent / "thruk-columns.json").read_text())["columns"]
            for kind, names in columns.items():
                table = {"host": "hosts", "service": "services", "contact": "contacts",
                         "logs": "log"}.get(kind, kind)
                query("GET " + table + "\nColumns: " + " ".join(names))
            command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;2;CRITICAL passive | p=2")
            command("ACKNOWLEDGE_SVC_PROBLEM;edge;passive;2;0;1;alice;investigating")
            assert query("GET services\nColumns: state state_type acknowledged perf_data\nFilter: description = passive") == [[2, 1, 1, "p=2"]]
            now = int(time.time())
            command(f"SCHEDULE_SVC_DOWNTIME;edge;passive;{now-1};{now+600};1;0;601;alice;maintenance")
            assert query("GET services\nColumns: scheduled_downtime_depth\nFilter: description = passive") == [[1]]
            assert query("GET comments\nColumns: author comment") == [["alice", "investigating"]]
            assert len(query("GET downtimes\nColumns: id")) == 1
            command("DISABLE_SVC_CHECK;edge;load")
            command("DISABLE_PASSIVE_SVC_CHECKS;edge;passive")
            command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;0;ignored", success=False)
            command("ENABLE_PASSIVE_SVC_CHECKS;edge;passive")
            command("INVENTED_COMMAND", success=False)
            with connect() as sock:
                sock.sendall(b"GET invented\nResponseHeader: fixed16\n\n")
                assert response(sock)[0] != 200
            with connect() as sock:
                sock.sendall(b"GET hosts\nColumns: missing\nResponseHeader: fixed16\n\n")
                assert response(sock)[0] != 200
            # Real upstream client used by Thruk, when installed by the CI job.
            if os.environ.get("THRUK_PERL_LIB"):
                env = dict(os.environ, PERL5LIB=os.environ["THRUK_PERL_LIB"])
                subprocess.run(["perl", str(Path(__file__).parent / "thruk-client.pl"), str(unix)],
                               env=env, check=True, timeout=15)
        finally:
            proc.send_signal(signal.SIGTERM)
            try:
                code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise AssertionError(log.read_text())
            assert code == 0, log.read_text()
        assert not unix.exists(), "socket was not cleaned up"
        assert retention.exists()
        proc = start()
        try:
            assert query("GET services\nColumns: state acknowledged\nFilter: description = passive") == [[2, 1]]
            assert query("GET services\nColumns: active_checks_enabled\nFilter: description = load") == [[0]]
            assert query("GET services\nColumns: scheduled_downtime_depth\nFilter: description = passive") == [[1]]
            command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;0;recovered")
            assert query("GET services\nColumns: state acknowledged\nFilter: description = passive") == [[0, 0]]
        finally:
            proc.terminate()
            assert proc.wait(timeout=10) == 0, log.read_text()

        sentinel = root / "sentinel"
        sentinel.write_text("do not delete")
        failed = subprocess.run([binary, "run", str(main), "--livestatus-unix", str(sentinel)],
                                capture_output=True, timeout=10)
        assert failed.returncode != 0 and sentinel.read_text() == "do not delete"
        main.write_text("cfg_file=missing.cfg\n")
        assert subprocess.run([binary, "config-check", str(main)], capture_output=True, timeout=10).returncode != 0
        print("PASS: config tree, plugins, timeouts, states, sockets, Thruk queries/commands and retention")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    run_suite(str(Path(parser.parse_args().binary).resolve()))
