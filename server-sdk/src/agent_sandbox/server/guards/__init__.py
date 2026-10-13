"""Guards (stdlib only): path, command, env, URL and process checks.

``server/guard.py`` holds :class:`PathGuard` and the checked-open helpers; this package re-exports
them and adds the scope helpers that the :class:`~agent_sandbox.server.runtime.PolicyEngine`
reaches through an ``EndpointContext``.

``check_env``, ``check_url`` and ``check_process`` are called from the live routes
(``enforce_exec_policy``, ``handle_env_set``, ``handle_browser_navigate``,
``handle_code_run``, ``_handle_create_session``).
"""

from __future__ import annotations

from .commands import (
    CommandGuard,
    check_command,
    command_guard,
    command_guard_from_context,
    expand_short_flags,
)
from .env import check_env
from .paths import (
    MAX_PATH_LENGTH,
    OP_DELETE,
    OP_EXEC,
    OP_READ,
    OP_WRITE,
    SYSTEM_DENY,
    PathGuard,
    open_checked,
    path_guard,
    path_guard_from_context,
)
from .process import check_process
from .urls import check_url

__all__ = [
    "MAX_PATH_LENGTH",
    "OP_DELETE",
    "OP_EXEC",
    "OP_READ",
    "OP_WRITE",
    "SYSTEM_DENY",
    "CommandGuard",
    "PathGuard",
    "check_command",
    "check_env",
    "check_process",
    "check_url",
    "command_guard",
    "command_guard_from_context",
    "expand_short_flags",
    "open_checked",
    "path_guard",
    "path_guard_from_context",
]
