"""Race-free writes and listings under an environment's workspace directory.

The scope is one directory. Writes never follow a symlink, never overwrite a file whose
bytes differ, refuse agent-config locations (the files change what the next CLI turn runs)
and cap the size. Listings read regular files only and skip those same locations.
"""

from __future__ import annotations

import contextlib
import os
import posixpath
import stat

from .errors import LocalApiError

__all__ = [
    "check_workspace_root",
    "list_files",
    "normalize_relative",
    "refused_location",
    "write_new_file",
]

#: Top-level directories whose contents steer the next CLI turn.
_REFUSED_TOP = frozenset({".git", ".codex", ".claude", ".cursor", ".qwen", ".qoder", ".ssh"})
_REFUSED_NAMES = frozenset(
    {
        ".mcp.json",
        "agents.md",
        "qwen.md",
        "claude.md",
        "gemini.md",
        ".bashrc",
        ".bash_profile",
        ".bash_login",
        ".bash_logout",
        ".profile",
        ".zshrc",
        ".zprofile",
        ".zshenv",
        ".envrc",
    }
)
_SYSTEM_ROOTS = (
    "/proc",
    "/sys",
    "/dev",
    "/etc",
    "/boot",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/run",
    "/var/lib",
)
_MAX_PATH = 1024
_MAX_LIST = 10_000
_MAX_DEPTH = 20


def check_workspace_root(path: str, field: str = "environment.workspace_directory") -> str:
    """Admit a workspace directory: absolute, no ``..``, not ``/`` or a system tree.

    The directory is created when missing. Returns the real path.
    """
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise LocalApiError(f"{field}: must be an absolute path", param=field)
    if ".." in path.split("/"):
        raise LocalApiError(f"{field}: must not contain '..'", param=field)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        raise LocalApiError(
            f"{field}: cannot create the directory", param=field, code="agents.workspace_error"
        ) from None
    real = os.path.realpath(path)
    if real == "/" or any(real == r or real.startswith(r + "/") for r in _SYSTEM_ROOTS):
        raise LocalApiError(
            f"{field}: system directories are not admitted", param=field, code="agents.path_refused"
        )
    return real


def normalize_relative(path: object, field: str = "path") -> str:
    """Interpret an absolute ``/workspace/...`` path relative to the workspace directory."""
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise LocalApiError(f"{field}: must be an absolute path", param=field)
    if len(path) > _MAX_PATH:
        raise LocalApiError(f"{field}: path is too long", param=field)
    raw = path.split("/")
    if ".." in raw:
        raise LocalApiError(f"{field}: must not contain '..'", param=field)
    parts = [p for p in raw if p not in ("", ".")]
    if parts and parts[0] == "workspace":
        parts = parts[1:]
    if any(len(p) > 255 for p in parts):
        raise LocalApiError(f"{field}: a path component is too long", param=field)
    return "/".join(parts)


def refused_location(rel: str) -> str | None:
    """Why *rel* may not be written, or ``None``."""
    parts = rel.split("/")
    if parts[0] in _REFUSED_TOP:
        return f"writes under {parts[0]}/ are refused: they change what the agent runs"
    if parts[-1].lower() in _REFUSED_NAMES:
        return f"writing {parts[-1]} is refused: it changes what the agent runs"
    return None


def write_new_file(root: str, rel: str, data: bytes) -> bool:
    """Create ``root/rel`` with *data*. Returns ``True`` when written, ``False`` when identical.

    Raises:
        LocalApiError: ``agents.file_exists`` when a different file is already there,
            ``agents.path_refused`` for a symlink, a non-directory component or a
            refused location.
    """
    if not rel:
        raise LocalApiError("path: names the workspace directory itself", param="path")
    why = refused_location(rel)
    if why:
        raise LocalApiError(f"path: {why}", param="path", code="agents.path_refused")
    parts = rel.split("/")
    flags_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    fds: list[int] = []
    try:
        try:
            current = os.open(root, flags_dir)
        except OSError:
            raise LocalApiError(
                "workspace directory is not available",
                code="agents.workspace_error",
            ) from None
        fds.append(current)
        for component in parts[:-1]:
            try:
                os.mkdir(component, 0o755, dir_fd=current)
            except FileExistsError:
                pass
            except OSError:
                raise LocalApiError(
                    "path: cannot create the directory", param="path", code="agents.path_refused"
                ) from None
            try:
                current = os.open(
                    component, flags_dir | getattr(os, "O_NOFOLLOW", 0), dir_fd=current
                )
            except OSError:
                raise LocalApiError(
                    "path: a component is a symlink or not a directory",
                    param="path",
                    code="agents.path_refused",
                ) from None
            fds.append(current)
        name = parts[-1]
        create = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(name, create | getattr(os, "O_CLOEXEC", 0), 0o644, dir_fd=current)
        except FileExistsError:
            return _same_bytes_or_refuse(current, name, data)
        except OSError:
            raise LocalApiError(
                "path: cannot create the file", param="path", code="agents.path_refused"
            ) from None
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return True
    finally:
        for fd in reversed(fds):
            with contextlib.suppress(OSError):
                os.close(fd)


def _same_bytes_or_refuse(dir_fd: int, name: str, data: bytes) -> bool:
    refuse = LocalApiError(
        "path: a different file already exists; files are never overwritten",
        param="path",
        code="agents.file_exists",
    )
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=dir_fd,
        )
    except OSError:
        raise refuse from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(data) or info.st_nlink > 1:
            raise refuse
        with os.fdopen(fd, "rb", closefd=False) as fh:
            existing = fh.read(len(data) + 1)
    finally:
        os.close(fd)
    if existing != data:
        raise refuse
    return False


def list_files(root: str, prefix: str = "") -> list[tuple[str, int]]:
    """Regular files under ``root/prefix`` as ``(relative path, size)``, sorted by path parts.

    Symlinks are not followed or listed; agent-config locations are skipped.
    """
    base = root
    for component in [p for p in prefix.split("/") if p]:
        base = os.path.join(base, component)
        try:
            info = os.lstat(base)
        except OSError:
            return []
        if not stat.S_ISDIR(info.st_mode):
            return []
    out: list[tuple[str, int]] = []
    stack: list[tuple[str, str, int]] = [(base, prefix.strip("/"), 0)]
    while stack and len(out) < _MAX_LIST:
        directory, rel_dir, depth = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            if rel.split("/")[0] in _REFUSED_TOP:
                continue
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < _MAX_DEPTH:
                        stack.append((entry.path, rel, depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    out.append((rel, entry.stat(follow_symlinks=False).st_size))
            except OSError:
                continue
            if len(out) >= _MAX_LIST:
                break
    out.sort(key=lambda row: posixpath.normpath(row[0]).split("/"))
    return out
