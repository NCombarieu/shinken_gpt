import base64
import socket
import threading
import time
from types import SimpleNamespace

import bottle

from shinken.http_client import HTTPClient
from shinken.http_daemon import HTTPDaemon
from shinken.scheduler import Scheduler


def _unused_local_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_python3_http_transport_handles_json_raw_and_pickled_post_data():
    bottle.default_app().routes[:] = []
    port = _unused_local_port()

    class API:
        received = None

        def ping(self):
            return True

        def receive(self, value):
            self.received = value
            return True

        receive.method = "post"

        def raw(self):
            return base64.b64encode(b"raw-payload")

        raw.encode = "raw"

        def binary(self):
            return b"unannotated-binary"

    api = API()
    daemon = HTTPDaemon(
        "127.0.0.1", port, "cheroot", False, "", "", "", False, 2
    )
    daemon.register(api)
    server_thread = threading.Thread(target=daemon.run, daemon=True)
    server_thread.start()
    client = HTTPClient("127.0.0.1", port, timeout=2)

    try:
        for _ in range(50):
            try:
                assert client.get("ping") is True
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise AssertionError("HTTP daemon did not start")

        value = {"text": "hé", "blob": b"\x00\xff"}
        args = {"value": value}
        assert client.post("receive", args) == "true"
        assert args == {"value": value}
        assert api.received == value
        assert base64.b64decode(client.get("raw")) == b"raw-payload"
        assert client.get("binary") == b"unannotated-binary"
    finally:
        daemon.shutdown()
        server_thread.join(2)
        bottle.default_app().routes[:] = []


def test_scheduler_brok_batch_zero_means_all_and_positive_is_a_limit():
    scheduler = SimpleNamespace(
        broks=["global-1", "global-2"],
        brokers={"broker": {"broks": ["private-1", "private-2"]}},
    )

    assert Scheduler.get_broks(scheduler, "broker", 3) == [
        "global-1",
        "global-2",
        "private-1",
    ]
    assert scheduler.broks == []
    assert scheduler.brokers["broker"]["broks"] == ["private-2"]
    assert Scheduler.get_broks(scheduler, "broker", 0) == ["private-2"]
