"""Base-image contract constants shared by the server, the client SDK and tooling.

These are the conventions a template layered on the Alibaba Cloud Agent Sandbox base
image can rely on (see ``docs/en/design/base-image-and-server-sdk.md``).  The module
is pure data and importable without side effects.
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_HOME",
    "DEFAULT_HTTP_PORT",
    "DEFAULT_PTY_PORT",
    "DEFAULT_USER",
    "ENVD_PORT",
    "GATEWAY_PORT",
    "CODE_INTERPRETER_PORT",
    "POLICY_FILE",
    "READY_COMMAND",
    "RESERVED_PORTS",
    "START_COMMAND",
]

DEFAULT_HTTP_PORT = 9000
DEFAULT_PTY_PORT = 9001

#: Ports owned by the platform inside the official base image.
# The FC reserved ports are the alicloud-express profile, not the HTTP API. Port 9000 stays the server default.
ENVD_PORT = 49983
GATEWAY_PORT = 5000
CODE_INTERPRETER_PORT = 49999
RESERVED_PORTS = frozenset({ENVD_PORT, GATEWAY_PORT, CODE_INTERPRETER_PORT})

DEFAULT_USER = "user"
DEFAULT_HOME = "/home/user"

#: Well-known policy location auto-loaded at start.
POLICY_FILE = "/etc/easy-sandbox/server-policy.json"

START_COMMAND = f"easy-sandbox-server serve --port {DEFAULT_HTTP_PORT}"
READY_COMMAND = f"easy-sandbox-server healthcheck --port {DEFAULT_HTTP_PORT}"
