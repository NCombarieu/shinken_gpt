#!/usr/bin/env python3
"""End-to-end smoke test: run the six Shinken daemons natively and check
what a production replacement of Shinken master must do.

Checks (each reported PASS/FAIL, exit code 1 if any fails):

1. config     shinken-arbiter -v accepts the test configuration
2. daemons    the six daemons answer GET /ping on their port
3. checks     active checks run (plugin journal) and reach the scheduler
4. livestatus Livestatus answers GET hosts on its port (50000 by default)
5. notify     a CRITICAL HARD state sends an e-mail through the shipped
              notify-service-by-email command to a local SMTP sink
6. nagios.cmd an external command written to the named pipe is applied
7. retention  an acknowledgement and a downtime survive a scheduler restart

Usage (from a source checkout or with Shinken installed)::

    python3 integration/e2e_smoke.py                 # standard ports
    python3 integration/e2e_smoke.py --port-offset 10000 --keep

The test configuration lives in integration/e2e/ and follows the module
interfaces of the project (retention-pickle, logstore-sqlite, named-pipe).
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E2E = ROOT / "integration" / "e2e"
sys.path.insert(0, str(ROOT / "integration"))

from smtp_sink import SMTPSink  # noqa: E402

ROLES = ("scheduler", "poller", "reactionner", "broker", "receiver", "arbiter")
PORTS = {"scheduler": 7768, "reactionner": 7769, "arbiter": 7770, "poller": 7771,
         "broker": 7772, "receiver": 7773, "livestatus": 50000}


class Smoke:
    def __init__(self, args):
        self.args = args
        self.ports = {name: port + args.port_offset for name, port in PORTS.items()}
        too_high = {n: p for n, p in self.ports.items() if not 0 < p < 65536}
        if too_high:
            raise SystemExit("--port-offset %d gives invalid TCP ports: %s"
                             % (args.port_offset, too_high))
        self.work = Path(args.workdir or tempfile.mkdtemp(prefix="shinken-e2e-")).resolve()
        self.etc = self.work / "etc"
        self.procs: dict[str, subprocess.Popen] = {}
        self.results: list[tuple[str, bool, str]] = []
        self.sink = None

    # ------------------------------------------------------------------ setup
    def render(self):
        for sub in ("etc/commands", "etc/daemons", "run", "log", "var/archives", "out"):
            (self.work / sub).mkdir(parents=True, exist_ok=True)
        modules_dir = Path(self.args.modules_dir or ROOT / "modules").resolve()
        values = {
            "@WORK@": str(self.work),
            "@MODULES_DIR@": str(modules_dir),
            "@LIBEXEC@": str(ROOT / "libexec"),
            "@PLUGINS@": str(E2E / "plugins"),
            "@SMTP_PORT@": str(self.sink.port),
        }
        for name, port in self.ports.items():
            values["@PORT_%s@" % name.upper()] = str(port)

        def subst(text, extra=None):
            for key, value in {**values, **(extra or {})}.items():
                text = text.replace(key, value)
            return text

        for src in (E2E / "etc").glob("*.cfg"):
            (self.etc / src.name).write_text(subst(src.read_text(encoding="utf-8")),
                                             encoding="utf-8")
        template = (E2E / "etc" / "daemons" / "daemon.ini.in").read_text(encoding="utf-8")
        for role in ROLES[:-1]:
            (self.etc / "daemons" / ("%sd.ini" % role)).write_text(
                subst(template, {"@ROLE@": role, "@PORT@": str(self.ports[role])}),
                encoding="utf-8")
        # The shipped notification commands are tested as they are.
        for name in ("notify-host-by-email.cfg", "notify-service-by-email.cfg"):
            shutil.copy(ROOT / "etc" / "commands" / name, self.etc / "commands" / name)
        for state in ("host", "flip", "static", "passive"):
            self.state(state, 0)

    def state(self, name, value):
        (self.work / "var" / ("%s.state" % name)).write_text("%d\n" % value)

    def command(self, role):
        if self.args.installed:
            exe = [shutil.which("shinken-%s" % role) or "shinken-%s" % role]
        else:
            exe = [sys.executable, str(ROOT / "bin" / ("shinken-%s" % role))]
        if role == "arbiter":
            return exe + ["-c", str(self.etc / "shinken.cfg"), "-n", "arbiter-master"]
        return exe + ["-c", str(self.etc / "daemons" / ("%sd.ini" % role))]

    def env(self):
        env = dict(os.environ)
        if not self.args.installed:
            env["PYTHONPATH"] = os.pathsep.join(
                [str(ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        env.setdefault("TZ", "Europe/Paris")
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def start(self, role):
        out = open(self.work / "out" / ("%s.stdout" % role), "ab")  # noqa: SIM115
        self.procs[role] = subprocess.Popen(
            self.command(role), cwd=self.work, env=self.env(), stdout=out,
            stderr=subprocess.STDOUT, start_new_session=True)

    def stop(self, role, timeout=60):
        proc = self.procs.get(role)
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.log("%s did not stop within %ds, killing it" % (role, timeout))
        # Kill leftovers of the process group (workers, modules).
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(10)

    # ---------------------------------------------------------------- helpers
    def log(self, message):
        print("[e2e %s] %s" % (time.strftime("%H:%M:%S"), message), flush=True)

    def record(self, name, ok, detail):
        self.results.append((name, ok, detail))
        self.log("%s %s: %s" % ("PASS" if ok else "FAIL", name, detail))

    @staticmethod
    def wait_for(predicate, timeout, interval=1.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = predicate()
            except Exception as exp:  # noqa: BLE001 - keep polling
                last = None
                Smoke.last_error = exp
            if last:
                return last
            time.sleep(interval)
        return last

    def ping(self, role):
        url = "http://127.0.0.1:%d/ping" % self.ports[role]
        with urllib.request.urlopen(url, timeout=3) as resp:
            return b"pong" in resp.read()

    def livestatus(self, query):
        if not query.endswith("\n\n"):
            query = query.rstrip("\n") + "\n"
            if not query.startswith("COMMAND"):
                query += "OutputFormat: json\n"
            query += "\n"
        with socket.create_connection(("127.0.0.1", self.ports["livestatus"]), timeout=5) as sock:
            sock.sendall(query.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            data = b""
            while chunk := sock.recv(65536):
                data += chunk
        text = data.decode("utf-8", "replace").strip()
        if query.startswith("COMMAND"):
            return text
        return json.loads(text) if text else []

    def services(self):
        rows = self.livestatus("GET services\nColumns: description state state_type "
                               "has_been_checked acknowledged scheduled_downtime_depth "
                               "plugin_output\nFilter: host_name = e2e-host")
        return {row[0]: dict(zip(("state", "state_type", "checked", "ack", "downtime",
                                  "output"), row[1:])) for row in rows}

    def count_in_log(self, filename, text):
        path = self.work / "log" / filename
        if not path.exists():
            return 0
        return path.read_text(encoding="utf-8", errors="replace").count(text)

    def write_pipe(self, line):
        path = self.work / "var" / "nagios.cmd"
        if not path.exists() or not stat.S_ISFIFO(path.stat().st_mode):
            raise FileNotFoundError("%s is not a named pipe" % path)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exp:
            if exp.errno == errno.ENXIO:  # no reader yet
                return False
            raise
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return True

    # ----------------------------------------------------------------- checks
    def check_config(self):
        proc = subprocess.run(self.command("arbiter") + ["-v"], cwd=self.work, env=self.env(),
                              capture_output=True, text=True, timeout=120, check=False)
        (self.work / "out" / "arbiter-verify.txt").write_text(proc.stdout + proc.stderr)
        ok = proc.returncode == 0
        self.record("config", ok, "shinken-arbiter -v rc=%d" % proc.returncode)
        return ok

    def check_daemons(self):
        for role in ROLES:
            self.start(role)
        alive = {}
        for role in ROLES:
            alive[role] = bool(self.wait_for(lambda r=role: self.ping(r), 60))
        dead = [role for role, ok in alive.items() if not ok]
        self.record("daemons", not dead, "all six answer /ping" if not dead
                    else "no answer from %s" % ", ".join(dead))

    def check_checks(self):
        journal = self.work / "out" / "checks.log"

        def ran():
            text = journal.read_text() if journal.exists() else ""
            return all(" %s " % name in text for name in ("host", "flip", "static"))
        ok = bool(self.wait_for(ran, self.args.timeout))
        self.record("checks", ok, "plugins executed by the poller (%s)" % journal.name
                    if ok else "no plugin execution recorded in %s" % journal)

    def check_livestatus(self):
        def hosts():
            return self.livestatus("GET hosts\nColumns: name state")
        rows = self.wait_for(hosts, self.args.timeout, 2)
        ok = bool(rows) and any(row[0] == "e2e-host" for row in rows)
        self.record("livestatus", ok, "GET hosts -> %s" % rows if ok else
                    "no answer on port %d (%s)" % (self.ports["livestatus"],
                                                   getattr(Smoke, "last_error", "")))
        return ok

    def check_notification(self):
        self.state("flip", 2)

        def mailed():
            return [m for m in self.sink.messages
                    if b"CRITICAL" in m[2] and b"Flip" in m[2]]
        mails = self.wait_for(mailed, self.args.timeout)
        ok = bool(mails)
        detail = ("mail to %s via notify-service-by-email" % mails[0][1] if ok else
                  "no mail received by the SMTP sink (see log/reactionnerd.log)")
        self.record("notify", ok, detail)

    def check_named_pipe(self, livestatus_ok):
        now = int(time.time())
        line = ("[%d] PROCESS_SERVICE_CHECK_RESULT;e2e-host;Passive;1;"
                "WARNING - via nagios.cmd" % now)
        written = self.wait_for(lambda: self.write_pipe(line), 30)
        if not written:
            self.record("nagios.cmd", False, "%s missing or without reader"
                        % (self.work / "var" / "nagios.cmd"))
            return
        if livestatus_ok:
            def applied():
                svc = self.services().get("Passive")
                return svc and svc["state"] == 1 and "nagios.cmd" in svc["output"]
            ok = bool(self.wait_for(applied, 60, 2))
        else:
            ok = bool(self.wait_for(
                lambda: self.count_in_log("schedulerd.log", "via nagios.cmd")
                or "via nagios.cmd" in (self.work / "out" / "scheduler.stdout").read_text(
                    errors="replace"), 60))
        self.record("nagios.cmd", ok, "PROCESS_SERVICE_CHECK_RESULT applied" if ok else
                    "command written but not applied to e2e-host/Passive")

    def check_retention(self, livestatus_ok):
        if not livestatus_ok:
            self.record("retention", False, "skipped: needs Livestatus to read ACK/downtimes")
            return
        now = int(time.time())
        commands = [
            "ACKNOWLEDGE_SVC_PROBLEM;e2e-host;Flip;2;1;1;e2e;ack before restart",
            "SCHEDULE_SVC_DOWNTIME;e2e-host;Static;%d;%d;1;0;3600;e2e;downtime before restart"
            % (now, now + 3600),
        ]
        for cmd in commands:
            self.livestatus("COMMAND [%d] %s\n\n" % (now, cmd))

        def applied():
            svc = self.services()
            return svc["Flip"]["ack"] == 1 and svc["Static"]["downtime"] > 0
        if not self.wait_for(applied, 60, 2):
            self.record("retention", False, "ACK/downtime not applied before restart")
            return
        dispatched = self.count_in_log("arbiterd.log", "Dispatch OK of conf in scheduler")
        self.log("restarting the scheduler")
        self.stop("scheduler")
        retention = self.work / "var" / "retention.dat"
        saved = retention.exists() and retention.stat().st_size > 0
        self.start("scheduler")
        redispatched = self.wait_for(
            lambda: self.count_in_log("arbiterd.log", "Dispatch OK of conf in scheduler")
            > dispatched, 120)
        if not redispatched:
            self.record("retention", False, "scheduler did not get its configuration back")
            return
        # Let the broker rebuild its state from the new initial broks.
        time.sleep(15)
        kept = self.wait_for(applied, 30, 2)
        svc = self.services()
        self.record("retention", bool(kept) and saved,
                    "retention.dat %s; after restart ack=%s downtime=%s"
                    % ("written" if saved else "MISSING", svc["Flip"]["ack"],
                       svc["Static"]["downtime"]))

    # ------------------------------------------------------------------- main
    def run(self):
        self.log("workdir %s" % self.work)
        with SMTPSink(self.work / "out" / "mails") as sink:
            self.sink = sink
            self.render()
            try:
                if not self.check_config():
                    return self.report()
                self.check_daemons()
                self.check_checks()
                livestatus_ok = self.check_livestatus()
                self.check_notification()
                self.check_named_pipe(livestatus_ok)
                self.check_retention(livestatus_ok)
            finally:
                for role in reversed(ROLES):
                    self.stop(role, 40)
        return self.report()

    def report(self):
        failed = [name for name, ok, _ in self.results if not ok]
        print("\n== Shinken e2e smoke test ==")
        for name, ok, detail in self.results:
            print("  %-11s %s  %s" % (name, "PASS" if ok else "FAIL", detail))
        if failed:
            print("\nLogs: %s/log and %s/out" % (self.work, self.work))
            for path in sorted((self.work / "log").glob("*.log")):
                lines = path.read_text(errors="replace").splitlines()
                errors = [ln for ln in lines if "ERROR" in ln or "Traceback" in ln]
                if errors:
                    print("\n--- %s (errors, last 15) ---" % path.name)
                    print("\n".join(errors[-15:]))
        elif not self.args.keep and not self.args.workdir:
            shutil.rmtree(self.work, ignore_errors=True)
        return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port-offset", type=int, default=0,
                        help="Add this offset to every port (default 0: 7768-7773, 50000)")
    parser.add_argument("--workdir", help="Directory for configuration, logs and state "
                                          "(default: new temporary directory)")
    parser.add_argument("--modules-dir", help="Shinken modules directory (default: modules/)")
    parser.add_argument("--installed", action="store_true",
                        help="Run the shinken-* commands from PATH instead of bin/")
    parser.add_argument("--timeout", type=int, default=90,
                        help="Timeout of each wait, in seconds (default 90)")
    parser.add_argument("--keep", action="store_true", help="Keep the workdir on success")
    return Smoke(parser.parse_args(argv)).run()


if __name__ == "__main__":
    sys.exit(main())
