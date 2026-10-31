#!/usr/bin/env python3
"""Minimal SMTP sink used by the notification tests and the e2e smoke test.

It speaks just enough SMTP (EHLO/HELO, optional AUTH PLAIN, MAIL, RCPT, DATA,
RSET, NOOP, QUIT) for ``smtplib`` clients and stores every accepted message as
an ``.eml`` file. It has no dependency outside the standard library on
purpose: ``smtpd`` was removed in Python 3.12 and ``aiosmtpd`` is not always
available in CI or on a production host.

Usage as a script::

    python3 integration/smtp_sink.py --port 2525 --outdir /tmp/mails

Usage from Python::

    with SMTPSink(outdir) as sink:
        ...  # send mail to ("127.0.0.1", sink.port)
        sink.messages  # list of (mail_from, rcpt_tos, raw_bytes)
"""

from __future__ import annotations

import argparse
import base64
import os
import socketserver
import threading
import time
from pathlib import Path


class _Handler(socketserver.StreamRequestHandler):
    timeout = 30

    def _reply(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("ascii"))
        self.wfile.flush()

    def handle(self) -> None:  # noqa: C901 - small protocol state machine
        sink: SMTPSink = self.server.sink  # type: ignore[attr-defined]
        self._reply("220 smtp-sink ESMTP ready")
        mail_from = None
        rcpts: list[str] = []
        authenticated = sink.credentials is None
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            verb = line.split(" ", 1)[0].upper()
            arg = line[len(verb):].strip()
            if verb in ("EHLO", "HELO"):
                if verb == "EHLO":
                    self.wfile.write(b"250-smtp-sink\r\n")
                    if sink.credentials is not None:
                        self.wfile.write(b"250-AUTH PLAIN\r\n")
                    self._reply("250 8BITMIME")
                else:
                    self._reply("250 smtp-sink")
            elif verb == "AUTH":
                parts = arg.split()
                if not parts or parts[0].upper() != "PLAIN":
                    self._reply("504 unsupported mechanism")
                    continue
                if len(parts) > 1:
                    token = parts[1]
                else:
                    self._reply("334 ")
                    token = self.rfile.readline().decode("ascii", "replace").strip()
                try:
                    _, user, password = base64.b64decode(token).decode("utf-8").split("\0")
                except (ValueError, UnicodeDecodeError):
                    self._reply("501 malformed")
                    continue
                if sink.credentials == (user, password):
                    authenticated = True
                    self._reply("235 authenticated")
                else:
                    self._reply("535 authentication failed")
            elif verb == "MAIL":
                if not authenticated:
                    self._reply("530 authentication required")
                    continue
                mail_from = arg.split(":", 1)[-1].strip().strip("<>").split(">")[0]
                rcpts = []
                self._reply("250 ok")
            elif verb == "RCPT":
                if mail_from is None:
                    self._reply("503 need MAIL first")
                    continue
                rcpts.append(arg.split(":", 1)[-1].strip().split(">")[0].strip("<"))
                self._reply("250 ok")
            elif verb == "DATA":
                if not rcpts:
                    self._reply("503 need RCPT first")
                    continue
                self._reply("354 end with <CRLF>.<CRLF>")
                lines = []
                while True:
                    data = self.rfile.readline()
                    if not data or data in (b".\r\n", b".\n"):
                        break
                    if data.startswith(b".."):
                        data = data[1:]
                    lines.append(data)
                sink.store(mail_from or "", rcpts, b"".join(lines))
                mail_from, rcpts = None, []
                self._reply("250 queued")
            elif verb == "RSET":
                mail_from, rcpts = None, []
                self._reply("250 ok")
            elif verb == "NOOP":
                self._reply("250 ok")
            elif verb == "QUIT":
                self._reply("221 bye")
                return
            else:
                self._reply("502 command not implemented")


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SMTPSink:
    """Threaded SMTP sink storing messages in memory and in ``outdir``."""

    def __init__(self, outdir=None, host="127.0.0.1", port=0, credentials=None):
        self.outdir = Path(outdir) if outdir else None
        self.credentials = credentials
        self.messages: list[tuple[str, list[str], bytes]] = []
        self._lock = threading.Lock()
        self._server = _Server((host, port), _Handler)
        self._server.sink = self  # type: ignore[attr-defined]
        self.host, self.port = self._server.server_address[:2]
        self._thread = None

    def store(self, mail_from, rcpts, data):
        with self._lock:
            self.messages.append((mail_from, list(rcpts), data))
            index = len(self.messages)
        if self.outdir:
            self.outdir.mkdir(parents=True, exist_ok=True)
            name = "%d-%04d.eml" % (int(time.time()), index)
            tmp = self.outdir / ("." + name)
            tmp.write_bytes(data)
            os.replace(tmp, self.outdir / name)

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal SMTP sink for tests")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2525)
    parser.add_argument("--outdir", required=True, help="Directory receiving .eml files")
    args = parser.parse_args()
    sink = SMTPSink(args.outdir, args.host, args.port)
    print("smtp-sink listening on %s:%d, writing to %s" % (sink.host, sink.port, args.outdir),
          flush=True)
    try:
        sink._server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        sink._server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
