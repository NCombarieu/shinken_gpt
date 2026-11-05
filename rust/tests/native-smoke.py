#!/usr/bin/env python3
"""Native integration scenarios: dependency gates, handlers, escalations and live reload."""
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from smoke import object_cfg as obj, eventually, request, response

BINARY = str(Path(sys.argv[1]).resolve())

class Daemon:
    def __init__(self, root, cfg, settings=""):
        self.root = root
        self.cfg = root / "objects.cfg"
        self.main = root / "main.cfg"
        self.endpoint = root / "live.sock"
        self.log = root / "daemon.log"
        self.retained = root / "state.json"
        self.cfg.write_text(cfg)
        self.main.write_text("cfg_file=objects.cfg\ninterval_length=1\nuse_timezone=UTC\n" + settings)
        out = self.log.open("w")
        self.proc = subprocess.Popen([BINARY, "run", str(self.main), "--livestatus-unix",
            str(self.endpoint), "--state-file", str(self.retained)], stdout=out, stderr=out)
        out.close()
        def ready():
            assert self.proc.poll() is None, self.log.read_text()
            return self.endpoint.exists()
        eventually(ready)

    def connect(self):
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(5)
        sock.connect(str(self.endpoint))
        return sock

    def query(self, text):
        with self.connect() as sock:
            return request(sock, text)

    def command(self, text, expected=200):
        with self.connect() as sock:
            sock.sendall((f"COMMAND [{int(time.time())}] " + text + "\nResponseHeader: fixed16\n\n").encode())
            status, body = response(sock)
            assert status == expected, (text, status, body, self.log.read_text())

    def svc(self, name, columns="state state_type has_been_checked"):
        return self.query("GET services\nColumns: " + columns + "\nFilter: description = " + name)

    def host(self, name, columns="state has_been_checked"):
        return self.query("GET hosts\nColumns: " + columns + "\nFilter: name = " + name)

    def force(self, name):
        self.command(f"SCHEDULE_FORCED_SVC_CHECK;edge;{name};{int(time.time())}")

    def close(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
        assert self.proc.wait(timeout=10) == 0, self.log.read_text()

def read_lines(path):
    return path.read_text().splitlines() if path.exists() else []

def rule_scenarios(root):
    records = root / "handlers"
    alerts = root / "alerts"
    marker = root / "handler-leak"
    code = root / "code"
    code.write_text("2")
    check = root / "check.sh"
    check.write_text(f"printf 'captured output'\nexit \"$(cat {code})\"\n")
    slow = root / "slow-handler.sh"
    slow.write_text(f"sleep 0.8\nprintf leaked > {marker}\n")
    cfg = obj("command", command_name="up", command_line="printf UP")
    cfg += obj("command", command_name="down", command_line=r"printf DOWN \; exit 2")
    cfg += obj("command", command_name="dynamic", command_line=f"/bin/sh {check}")
    cfg += obj("command", command_name="handler",
        command_line=rf"printf '%s\n' '$ARG1$|$SERVICEDESC$|$SERVICESTATE$|$SERVICESTATETYPE$|$SERVICEATTEMPT$' >> {records}")
    cfg += obj("command", command_name="slow-handler", command_line=f"/bin/sh {slow}")
    cfg += obj("command", command_name="notify",
        command_line=rf"printf '%s\n' '$SERVICEDESC$|$CONTACTNAME$|$NOTIFICATIONTYPE$|$NOTIFICATIONNUMBER$' >> {alerts}")
    cfg += obj("host", host_name="edge")
    cfg += obj("host", host_name="router")
    cfg += obj("host", host_name="alternate")
    cfg += obj("host", host_name="child", parents="router", check_command="down", max_check_attempts="1", check_interval="0.2")
    cfg += obj("host", host_name="redundant", parents="router,alternate", check_command="down", max_check_attempts="1", check_interval="0.2")
    for contact in ["junior", "senior", "manager"]:
        cfg += obj("contact", contact_name=contact, service_notification_commands="notify")
    for service in ["upstream", "bridge", "leaf", "handler-service", "timeout-handler", "escalated"]:
        attrs = dict(host_name="edge", service_description=service, active_checks_enabled="0",
            contacts="junior", notifications_enabled="0", notification_interval="0")
        if service == "leaf":
            attrs.update(check_command="up", active_checks_enabled="1", check_interval="0.2", max_check_attempts="1")
        if service == "handler-service":
            attrs.update(check_command="dynamic", event_handler="handler!LOCAL", max_check_attempts="3")
        if service == "timeout-handler":
            attrs.update(event_handler="slow-handler")
        if service == "escalated":
            attrs.update(notifications_enabled="1", notification_interval="1")
        cfg += obj("service", **attrs)
    cfg += obj("servicedependency", host_name="edge", service_description="upstream",
        dependent_service_description="bridge", execution_failure_criteria="p,c",
        notification_failure_criteria="p,c")
    cfg += obj("servicedependency", host_name="edge", service_description="bridge",
        dependent_service_description="leaf", execution_failure_criteria="c",
        notification_failure_criteria="c", inherits_parent="1")
    cfg += obj("serviceescalation", host_name="edge", service_description="escalated",
        first_notification="2", last_notification="0", contacts="senior", notification_interval="0")
    cfg += obj("serviceescalation", host_name="edge", service_description="escalated",
        first_notification="2", last_notification="3", contacts="manager", notification_interval="2")
    daemon = Daemon(root, cfg, "global_service_event_handler=handler!GLOBAL\nevent_handler_timeout=0.2\n")
    try:
        eventually(lambda: daemon.host("child") == [[1, 1]])
        daemon.command("PROCESS_HOST_CHECK_RESULT;router;1;router down")
        eventually(lambda: daemon.host("child") == [[2, 1]])
        eventually(lambda: daemon.host("redundant") == [[1, 1]])
        daemon.command("PROCESS_HOST_CHECK_RESULT;router;0;router recovered")
        eventually(lambda: daemon.host("child") == [[1, 1]])

        assert daemon.svc("leaf", "has_been_checked execution_dependencies_failed") == [[0, 1]]
        daemon.force("leaf")
        eventually(lambda: daemon.svc("leaf", "has_been_checked") == [[1]])
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;upstream;2;upstream critical")
        daemon.command("DISABLE_SVC_CHECK;edge;leaf")
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;leaf;2;dependent problem")
        daemon.command("ENABLE_SVC_NOTIFICATIONS;edge;leaf")
        time.sleep(0.4)
        assert not read_lines(alerts), "notification dependency was ignored"
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;upstream;0;upstream recovered")
        eventually(lambda: any(line.startswith("leaf|") for line in read_lines(alerts)))
        daemon.command("ENABLE_SVC_CHECK;edge;leaf")
        eventually(lambda: daemon.svc("leaf", "state") == [[0]])

        # Every SOFT attempt, first HARD problem and recovery; global runs before local.
        def handler_lines():
            return [line for line in read_lines(records) if "|handler-service|" in line]
        for attempt, kind in [(1, "SOFT"), (2, "SOFT"), (3, "HARD")]:
            daemon.force("handler-service")
            eventually(lambda: len(handler_lines()) >= attempt * 2)
            assert handler_lines()[-2:] == [
                f"GLOBAL|handler-service|CRITICAL|{kind}|{attempt}",
                f"LOCAL|handler-service|CRITICAL|{kind}|{attempt}"], handler_lines()
        daemon.force("handler-service")
        time.sleep(0.4)
        assert len(handler_lines()) == 6, "persistent HARD problem reran handler"
        code.write_text("0")
        daemon.force("handler-service")
        eventually(lambda: len(handler_lines()) == 8)
        assert handler_lines()[-1] == "LOCAL|handler-service|OK|HARD|1", handler_lines()
        daemon.command("DISABLE_SVC_EVENT_HANDLER;edge;handler-service")
        code.write_text("2")
        daemon.force("handler-service")
        time.sleep(0.4)
        assert len(handler_lines()) == 8, "disabled handler executed"
        daemon.command("ENABLE_SVC_EVENT_HANDLER;edge;handler-service")
        code.write_text("0")
        daemon.force("handler-service")
        eventually(lambda: len(handler_lines()) == 10)
        assert handler_lines()[-1] == "LOCAL|handler-service|OK|SOFT|1", handler_lines()
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;timeout-handler;2;fail")
        eventually(lambda: daemon.svc("timeout-handler", "last_event_handler_exit_code") == [[3]])
        time.sleep(0.9)
        assert not marker.exists(), "timed-out handler descendant survived"

        # Overlapping escalations union contacts and use the shortest (zero) interval.
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;escalated;2;escalate")
        def escalated():
            return [line for line in read_lines(alerts) if line.startswith("escalated|")]
        eventually(lambda: len(escalated()) >= 1)
        assert escalated() == ["escalated|junior|PROBLEM|1"], escalated()
        start = time.monotonic()
        eventually(lambda: len(escalated()) >= 3)
        assert time.monotonic() - start > 0.65, "escalation bypassed notification interval"
        assert set(escalated()[1:]) == {"escalated|senior|PROBLEM|2", "escalated|manager|PROBLEM|2"}
        time.sleep(1.3)
        assert len(escalated()) == 3, "zero escalation interval repeated"
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;escalated;0;recovered")
        eventually(lambda: len(escalated()) == 6)
        assert set(escalated()[3:]) == {f"escalated|{c}|RECOVERY|0" for c in ["junior", "senior", "manager"]}
    finally:
        daemon.close()
    print("PASS: topology, dependency inheritance, forced checks, handler sequencing/timeout and escalation routing")

def reload_scenarios(root):
    begun = root / "begun"
    leaked = root / "obsolete-result"
    script = root / "slow-check.sh"
    script.write_text(f"printf started > {begun}\nsleep 2\nprintf leaked > {leaked}\nprintf OLD\nexit 2\n")
    cfg = obj("command", command_name="up", command_line="printf NEW")
    cfg += obj("command", command_name="slow", command_line=f"/bin/sh {script}")
    cfg += obj("host", host_name="edge")
    cfg += obj("host", host_name="removed")
    cfg += obj("service", host_name="edge", service_description="saved", active_checks_enabled="0")
    cfg += obj("service", host_name="edge", service_description="inflight", check_command="slow", check_interval="20", max_check_attempts="1")
    daemon = Daemon(root, cfg, "enable_notifications=0\nservice_check_timeout=5\n")
    keep = daemon.connect()
    try:
        eventually(begun.exists)
        inode = daemon.endpoint.stat().st_ino
        pid = request(keep, "GET status\nColumns: nagios_pid", keep=True)[0][0]
        daemon.command("PROCESS_SERVICE_CHECK_RESULT;edge;saved;2;preserve me")
        daemon.command("ACKNOWLEDGE_SVC_PROBLEM;edge;saved;2;0;1;operator;investigating")
        daemon.command("ADD_SVC_COMMENT;edge;saved;0;operator;survives reload")
        now = int(time.time())
        daemon.command(f"SCHEDULE_SVC_DOWNTIME;edge;saved;{now-1};{now+600};1;0;601;operator;maintenance")
        replacement = cfg.replace(" host_name removed\n", " host_name added\n").replace(" check_command slow\n", " check_command up\n")
        daemon.cfg.write_text(replacement)
        daemon.proc.send_signal(signal.SIGHUP)
        eventually(lambda: request(keep, "GET status\nColumns: configuration_reloads", keep=True) == [[1]])
        assert daemon.endpoint.stat().st_ino == inode, "reload rebound socket"
        assert request(keep, "GET status\nColumns: nagios_pid", keep=True) == [[pid]]
        assert daemon.host("removed") == []
        assert daemon.host("added") == [[0, 0]]
        assert daemon.svc("saved", "state acknowledged scheduled_downtime_depth") == [[2, 1, 1]]
        assert daemon.query("GET comments\nColumns: comment\nFilter: comment = survives reload") == [["survives reload"]]
        eventually(lambda: daemon.svc("inflight", "state plugin_output") == [[0, "NEW"]])
        time.sleep(2.2)
        assert not leaked.exists(), "obsolete check survived reload"

        daemon.cfg.write_text(replacement + obj("host", host_name="edge"))
        daemon.proc.send_signal(signal.SIGHUP)
        eventually(lambda: "configuration reload rejected:" in daemon.log.read_text())
        assert request(keep, "GET status\nColumns: configuration_reloads", keep=True) == [[1]]
        assert daemon.svc("saved", "plugin_output") == [["preserve me"]]
        daemon.cfg.write_text(replacement + obj("service", host_name="edge", service_description="new-passive"))
        daemon.command("RELOAD_CONFIG")
        eventually(lambda: request(keep, "GET status\nColumns: configuration_reloads", keep=True) == [[2]])
        assert daemon.svc("new-passive", "has_been_checked") == [[0]]
        daemon.query("GET log\nColumns: host_name plugin_output")
        assert daemon.svc("saved", "acknowledged") == [[1]]
    finally:
        keep.close()
        daemon.close()
    print("PASS: SIGHUP/command reload, persistent connections, state reconciliation, rejected config and obsolete process cancellation")

with tempfile.TemporaryDirectory(prefix="rust-native-") as temp:
    root = Path(temp)
    (root / "rules").mkdir()
    (root / "reload").mkdir()
    rule_scenarios(root / "rules")
    reload_scenarios(root / "reload")
