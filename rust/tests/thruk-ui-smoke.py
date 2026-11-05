#!/usr/bin/env python3
"""Real Thruk HTTP rendering and an authenticated, CSRF-protected UI command."""
import base64
from html.parser import HTMLParser
import http.cookiejar
from pathlib import Path
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from smoke import eventually, request

port, engine_port = map(int, sys.argv[1:3])
results = Path(sys.argv[3])
base = f"http://127.0.0.1:{port}/demo/thruk/cgi-bin/"
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
authorization = "Basic " + base64.b64encode(b"omdadmin:rust-ui-ci").decode()

def page(path, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(base + path, body, {
        "Authorization": authorization, "Referer": base + "status.cgi",
        "User-Agent": "Python-Thruk-native-integration",
    })
    with opener.open(req, timeout=15) as response:
        text = response.read().decode("utf-8", "replace")
        assert response.status == 200, response.status
        return text

def query(text):
    with socket.create_connection(("127.0.0.1", engine_port), timeout=5) as sock:
        return request(sock, text)

last_error = ""
def ready():
    global last_error
    try:
        text = page("tac.cgi")
        (results / "tactical.html").write_text(text)
        if "Tactical" in text and "Native Rust" in text:
            return True
        last_error = text[-1000:]
    except (OSError, urllib.error.URLError, AssertionError) as error:
        last_error = str(error)
    return False

try:
    eventually(ready, timeout=180)
except AssertionError as error:
    raise AssertionError("Thruk did not become ready: " + last_error) from error

pages = [
    ("hosts.html", "status.cgi?style=hostdetail", ["localhost", "UP"]),
    ("services.html", "status.cgi?style=detail", ["Native check", "Example alert", "Passive input"]),
    ("service.html", "extinfo.cgi?type=2&host=localhost&service=Example+alert", ["Example alert", "CRITICAL"]),
    ("process.html", "extinfo.cgi?type=0", ["shinken-rs"]),
]
for name, url, expected in pages:
    html = page(url)
    (results / name).write_text(html)
    for value in expected:
        assert value in html, (name, value, html[-2000:])
    assert "Error 500" not in html and "internal server error" not in html.lower(), name

class Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name"):
            if attrs.get("type") in ("checkbox", "radio") and "checked" not in attrs:
                return
            self.fields[attrs["name"]] = attrs.get("value", "")

html = page("cmd.cgi?cmd_typ=1&host=localhost")
(results / "comment-form.html").write_text(html)
form = Form()
form.feed(html)
assert form.fields.get("CSRFtoken"), "actual command form must provide CSRF protection"
form.fields.update(cmd_mod="2", cmd_typ="1", host="localhost", com_author="omdadmin",
                   com_data="native-thruk-ui-comment", persistent="1", btnSubmit="Commit")
submitted = page("cmd.cgi", form.fields)
(results / "command-result.html").write_text(submitted)
eventually(lambda: query("GET comments\nColumns: author comment\nFilter: comment = native-thruk-ui-comment") ==
           [["omdadmin", "native-thruk-ui-comment"]])
assert query("GET status\nColumns: num_hosts num_services") == [[1, 3]]
print("PASS: actual Thruk tactical/host/service/process pages and authenticated comment form against Rust")
