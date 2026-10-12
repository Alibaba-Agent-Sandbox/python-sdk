"""Guards of Server SDK v2 (stdlib only): path scoping and command allow-lists.

Stage WP-3 of ``docs/en/design/server-sdk-v2/10-implementation-plan.md``.  The flat
``server/guard.py`` stays importable; this package re-exports it and adds the scope helpers of
design 03 (sections 6 and 7) that the in-flight :class:`~easy_sandbox.server.runtime.PolicyEngine`
can call through an ``EndpointContext``.

Deferred to later work packages: ``env.py``, ``urls.py``, ``harden.py``, ``launcher.py`` and the
race-free ``open_beneath`` family.
"""

from __future__ import annotations

from .commands import (
    CommandGuard,
    check_command,
    command_guard,
    command_guard_from_context,
    expand_short_flags,
)
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
    "command_guard",
    "command_guard_from_context",
    "expand_short_flags",
    "open_checked",
    "path_guard",
    "path_guard_from_context",
]
