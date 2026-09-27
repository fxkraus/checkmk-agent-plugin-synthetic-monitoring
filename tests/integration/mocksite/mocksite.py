"""Self-contained mock website for the live integration test. Standard library only."""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

_HOME = b"""<!doctype html><html><head><title>synmon mock</title></head><body>
<div id="synmon-hero" style="width:100%;height:400px;background:#0a3">Hero</div>
<p>Mock content for FCP/TTFB.</p>
<button id="synmon-inp-btn">Click</button>
<div id="synmon-shift" style="height:10px">shifts</div>
<script>
document.getElementById('synmon-inp-btn').addEventListener('click', () => {
  const t = Date.now() + 60; while (Date.now() < t) {}  // block to register INP
  document.body.appendChild(document.createTextNode('clicked'));
});
setTimeout(() => { document.getElementById('synmon-shift').style.height = '200px'; }, 100);
</script></body></html>"""

_LOGIN = b"""<!doctype html><html><body><form method="POST" action="/login">
<input name="user"><input name="pass" type="password">
<button id="synmon-login-btn" type="submit">Sign in</button></form></body></html>"""

_PROTECTED = b"""<!doctype html><html><body><h1>Protected area</h1>
<div id="synmon-hero" style="width:100%;height:300px;background:#06c">Secret</div></body></html>"""


def handle(method, path, cookies, state):
    path = path.split("?", 1)[0]
    if path == "/healthz":
        return 200, {"Content-Type": "text/plain"}, b"ok"
    if path == "/":
        return 200, {"Content-Type": "text/html"}, _HOME
    if path == "/login" and method == "GET":
        return 200, {"Content-Type": "text/html"}, _LOGIN
    if path == "/login" and method == "POST":
        return 302, {"Location": "/protected", "Set-Cookie": "sid=ok; Path=/"}, b""
    if path == "/protected":
        if cookies.get("sid"):
            return 200, {"Content-Type": "text/html"}, _PROTECTED
        return 302, {"Location": "/login"}, b""
    if path == "/flaky":
        state["flaky_hits"] = state.get("flaky_hits", 0) + 1
        if state["flaky_hits"] <= 1:
            return 500, {"Content-Type": "text/plain"}, b"flaky"
        return 200, {"Content-Type": "text/html"}, _HOME
    return 404, {"Content-Type": "text/plain"}, b"not found"


def _parse_cookies(raw):
    out = {}
    for part in (raw or "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


def serve(port):
    state = {"flaky_hits": 0}

    class _H(BaseHTTPRequestHandler):
        def _do(self, method):
            status, headers, body = handle(
                method, self.path, _parse_cookies(self.headers.get("Cookie")), state
            )
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            self._do("GET")

        def do_POST(self):
            self._do("POST")

        def log_message(self, *_args):
            pass

    HTTPServer(("0.0.0.0", port), _H).serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8080)
