#!/usr/bin/env python3
"""Deterministic integration checks used by the Podman lab.

The script intentionally uses only Python's standard library so the integration
suite validates Shinken itself instead of an unrelated monitoring plugin
package. Checks append markers to the shared Shinken data volume so the outer
lab can prove that scheduler/poller execution actually happened.
"""

from __future__ import annotations

import socket
import sys
import urllib.request
from pathlib import Path


def record(marker_file: str, marker: str) -> None:
    path = Path(marker_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{marker}\n")


def check_host(host: str, marker_file: str) -> int:
    try:
        address = socket.gethostbyname(host)
    except OSError as exc:
        print(f"CRITICAL - cannot resolve {host}: {exc}")
        return 2
    record(marker_file, f"host-ok {host} {address}")
    print(f"OK - {host} resolves to {address}")
    return 0


def check_http(host: str, marker_file: str) -> int:
    url = f"http://{host}:8000/"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.status
            body = response.read(256)
    except Exception as exc:
        print(f"CRITICAL - {url}: {exc}")
        return 2
    if status != 200:
        print(f"CRITICAL - {url} returned HTTP {status}")
        return 2
    record(marker_file, f"http-ok {host} {status}")
    print(f"OK - {url} returned HTTP {status} ({len(body)} bytes sampled)")
    return 0


def check_expected_failure(host: str, marker_file: str) -> int:
    record(marker_file, f"critical-seen {host}")
    print(f"CRITICAL - intentional integration failure for {host}")
    return 2


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in {"host", "http", "fail"}:
        print(
            f"usage: {sys.argv[0]} <host|http|fail> <hostname> <marker-file>",
            file=sys.stderr,
        )
        return 3
    mode, host, marker_file = sys.argv[1:]
    if mode == "host":
        return check_host(host, marker_file)
    if mode == "http":
        return check_http(host, marker_file)
    return check_expected_failure(host, marker_file)


if __name__ == "__main__":
    raise SystemExit(main())
