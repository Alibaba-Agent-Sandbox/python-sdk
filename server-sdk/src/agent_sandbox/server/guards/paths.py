"""Path guards: allow roots, deny globs, read-only scopes, non-removable system deny list.

:class:`PathGuard` itself lives in :mod:`agent_sandbox.server.guard` and is re-exported.
This module adds the constructors: a root is a directory
(never ``/`` or a pattern) and ``/proc``, ``/sys`` and ``/dev`` are always denied.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..guard import (
    MAX_PATH_LENGTH,
    OP_DELETE,
    OP_EXEC,
    OP_READ,
    OP_WRITE,
    PathGuard,
    open_checked,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..runtime import EndpointContext

__all__ = [
    "MAX_PATH_LENGTH",
    "OP_DELETE",
    "OP_EXEC",
    "OP_READ",
    "OP_WRITE",
    "SYSTEM_DENY",
    "PathGuard",
    "open_checked",
    "path_guard",
    "path_guard_from_context",
]

#: Directories no scope can reach, whatever its roots.
SYSTEM_DENY: tuple[str, ...] = ("/proc", "/sys", "/dev")


def _with_system_deny(deny: Sequence[str]) -> tuple[str, ...]:
    extra = tuple(p for p in SYSTEM_DENY if p not in deny)
    return (*deny, *extra)


def path_guard(
    *roots: str,
    deny: Sequence[str] = (),
    readonly: bool = False,
    symlinks: str = "within",
) -> PathGuard:
    """Build a guard that admits paths under *roots* only.

    Args:
        roots: One or more directories; relative inputs resolve against the first.
        deny: Deny globs (``**/.env``, ``*.pem``, ``/srv/secret``); a directory pattern
            denies its whole subtree.
        readonly: Refuse ``write`` and ``delete`` operations.
        symlinks: ``"within"`` (target must stay inside a root) or ``"never"``.

    Raises:
        ValueError: no root, a root that is ``/``, relative, or contains glob characters.
    """
    if not roots:
        raise ValueError("path_guard needs at least one root")
    for root in roots:
        if not isinstance(root, str) or not os.path.isabs(root):
            raise ValueError(f"root must be an absolute directory path: {root!r}")
        if os.path.normpath(root) == os.sep:
            raise ValueError("root '/' is not allowed: it would expose /proc and every secret")
        if any(ch in root for ch in "*?[") or "\x00" in root:
            raise ValueError(f"root must be a directory, not a pattern: {root!r}")
    if symlinks not in ("within", "never"):
        raise ValueError(f"symlinks must be 'within' or 'never', got {symlinks!r}")
    return PathGuard(
        roots[0],
        allow=roots,
        deny=_with_system_deny(deny),
        read_only=readonly,
        symlinks=symlinks,
        relative_to_root=True,
    )


def path_guard_from_context(ctx: EndpointContext) -> PathGuard:
    """The endpoint's guard from the policy engine, plus the system deny list."""
    base = ctx.guard()
    return PathGuard(
        base.base_dir,
        allow=base.allow,
        deny=_with_system_deny(base.deny),
        read_only=base.read_only,
        symlinks=base.symlinks,
        relative_to_root=base.relative_to_root,
    )
