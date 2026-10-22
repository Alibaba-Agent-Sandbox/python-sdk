"""Helpers: start a real :class:`SandboxServer` on a free port inside a thread."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from typing import Any

from agent_sandbox.server.app import SandboxServer
from agent_sandbox.server.endpoints import CapabilityGroup
from agent_sandbox.server.policy import ServerPolicy
from agent_sandbox.server.registry import CommandRegistry
from agent_sandbox.server.router import default_table
from agent_sandbox.server.runtime import PolicyEngine


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def wire(
    httpd: Any,
    *,
    auth_token: str | None = None,
    registry: CommandRegistry | None = None,
    policy: dict[str, Any] | None = None,
) -> Any:
    """Attach what :meth:`SandboxServer.serve` attaches to a bare ``ThreadingHTTPServer``."""
    httpd.auth_token = auth_token
    httpd.registry = registry
    httpd.route_table = default_table()
    document = dict(policy or {})
    if auth_token:
        import hashlib

        document["auth"] = {
            **document.get("auth", {}),
            "tokens": [
                {
                    "id": "server",
                    "scopes": ["*"],
                    "token_sha256": hashlib.sha256(auth_token.encode()).hexdigest(),
                },
            ],
        }
    httpd.policy_engine = PolicyEngine(
        ServerPolicy.from_dict(document),
        default_table(),
        registry=registry,
    )
    return httpd


class Live:
    """A running server plus a tiny HTTP client."""

    def __init__(self, **kwargs: Any) -> None:
        self._closed = False
        self.port = free_port()
        self.registry: CommandRegistry = kwargs.pop("registry", None) or CommandRegistry()
        kwargs.setdefault("pty_port", free_port())
        self.pty_port: int = kwargs["pty_port"]
        self.server = SandboxServer(host="127.0.0.1", registry=self.registry, **kwargs)
        self.thread = threading.Thread(target=self.server.serve, args=(self.port,), daemon=True)
        self.thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            # A successful TCP connect alone can precede app initialization.
            # Wait for this instance to install its policy and start its PTY
            # thread before exposing it to assertions or teardown.
            httpd = self.server._httpd
            pty = self.server._pty_thread
            if (
                httpd is None
                or not hasattr(httpd, "policy_engine")
                or (
                    self.server.policy_engine.group_enabled(CapabilityGroup.TERMINAL)
                    and (pty is None or pty.ident is None)
                )
            ):
                time.sleep(0.02)
                continue
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.02)
        else:
            raise RuntimeError("Test server did not become ready within five seconds")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.server.shutdown()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        hdrs = dict(headers or {})
        data = raw_body
        if body is not None:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        out_headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        try:
            parsed: Any = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = payload
        return resp.status, parsed, out_headers

    def get(self, path: str, **kw: Any) -> tuple[int, Any]:
        status, body, _ = self.request("GET", path, **kw)
        return status, body

    def post(self, path: str, body: Any = None, **kw: Any) -> tuple[int, Any]:
        status, resp, _ = self.request("POST", path, body if body is not None else {}, **kw)
        return status, resp
