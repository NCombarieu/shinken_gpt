#!/usr/bin/env python3
"""Exercise native notification commands using local files only."""
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from smoke import object_cfg, eventually, request, response

binary = str(Path(sys.argv[1]).resolve())
with tempfile.TemporaryDirectory(prefix="rust-notify-") as temp:
    root = Path(temp)
    main = root / "main.cfg"
    cfg = root / "objects.cfg"
    alerts = root / "alerts"
    marker = root / "injected"
    endpoint = root / "live.sock"
    retained = root / "state.json"
    main.write_text("cfg_file=objects.cfg\ninterval_length=1\nuse_timezone=UTC\nnotification_timeout=0.5\n")
    objects = object_cfg("command", command_name="record",
        command_line=r"/usr/bin/printf '%s\n' '$NOTIFICATIONTYPE$|$HOSTNAME$|$SERVICEDESC$|$SERVICESTATE$|$CONTACTNAME$|$SERVICEOUTPUT$' >> $ARG1$")
    objects += object_cfg("command", command_name="up", command_line="printf UP")
    objects += object_cfg("timeperiod", timeperiod_name="none", alias="Never")
    objects += object_cfg("contact", contact_name="operator", notificationways="local")
    objects += object_cfg("notificationway", notificationway_name="local",
        service_notification_commands=f"record!{alerts}", service_notification_options="c,w,r",
        service_notification_period="24x7")
    objects += object_cfg("host", host_name="edge", contacts="operator", notifications_enabled="0")
    objects += object_cfg("host", host_name="closed-host", check_command="up", check_period="none", notifications_enabled="0")
    objects += object_cfg("service", host_name="edge", service_description="passive",
        active_checks_enabled="0", notifications_enabled="1", notification_interval="0",
        notification_options="c,w,r", notification_period="24x7")
    objects += object_cfg("service", host_name="edge", service_description="closed",
        active_checks_enabled="0", notifications_enabled="1", notification_interval="0",
        notification_period="none")
    objects += object_cfg("service", host_name="edge", service_description="repeat",
        active_checks_enabled="0", notifications_enabled="1", notification_interval="0.5")
    cfg.write_text(objects)
    log = root / "daemon.log"
    def start():
        out = log.open("a")
        proc = subprocess.Popen([binary, "run", str(main), "--livestatus-unix", str(endpoint),
                                 "--state-file", str(retained)], stdout=out, stderr=out)
        out.close()
        def ready():
            assert proc.poll() is None, log.read_text()
            return endpoint.exists()
        eventually(ready)
        return proc
    def connect():
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(5)
        sock.connect(str(endpoint))
        return sock
    def query(text):
        with connect() as sock:
            return request(sock, text)
    def command(text):
        with connect() as sock:
            sock.sendall((f"COMMAND [{int(time.time())}] " + text + "\nResponseHeader: fixed16\n\n").encode())
            status, body = response(sock)
            assert status == 200, (text, status, body)
    def lines():
        return alerts.read_text().splitlines() if alerts.exists() else []
    def wait_lines(count):
        eventually(lambda: len(lines()) >= count)
        assert len(lines()) == count, lines()
    proc = start()
    try:
        assert query("GET status\nColumns: enable_notifications") == [[1]]
        assert query("GET hosts\nColumns: has_been_checked in_check_period\nFilter: name = closed-host") == [[0, 0]]
        command(f"SCHEDULE_FORCED_HOST_CHECK;closed-host;{int(time.time())}")
        eventually(lambda: query("GET hosts\nColumns: has_been_checked\nFilter: name = closed-host") == [[1]])
        literal = f'CRITICAL $(touch {marker}); "quotes" and ' + chr(96) + 'literal' + chr(96)
        command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;2;" + literal)
        wait_lines(1)
        assert lines()[0] == "PROBLEM|edge|passive|CRITICAL|operator|" + literal, lines()
        assert not marker.exists(), "plugin output became shell code"
        eventually(lambda: query("GET services\nColumns: current_notification_number\nFilter: description = passive") == [[1]])
        command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;2;still critical")
        time.sleep(1.2)
        assert len(lines()) == 1, "notification_interval=0 must not repeat"
        command("ACKNOWLEDGE_SVC_PROBLEM;edge;passive;2;0;1;operator;investigating")
        command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;1;warning acknowledged")
        time.sleep(1.2)
        assert len(lines()) == 1, "sticky acknowledgement did not suppress notification"
        command("REMOVE_SVC_ACKNOWLEDGEMENT;edge;passive")
        wait_lines(2)
        assert "|WARNING|" in lines()[1]
        command("PROCESS_SERVICE_CHECK_RESULT;edge;closed;2;closed period")
        time.sleep(0.4)
        assert len(lines()) == 2, "closed notification period was ignored"
    finally:
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=10) == 0, log.read_text()
    proc = start()
    try:
        time.sleep(1.2)
        assert len(lines()) == 2, "retention lost successful notification history"
        command("DISABLE_NOTIFICATIONS")
        command("PROCESS_SERVICE_CHECK_RESULT;edge;passive;0;recovered")
        time.sleep(0.4)
        assert len(lines()) == 2
        command("ENABLE_NOTIFICATIONS")
        wait_lines(3)
        assert lines()[2] == "RECOVERY|edge|passive|OK|operator|recovered"
        assert not marker.exists()
        command("PROCESS_SERVICE_CHECK_RESULT;edge;repeat;2;repeat problem")
        eventually(lambda: len([line for line in lines() if "|repeat|" in line]) >= 2)
        now = int(time.time())
        command(f"SCHEDULE_SVC_DOWNTIME;edge;repeat;{now-1};{now+600};1;0;601;operator;quiet")
        time.sleep(0.3)
        before = len(lines())
        time.sleep(1.3)
        assert len(lines()) == before, "downtime did not suppress repeated notifications"
    finally:
        proc.terminate()
        assert proc.wait(timeout=10) == 0, log.read_text()
    print("PASS: native notifications, suppression, recovery, retention, safe macros and periods")
