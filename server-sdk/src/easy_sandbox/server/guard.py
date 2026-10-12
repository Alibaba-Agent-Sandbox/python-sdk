"""Path scoping for the sandbox HTTP server — stdlib-only.

:class:`PathGuard` implements the ``paths`` section of an endpoint rule
(``allow`` roots, ``deny`` patterns, ``read_only``, ``symlinks``).  It returns the
**resolved** path that the operation must then use (no second resolution), and
checks run *before* any existence check so denials do not form a filesystem
oracle.  :func:`open_checked` narrows the check/use window by opening with
``O_NOFOLLOW`` and re-verifying the opened descriptor.

Residual risk (documented in the design): an attacker who can concurrently
rename *intermediate* directories (needs process/terminal access) can still race
the check; do not expose process endpoints next to path scoping.
"""

from __future__ import annotations

import errno
import fnmatch
import os
from typing import TYPE_CHECKING

from .policy import PolicyDenied

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["PathGuard", "open_checked", "MAX_PATH_LENGTH"]

MAX_PATH_LENGTH = 4096

#: Operation classes understood by ``read_only``.
OP_READ = "read"
OP_WRITE = "write"
OP_DELETE = "delete"
OP_EXEC = "exec"
_MUTATING_OPS = frozenset({OP_WRITE, OP_DELETE})
VALID_OPS = frozenset({OP_READ, OP_WRITE, OP_DELETE, OP_EXEC})


def _prefixes(path: str) -> list[str]:
    """Return *path* and every ancestor except ``/`` (``/a/b`` -> ``/a/b``, ``/a``)."""
    out: list[str] = []
    current = path
    while current and current != os.sep:
        out.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return out


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _deny_matches(path: str, pattern: str) -> bool:
    """Return whether *pattern* denies *path* or any ancestor of it.

    * no ``/`` in the pattern -> matches any path component (``*.pem``, ``.env``);
    * absolute pattern -> directory prefix (a glob is allowed: ``/home/*/.ssh``);
    * otherwise -> matches the tail of the path (``**/.env`` ~ ``*/.env``).

    Matching is case-sensitive (POSIX semantics).
    """
    if "/" not in pattern:
        return any(fnmatch.fnmatchcase(part, pattern) for part in path.split(os.sep) if part)
    stripped = pattern.rstrip("/")
    if pattern.startswith("/"):
        return any(
            prefix == stripped or fnmatch.fnmatchcase(prefix, stripped)
            for prefix in _prefixes(path)
        )
    tail = stripped[3:] if stripped.startswith("**/") else stripped
    return any(
        fnmatch.fnmatchcase(prefix, "*/" + tail) or fnmatch.fnmatchcase(prefix, tail)
        for prefix in _prefixes(path)
    )


class PathGuard:
    """Resolve and authorise filesystem paths for one endpoint.

    Args:
        base_dir: Default boundary when *allow* is empty.
        allow: Allowed root directories (replace *base_dir* when given).
        deny: Deny patterns (directory prefixes or globs).
        read_only: Reject ``write`` / ``delete`` operations.
        symlinks: ``"within"`` or ``"never"``.
        relative_to_root: Resolve relative inputs against the first allow root
            (set when ``allow`` is configured).  Otherwise they resolve against the
            process CWD (legacy behaviour).
    """

    def __init__(
        self,
        base_dir: str,
        allow: Sequence[str] = (),
        deny: Sequence[str] = (),
        read_only: bool = False,
        symlinks: str = "within",
        relative_to_root: bool = True,
    ) -> None:
        self.base_dir = base_dir
        self.allow = tuple(allow)
        self.deny = tuple(deny)
        self.read_only = read_only
        self.symlinks = symlinks
        self.relative_to_root = relative_to_root

    # -- helpers ------------------------------------------------------- #

    def roots(self) -> list[tuple[str, str]]:
        """Return ``(lexical_root, real_root)`` pairs (realpath-ed per call)."""
        raws = self.allow or (self.base_dir,)
        return [(os.path.normpath(r), os.path.realpath(r)) for r in raws]

    def primary_root(self) -> str:
        """Directory against which relative inputs are resolved."""
        return self.roots()[0][1]

    def _denied(self, *paths: str) -> bool:
        return any(_deny_matches(p, pat) for p in paths for pat in self.deny)

    # -- main API ------------------------------------------------------ #

    def resolve(self, raw: object, op: str = OP_READ, *, field: str = "") -> str:
        """Return the resolved, authorised absolute path or raise :class:`PolicyDenied`."""
        if not isinstance(raw, str) or not raw:
            raise PolicyDenied(
                "invalid_path", "Missing or invalid path", status=400, error_type="ValueError"
            )
        if "\x00" in raw:
            raise PolicyDenied(
                "invalid_path", "Path contains a NUL byte", status=400, error_type="ValueError"
            )
        if len(raw) > MAX_PATH_LENGTH:
            raise PolicyDenied("invalid_path", "Path too long", status=400, error_type="ValueError")
        label = f"{field}: " if field else ""
        if os.path.isabs(raw):
            lexical = os.path.normpath(raw)
        elif self.relative_to_root:
            lexical = os.path.normpath(os.path.join(self.primary_root(), raw))
        else:
            lexical = os.path.normpath(os.path.abspath(raw))
        resolved = os.path.realpath(lexical)
        return self._authorise(lexical, resolved, op, label)

    def check_resolved(self, resolved: str, op: str = OP_READ) -> str:
        """Authorise an already-resolved path (used after ``open``)."""
        return self._authorise(resolved, resolved, op, "")

    def _authorise(self, lexical: str, resolved: str, op: str, label: str) -> str:
        roots = self.roots()
        root_match: tuple[str, str] | None = None
        for lex_root, real_root in roots:
            if _within(resolved, real_root):
                root_match = (lex_root, real_root)
                break
        if root_match is None:
            raise PolicyDenied(
                "path_not_allowed", f"{label}Path is outside the allowed directories"
            )
        if self.symlinks == "never" and not self._lexically_inside(lexical, root_match, resolved):
            raise PolicyDenied("symlink_denied", f"{label}Symlinks are not allowed here")
        if self._denied(resolved, lexical):
            raise PolicyDenied("path_denied", f"{label}Path is denied by policy")
        if self.read_only and op in _MUTATING_OPS:
            raise PolicyDenied("read_only", f"{label}This endpoint is read-only")
        return resolved

    def _lexically_inside(self, lexical: str, root: tuple[str, str], resolved: str) -> bool:
        """For ``symlinks: never``: ``lexical`` must map onto ``resolved`` below the root."""
        lex_root, real_root = root
        if _within(lexical, real_root):
            rel = os.path.relpath(lexical, real_root)
        elif _within(lexical, lex_root):
            rel = os.path.relpath(lexical, lex_root)
        else:
            return False
        expected = os.path.normpath(os.path.join(real_root, rel))
        return expected == resolved

    def permits(self, path: str, op: str = OP_READ) -> bool:
        """Return whether *path* (any form) may be touched; never raises."""
        try:
            self.resolve(path, op)
        except PolicyDenied:
            return False
        return True


def open_checked(guard: PathGuard, resolved: str, flags: int, op: str, mode: int = 0o666) -> int:
    """Open *resolved* with ``O_NOFOLLOW`` and re-verify the descriptor against *guard*.

    Returns an OS-level file descriptor (caller closes it / wraps it with ``os.fdopen``).

    Raises:
        PolicyDenied: ``symlink_denied`` when the final component was swapped for a
            symlink, ``path_not_allowed``/``path_denied`` when the opened inode resolves
            outside the policy.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(resolved, flags | nofollow | getattr(os, "O_CLOEXEC", 0), mode)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PolicyDenied("symlink_denied", "Symlinks are not allowed here") from exc
        raise
    try:
        proc_link = f"/proc/self/fd/{fd}"
        if os.path.exists(proc_link):
            actual = os.path.realpath(proc_link)
            if actual != resolved and not actual.endswith(" (deleted)"):
                guard.check_resolved(actual, op)
        else:
            st_fd = os.fstat(fd)
            try:
                st_path = os.stat(resolved, follow_symlinks=False)
            except OSError:
                st_path = None
            if st_path is not None and (st_path.st_ino, st_path.st_dev) != (
                st_fd.st_ino,
                st_fd.st_dev,
            ):
                raise PolicyDenied("symlink_denied", "File changed during access")
    except BaseException:
        os.close(fd)
        raise
    return fd
