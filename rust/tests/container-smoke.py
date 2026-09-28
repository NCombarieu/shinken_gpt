"""Verify the daemon through the port published by rootless Podman."""
import socket
import sys
from smoke import eventually, request

port = int(sys.argv[1])

def healthy():
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            rows = request(sock, "GET services\nColumns: state has_been_checked\nFilter: description = Native check")
            return rows == [[0, 1]]
    except (OSError, AssertionError):
        return False

eventually(healthy)
with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
    assert request(sock, "GET status\nColumns: num_hosts num_services enable_notifications") == [[1, 3, 0]]
print("PASS: rootless container daemon and published Livestatus port")
