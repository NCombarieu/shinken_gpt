#!/usr/bin/env python3
"""Check the per-protocol services of the integration lab in /api/status.

Reads the broker status JSON on stdin, prints one line per expectation and
exits non-zero while any expectation is not met (the lab polls it).
"""

from __future__ import annotations

import json
import sys

# (service key, expected state_id, text expected in the output, what it proves)
EXPECTATIONS = [
    ("integration-sshtarget/Load via SSH", 0, "LOAD",
     "active SSH check: poller key setup, known_hosts, forced command"),
    ("integration-sshtarget/Forbidden via SSH", 3, "is not allowed",
     "a check name outside the target's list is refused"),
    ("integration-passive/Backup", 1, "lab passive result",
     "passive result pushed over SSH -> passive-ssh -> Livestatus -> scheduler"),
    ("integration-http/API health", 0, "status = UP",
     "check_json_api plugin shipped in the image"),
]


def main() -> int:
    try:
        services = json.load(sys.stdin).get("services", {})
    except ValueError:
        services = {}
    failed = 0
    for key, state, text, meaning in EXPECTATIONS:
        service = services.get(key)
        if service is None:
            ok, seen = False, "service not in status"
        else:
            output = service.get("output", "")
            ok = service.get("state_id") == state and text in output
            seen = f"state_id={service.get('state_id')} output={output[:120]!r}"
        failed += not ok
        print(f"{'OK  ' if ok else 'WAIT'} {key}: {meaning} [{seen}]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
