"""PoCs: authentication, transport and browser-reachable attack surface (03 section 5, 02 section 6)."""
from __future__ import annotations

import http.client
import json
import os
import socket
import time
from urllib.parse import urlparse

from _common import *  # noqa: F403
from _common import PathScope, Policy, Principal, Server, mktree, secure
import ebxp.api as api


def is_a1_unresolvable_token_env_degrades_to_open_admin():
    """IS-A1: auth.tokens configured, but the referenced env var is unset/empty -> must refuse to start, not go anonymous+admin."""
    os.environ.pop("EBX_ISEC_UNSET_TOKEN", None)
    cfg = {"preset": "minimal",
           "auth": {"tokens": [{"id": "grader", "roles": ["grader"], "token_env": "EBX_ISEC_UNSET_TOKEN"}]}}
    try:
        srv = api.from_config(cfg)
    except Exception:
        return                                           # fail-closed: refusing to start is the correct outcome
    principal = srv.authenticate({})                     # a request with NO credentials
    secure(principal is None, f"unauthenticated request resolved to {principal}: a missing secret turned the server into open mode")


def _open_server():
    root = mktree()
    (root / "a.txt").write_text("hello")
    srv = api.SandboxServer(Policy().allow("files.stat", paths=PathScope(str(root))))    # no tokens: open mode
    httpd = api.start_http(srv)
    return httpd, root


def is_a2_browser_csrf_and_dns_rebinding_are_not_blocked():
    """IS-A2: any web page can POST text/plain JSON (no preflight) to an open-mode server; Host/Origin are never checked."""
    httpd, root = _open_server()
    try:
        port = httpd.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/ops/files.stat", body=json.dumps({"path": str(root / "a.txt")}),
                     headers={"Content-Type": "text/plain", "Host": "rebind.evil.example:9000", "Origin": "https://evil.example"})
        resp = conn.getresponse()
        resp.read()
        secure(resp.status in (400, 403, 415), f"cross-origin text/plain POST with a foreign Host was executed (HTTP {resp.status})")
    finally:
        httpd.shutdown()


def is_a3_idle_connections_are_never_timed_out():
    """IS-A3: auth runs after header parsing; a socket that never finishes its request line holds a thread forever."""
    httpd, _ = _open_server()
    try:
        port = httpd.server_address[1]
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.sendall(b"GET /ops HTTP/1.1\r\nHost: x\r\n")      # never terminates the header block
        deadline = time.time() + 6
        closed = False
        while time.time() < deadline:
            try:
                if s.recv(1) == b"":
                    closed = True
                    break
            except socket.timeout:
                continue
            except OSError:
                closed = True
                break
        s.close()
        secure(closed, "server kept an unauthenticated half-open request for >6 s (no header/body read timeout; "
                       "with max_connections=64 this is a one-socket-per-slot total outage)")
    finally:
        httpd.shutdown()


def is_a8_double_slash_target_is_routed_by_the_path_after_the_authority():
    """IS-A8: v1 does `urlparse(self.path).path`; `//anything/shell` was routed as `/shell` (proxy-ACL confusion).

    Rewired to the spike's real transport: a raw request with each ambiguous target must be rejected (400)."""
    httpd, _ = _open_server()
    try:
        port = httpd.server_address[1]
        for target in ("//x/ops", "///ops", "/ops/./", "/ops/../ops", "/%2e%2e/ops", "/ops%2f", "/a%00b"):
            s = socket.create_connection(("127.0.0.1", port), timeout=3)
            s.sendall(f"GET {target} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
            status = s.recv(64).split(b" ")[1]
            s.close()
            secure(status == b"400", f"request-target {target!r} was dispatched (HTTP {status.decode()}) instead of 400 request.bad_target")
    finally:
        httpd.shutdown()


CHECKS = [
    ("IS-A1", is_a1_unresolvable_token_env_degrades_to_open_admin),
    ("IS-A2", is_a2_browser_csrf_and_dns_rebinding_are_not_blocked),
    ("IS-A3", is_a3_idle_connections_are_never_timed_out),
    ("IS-A8", is_a8_double_slash_target_is_routed_by_the_path_after_the_authority),
]
