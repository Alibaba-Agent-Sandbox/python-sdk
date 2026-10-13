"""File-operation route handlers for the sandbox HTTP server.

Provides endpoints for directory listing, file stat, mkdir, delete, move,
search, streaming upload/download, and archive creation.  All routes are
registered on the module-level default :class:`RouteTable` at import time
(side-effect) under :data:`CapabilityGroup.FILE_OPS`.
"""

from __future__ import annotations

import base64
import fnmatch
import io
import os
import shutil
import tarfile
import threading
import zipfile
from datetime import datetime, timezone
from typing import Any

from .guard import OP_DELETE, OP_READ, OP_WRITE, PathGuard, open_checked
from .policy import PolicyDenied
from .router import CapabilityGroup, default_table
from .routes import _resolve_safe_path
from .runtime import EndpointContext, context_of
from .types import ServerRequest, ServerResponse, SSEResponse

__all__: list[str] = []

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_ENTRIES = 1000
_DEFAULT_MAX_DEPTH = 3
_SEARCH_MAX_DEPTH = 5
_SEARCH_MAX_RESULTS = 100
_SEARCH_TIMEOUT_SECONDS = 10
_CHUNK_SIZE = 64 * 1024  # 64 KB
_DEFAULT_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
_MAX_UPLOAD_ENV_VAR = "EBX_MAX_UPLOAD_SIZE"
_ARCHIVE_MAX_SIZE = 100 * 1024 * 1024  # 100 MB
_ARCHIVE_MAX_FILES = 10_000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_mtime(ts: float) -> str:
    """Convert a POSIX timestamp to an ISO 8601 UTC string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _max_upload_size() -> int:
    """Return the configured maximum upload size in bytes."""
    raw = os.environ.get(_MAX_UPLOAD_ENV_VAR, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _DEFAULT_MAX_UPLOAD_SIZE


def _resolve(ctx: EndpointContext | None, raw: str, op: str = OP_READ, field: str = "") -> str:
    """Resolve *raw* via the policy guard, or the legacy base-dir check without a policy.

    Raises:
        ValueError: legacy mode, path escapes the base directory.
        PolicyDenied: policy mode, the guard rejected the path.
    """
    if ctx is None:
        return _resolve_safe_path(raw)
    return ctx.resolve_path(raw, op, field=field)


def _legacy_inside_base(path: str) -> bool:
    """Whether the real location of *path* is inside ``EBX_SERVER_BASE_DIR``."""
    base = os.path.realpath(os.environ.get("EBX_SERVER_BASE_DIR", "/home/user"))
    real = os.path.realpath(path)
    return real == base or real.startswith(base + os.sep)


def _tree_denied(guard: PathGuard, root: str, op: str) -> bool:
    """Whether any descendant of directory *root* fails the guard (bounded walk)."""
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [*dirnames, *filenames]:
            seen += 1
            if seen > 100_000 or not guard.permits(os.path.join(dirpath, name), op):
                return True
    return False


def _protect_tree(ctx: EndpointContext, resolved: str, op: str) -> None:
    """Refuse to remove/move a boundary root or a tree holding denied entries."""
    guard = ctx.guard()
    if any(resolved == real for _lex, real in guard.roots()):
        raise PolicyDenied("path_denied", "The allowed root directory itself cannot be modified")
    if guard.deny and os.path.isdir(resolved) and _tree_denied(guard, resolved, op):
        raise PolicyDenied("path_denied", "Directory contains entries denied by policy")


def _extension_check(ctx: EndpointContext, resolved: str) -> None:
    """Enforce ``allow_extensions`` / ``deny_extensions`` on the target file name."""
    ext = os.path.splitext(resolved)[1].lower()
    allow = [e.lower() for e in ctx.param("allow_extensions", [])]
    deny = [e.lower() for e in ctx.param("deny_extensions", [])]
    if (allow and ext not in allow) or ext in deny:
        raise PolicyDenied(
            "extension_not_allowed", f"Files with extension {ext or '(none)'!r} are not allowed"
        )


def _entry_type(path: str) -> str:
    """Return ``'file'``, ``'directory'``, or ``'symlink'``."""
    if os.path.islink(path):
        return "symlink"
    if os.path.isdir(path):
        return "directory"
    return "file"


def _too_large(size: int, limit: int, ctx: EndpointContext | None) -> ServerResponse:
    body: dict[str, Any] = {
        "error": f"File size {size} exceeds limit {limit}",
        "type": "ValueError",
    }
    if ctx is not None:
        body.update({"code": "payload_too_large", "limit": limit})
    return ServerResponse(status=413, body=body)


def _write_checked(ctx: EndpointContext, resolved: str, data: bytes) -> None:
    """Write *data* using an ``O_NOFOLLOW`` descriptor verified against the guard."""
    flags = os.O_WRONLY | os.O_CREAT
    overwrite = ctx.param("overwrite", True)
    if not overwrite:
        flags |= os.O_EXCL
    try:
        fd = open_checked(ctx.guard(), resolved, flags, OP_WRITE)
    except FileExistsError as exc:
        raise PolicyDenied(
            "file_exists", "File already exists", status=409, error_type="FileExistsError"
        ) from exc
    with os.fdopen(fd, "wb") as f:
        f.truncate(0)
        offset = 0
        while offset < len(data):
            f.write(data[offset : offset + _CHUNK_SIZE])
            offset += _CHUNK_SIZE


def _read_checked(ctx: EndpointContext, resolved: str) -> bytes | ServerResponse:
    """Read a file through a verified descriptor, honouring ``limits.max_bytes``."""
    fd = open_checked(ctx.guard(), resolved, os.O_RDONLY, OP_READ)
    limit = ctx.limit("max_bytes")
    with os.fdopen(fd, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        if limit is not None and size > int(limit):
            return _too_large(size, int(limit), ctx)
        cap = int(limit) + 1 if limit is not None else None
        data = f.read(cap) if cap is not None else f.read()
    if limit is not None and len(data) > int(limit):
        return _too_large(len(data), int(limit), ctx)
    return data


# ---------------------------------------------------------------------------
# GET /files/list
# ---------------------------------------------------------------------------


def _handle_files_list(request: ServerRequest) -> ServerResponse:
    """List directory contents, optionally recursive."""
    raw_path = request.query.get("path", [""])[0]
    if not raw_path:
        return ServerResponse.error(400, "Missing 'path' query parameter", "ValueError")

    recursive_str = request.query.get("recursive", ["false"])[0].lower()
    recursive = recursive_str in {"true", "yes", "1"}

    try:
        max_entries = int(request.query.get("max_entries", [str(_DEFAULT_MAX_ENTRIES)])[0])
    except ValueError:
        max_entries = _DEFAULT_MAX_ENTRIES

    ctx = context_of(request)
    entry_cap = int(ctx.limit("max_entries", _DEFAULT_MAX_ENTRIES)) if ctx else _DEFAULT_MAX_ENTRIES
    max_depth = int(ctx.limit("max_depth", _DEFAULT_MAX_DEPTH)) if ctx else _DEFAULT_MAX_DEPTH
    max_entries = min(max_entries, entry_cap)

    try:
        safe_path = _resolve(ctx, raw_path)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    if not os.path.isdir(safe_path):
        return ServerResponse.error(404, f"Directory not found: {raw_path}", "FileNotFoundError")

    base_dir = os.environ.get("EBX_SERVER_BASE_DIR", "/home/user")
    base_dir = os.path.realpath(base_dir)
    guard = ctx.guard() if ctx else None

    entries: list[dict[str, Any]] = []

    def _scan(dir_path: str, depth: int) -> None:
        if len(entries) >= max_entries:
            return
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    if len(entries) >= max_entries:
                        return
                    if guard is not None:
                        if not guard.permits(entry.path):
                            continue
                    # Don't follow symlinks that point outside base_dir
                    elif entry.is_symlink():
                        real = os.path.realpath(entry.path)
                        if not real.startswith(base_dir + os.sep) and real != base_dir:
                            continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "directory" if entry.is_dir(follow_symlinks=False) else "file",
                            "size": stat.st_size,
                            "modified": _iso_mtime(stat.st_mtime),
                        }
                    )
                    is_subdir = entry.is_dir(follow_symlinks=False)
                    if recursive and is_subdir and depth < max_depth:
                        _scan(entry.path, depth + 1)
        except PermissionError:
            pass

    _scan(safe_path, 1)
    return ServerResponse.ok({"entries": entries})


# ---------------------------------------------------------------------------
# GET /files/stat
# ---------------------------------------------------------------------------


def _handle_files_stat(request: ServerRequest) -> ServerResponse:
    """Return stat information for a single file or directory."""
    raw_path = request.query.get("path", [""])[0]
    if not raw_path:
        return ServerResponse.error(400, "Missing 'path' query parameter", "ValueError")

    try:
        safe_path = _resolve(context_of(request), raw_path)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    exists = os.path.exists(safe_path)
    if not exists:
        return ServerResponse.ok(
            {
                "name": os.path.basename(safe_path),
                "path": safe_path,
                "type": "unknown",
                "size": 0,
                "permissions": "",
                "modified": "",
                "accessed": "",
                "created": "",
                "exists": False,
            }
        )

    try:
        st = os.stat(safe_path, follow_symlinks=False)
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok(
        {
            "name": os.path.basename(safe_path),
            "path": safe_path,
            "type": _entry_type(safe_path),
            "size": st.st_size,
            "permissions": oct(st.st_mode)[-3:],
            "modified": _iso_mtime(st.st_mtime),
            "accessed": _iso_mtime(st.st_atime),
            "created": _iso_mtime(st.st_ctime),
            "exists": True,
        }
    )


# ---------------------------------------------------------------------------
# POST /files/mkdir
# ---------------------------------------------------------------------------


def _handle_files_mkdir(request: ServerRequest) -> ServerResponse:
    """Create a directory (with parents)."""
    body = request.body or {}
    raw_path = body.get("path", "")
    if not raw_path or not isinstance(raw_path, str):
        return ServerResponse.error(400, "Missing or invalid 'path'", "ValueError")

    try:
        safe_path = _resolve(context_of(request), raw_path, OP_WRITE)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    try:
        os.makedirs(safe_path, exist_ok=True)
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok({"path": safe_path, "created": True})


# ---------------------------------------------------------------------------
# DELETE /files
# ---------------------------------------------------------------------------


def _handle_files_delete(request: ServerRequest) -> ServerResponse:
    """Delete a file or directory."""
    raw_path = request.query.get("path", [""])[0]
    if not raw_path:
        return ServerResponse.error(400, "Missing 'path' query parameter", "ValueError")

    ctx = context_of(request)
    try:
        safe_path = _resolve(ctx, raw_path, OP_DELETE)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    if not os.path.exists(safe_path):
        return ServerResponse.error(404, f"Path not found: {raw_path}", "FileNotFoundError")

    if ctx is not None:
        _protect_tree(ctx, safe_path, OP_DELETE)

    try:
        if os.path.isdir(safe_path):
            shutil.rmtree(safe_path)
        else:
            os.remove(safe_path)
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok({"path": safe_path, "deleted": True})


# ---------------------------------------------------------------------------
# POST /files/move
# ---------------------------------------------------------------------------


def _handle_files_move(request: ServerRequest) -> ServerResponse:
    """Move or rename a file/directory."""
    body = request.body or {}
    source = body.get("source", "")
    destination = body.get("destination", "")

    if not source or not isinstance(source, str):
        return ServerResponse.error(400, "Missing or invalid 'source'", "ValueError")
    if not destination or not isinstance(destination, str):
        return ServerResponse.error(400, "Missing or invalid 'destination'", "ValueError")

    ctx = context_of(request)
    try:
        safe_src = _resolve(ctx, source, OP_DELETE, "source")
    except ValueError as exc:
        return ServerResponse.error(400, f"source: {exc}", "ValueError")

    try:
        safe_dst = _resolve(ctx, destination, OP_WRITE, "destination")
    except ValueError as exc:
        return ServerResponse.error(400, f"destination: {exc}", "ValueError")

    if not os.path.exists(safe_src):
        return ServerResponse.error(404, f"Source not found: {source}", "FileNotFoundError")

    if ctx is not None:
        _protect_tree(ctx, safe_src, OP_DELETE)

    try:
        # Ensure destination parent exists
        os.makedirs(os.path.dirname(safe_dst) or ".", exist_ok=True)
        shutil.move(safe_src, safe_dst)
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok({"source": safe_src, "destination": safe_dst})


# ---------------------------------------------------------------------------
# POST /files/search
# ---------------------------------------------------------------------------


def _handle_files_search(request: ServerRequest) -> ServerResponse:
    """Search for files matching a glob pattern."""
    body = request.body or {}
    raw_path = body.get("path", "")
    pattern = body.get("pattern", "")

    if not raw_path or not isinstance(raw_path, str):
        return ServerResponse.error(400, "Missing or invalid 'path'", "ValueError")
    if not pattern or not isinstance(pattern, str):
        return ServerResponse.error(400, "Missing or invalid 'pattern'", "ValueError")

    try:
        max_depth = int(body.get("max_depth", _SEARCH_MAX_DEPTH))
        max_results = int(body.get("max_results", _SEARCH_MAX_RESULTS))
    except (ValueError, TypeError):
        return ServerResponse.error(
            400,
            "Invalid 'max_depth' or 'max_results': must be integers",
            "ValueError",
        )

    ctx = context_of(request)
    try:
        safe_path = _resolve(ctx, raw_path)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    if not os.path.isdir(safe_path):
        return ServerResponse.error(404, f"Directory not found: {raw_path}", "FileNotFoundError")

    guard = ctx.guard() if ctx else None
    search_timeout: float = _SEARCH_TIMEOUT_SECONDS
    if ctx is not None:
        max_depth = min(max_depth, int(ctx.limit("max_depth", max_depth)))
        max_results = min(max_results, int(ctx.limit("max_results", max_results)))
        search_timeout = float(ctx.limit("timeout_seconds", _SEARCH_TIMEOUT_SECONDS))

    results: list[dict[str, str]] = []
    timed_out = False
    cancelled = threading.Event()

    # Use a timer thread for timeout (works in any thread, unlike SIGALRM)
    timer = threading.Timer(search_timeout, cancelled.set)
    timer.start()

    try:
        for dirpath, dirnames, filenames in os.walk(safe_path):
            if cancelled.is_set():
                timed_out = True
                break
            rel_depth = dirpath[len(safe_path) :].count(os.sep)
            if rel_depth >= max_depth:
                dirnames.clear()
                continue
            if guard is not None:
                dirnames[:] = [d for d in dirnames if guard.permits(os.path.join(dirpath, d))]
            for name in filenames:
                if cancelled.is_set():
                    timed_out = True
                    break
                if fnmatch.fnmatch(name, pattern):
                    full = os.path.join(dirpath, name)
                    if guard is not None and not guard.permits(full):
                        continue
                    results.append(
                        {
                            "name": name,
                            "path": full,
                        }
                    )
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results or timed_out:
                break
    finally:
        timer.cancel()

    return ServerResponse.ok(
        {
            "results": results,
            "timed_out": timed_out,
        }
    )


# ---------------------------------------------------------------------------
# POST /files/upload-stream
# ---------------------------------------------------------------------------


def _handle_files_upload_stream(request: ServerRequest) -> ServerResponse:
    """Upload a file via base64-encoded content with chunked decoding."""
    body = request.body or {}
    raw_path = body.get("path", "")
    content_b64 = body.get("content_base64", "")

    if not raw_path or not isinstance(raw_path, str):
        return ServerResponse.error(400, "Missing or invalid 'path'", "ValueError")
    if not content_b64 or not isinstance(content_b64, str):
        return ServerResponse.error(400, "Missing or invalid 'content_base64'", "ValueError")

    ctx = context_of(request)
    try:
        safe_path = _resolve(ctx, raw_path, OP_WRITE)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")
    if ctx is not None:
        _extension_check(ctx, safe_path)

    # Decode the full base64 first to validate, then write in chunks
    try:
        data = base64.b64decode(content_b64, validate=True)
    except Exception as exc:
        return ServerResponse.error(400, f"Invalid base64: {exc}", "ValueError")

    max_size = int(ctx.limit("max_bytes", _max_upload_size())) if ctx else _max_upload_size()
    if len(data) > max_size:
        return _too_large(len(data), max_size, ctx)

    try:
        os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
        if ctx is None:
            with open(safe_path, "wb") as f:
                offset = 0
                while offset < len(data):
                    chunk = data[offset : offset + _CHUNK_SIZE]
                    f.write(chunk)
                    offset += _CHUNK_SIZE
        else:
            _write_checked(ctx, safe_path, data)
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok({"path": safe_path, "bytes": len(data)})


# ---------------------------------------------------------------------------
# GET /files/download-stream
# ---------------------------------------------------------------------------


def _handle_files_download_stream(request: ServerRequest) -> ServerResponse:
    """Download a file, reading in chunks and returning base64."""
    raw_path = request.query.get("path", [""])[0]
    if not raw_path:
        return ServerResponse.error(400, "Missing 'path' query parameter", "ValueError")

    ctx = context_of(request)
    try:
        safe_path = _resolve(ctx, raw_path)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")

    if not os.path.isfile(safe_path):
        return ServerResponse.error(404, f"File not found: {raw_path}", "FileNotFoundError")

    try:
        if ctx is None:
            buf = io.BytesIO()
            with open(safe_path, "rb") as f:
                while True:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    buf.write(chunk)
            file_data = buf.getvalue()
        else:
            read_result = _read_checked(ctx, safe_path)
            if isinstance(read_result, ServerResponse):
                return read_result
            file_data = read_result
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    return ServerResponse.ok(
        {
            "path": safe_path,
            "content_base64": base64.b64encode(file_data).decode("ascii"),
            "bytes": len(file_data),
        }
    )


# ---------------------------------------------------------------------------
# POST /files/archive
# ---------------------------------------------------------------------------


def _archive_members(sp: str, guard: PathGuard | None) -> list[tuple[str, str]]:
    """Return ``(real_path, arcname)`` pairs for *sp*, skipping unsafe/denied entries.

    Symlinks are never followed out of the boundary: a file symlink is included only
    when its target is inside the boundary (policy guard, or ``EBX_SERVER_BASE_DIR``
    in legacy mode) and not denied.
    """

    def ok(path: str) -> bool:
        if guard is not None:
            return guard.permits(path)
        return not os.path.islink(path) or _legacy_inside_base(path)

    base_name = os.path.basename(sp)
    if os.path.isfile(sp):
        return [(sp, base_name)] if ok(sp) else []
    members: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(sp):
        if guard is not None:
            dirnames[:] = [d for d in dirnames if guard.permits(os.path.join(dirpath, d))]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            if ok(full):
                members.append((full, os.path.join(base_name, os.path.relpath(full, sp))))
    return members


def _handle_files_archive(request: ServerRequest) -> ServerResponse:
    """Create an archive (tar.gz or zip) from a list of paths."""
    body = request.body or {}
    paths = body.get("paths")
    fmt = body.get("format", "tar.gz")

    if not paths or not isinstance(paths, list):
        return ServerResponse.error(400, "Missing or invalid 'paths'", "ValueError")
    if fmt not in {"tar.gz", "zip"}:
        return ServerResponse.error(400, f"Unsupported format: {fmt}", "ValueError")

    ctx = context_of(request)
    max_files = int(ctx.limit("max_files", _ARCHIVE_MAX_FILES)) if ctx else _ARCHIVE_MAX_FILES
    max_size = int(ctx.limit("max_bytes", _ARCHIVE_MAX_SIZE)) if ctx else _ARCHIVE_MAX_SIZE
    guard = ctx.guard() if ctx else None

    safe_paths: list[str] = []
    for raw in paths:
        if not isinstance(raw, str):
            return ServerResponse.error(400, "All paths must be strings", "ValueError")
        try:
            safe_paths.append(_resolve(ctx, raw))
        except ValueError as exc:
            return ServerResponse.error(400, str(exc), "ValueError")

    # Validate all paths exist
    for sp in safe_paths:
        if not os.path.exists(sp):
            return ServerResponse.error(404, f"Path not found: {sp}", "FileNotFoundError")

    # Count files and check limits
    total_files = 0
    for sp in safe_paths:
        if os.path.isfile(sp):
            total_files += 1
        elif os.path.isdir(sp):
            for _dirpath, _dirnames, filenames in os.walk(sp):
                total_files += len(filenames)
                if total_files > max_files:
                    return ServerResponse.error(
                        400,
                        f"Too many files ({total_files}+), limit is {max_files}",
                        "ValueError",
                    )

    buf = io.BytesIO()
    try:
        if fmt == "tar.gz":
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for sp in safe_paths:
                    if guard is None:
                        tar.add(sp, arcname=os.path.basename(sp))
                    else:
                        for full, arcname in _archive_members(sp, guard):
                            tar.add(full, arcname=arcname, recursive=False)
        else:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for sp in safe_paths:
                    for full, arcname in _archive_members(sp, guard):
                        zf.write(full, arcname)
    except OSError as exc:
        return ServerResponse.error(500, str(exc), type(exc).__name__)

    archive_data = buf.getvalue()
    if len(archive_data) > max_size:
        return ServerResponse(
            status=413,
            body={
                "error": f"Archive size {len(archive_data)} exceeds limit {max_size}",
                "type": "ValueError",
                **({"code": "payload_too_large", "limit": max_size} if ctx else {}),
            },
        )

    return ServerResponse.ok(
        {
            "content_base64": base64.b64encode(archive_data).decode("ascii"),
            "format": fmt,
            "bytes": len(archive_data),
        }
    )


# ---------------------------------------------------------------------------
# GET /files/watch  (SSE, polling)
# ---------------------------------------------------------------------------

_WATCH_DEFAULT_DURATION = 300.0
_WATCH_MAX_ENTRIES = 5000


def _snapshot(
    root: str, recursive: bool, guard: PathGuard | None
) -> dict[str, tuple[int, int, bool]]:
    """Return ``{path: (mtime_ns, size, is_dir)}`` for the tree under *root* (bounded)."""
    snap: dict[str, tuple[int, int, bool]] = {}

    def scan(directory: str, depth: int) -> None:
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if len(snap) >= _WATCH_MAX_ENTRIES:
                        return
                    if guard is not None and not guard.permits(entry.path):
                        continue
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    is_dir = entry.is_dir(follow_symlinks=False)
                    snap[entry.path] = (st.st_mtime_ns, st.st_size, is_dir)
                    if recursive and is_dir and depth < _DEFAULT_MAX_DEPTH + 2:
                        scan(entry.path, depth + 1)
        except OSError:
            return

    scan(root, 1)
    return snap


def _sse(event: str, data: dict[str, Any]) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _handle_files_watch(request: ServerRequest) -> SSEResponse | ServerResponse:
    """``GET /files/watch`` — stream create/modify/delete events for a directory."""
    import time

    raw_path = request.query.get("path", [""])[0]
    if not raw_path:
        return ServerResponse.error(400, "Missing 'path' query parameter", "ValueError")
    recursive = request.query.get("recursive", ["false"])[0].lower() in {"true", "yes", "1"}
    try:
        interval = min(5.0, max(0.1, float(request.query.get("interval", ["0.5"])[0])))
        duration = float(request.query.get("timeout", [str(_WATCH_DEFAULT_DURATION)])[0])
    except ValueError:
        return ServerResponse.error(400, "Invalid 'interval' or 'timeout'", "ValueError")
    ctx = context_of(request)
    cap = (
        float(ctx.limit("max_duration_seconds", _WATCH_DEFAULT_DURATION))
        if ctx
        else (_WATCH_DEFAULT_DURATION)
    )
    duration = min(max(duration, 0.1), cap)
    try:
        safe_path = _resolve(ctx, raw_path)
    except ValueError as exc:
        return ServerResponse.error(400, str(exc), "ValueError")
    if not os.path.isdir(safe_path):
        return ServerResponse.error(404, f"Directory not found: {raw_path}", "FileNotFoundError")
    guard = ctx.guard() if ctx else None

    def events() -> Any:
        previous = _snapshot(safe_path, recursive, guard)
        yield _sse("ready", {"path": safe_path})
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
            current = _snapshot(safe_path, recursive, guard)
            for path, meta in sorted(current.items()):
                old = previous.get(path)
                if old is None:
                    yield _sse("change", {"type": "created", "path": path, "is_dir": meta[2]})
                elif old[:2] != meta[:2]:
                    yield _sse("change", {"type": "modified", "path": path, "is_dir": meta[2]})
            for path, meta in sorted(previous.items()):
                if path not in current:
                    yield _sse("change", {"type": "deleted", "path": path, "is_dir": meta[2]})
            previous = current
        yield _sse("end", {"reason": "timeout"})

    return SSEResponse(event_iterator=events())


# ---------------------------------------------------------------------------
# Route registration (import side-effect)
# ---------------------------------------------------------------------------

_table = default_table()

_table.register(
    "GET",
    "/files/list",
    _handle_files_list,
    group=CapabilityGroup.FILE_OPS,
    name="files_list",
)
_table.register(
    "GET",
    "/files/stat",
    _handle_files_stat,
    group=CapabilityGroup.FILE_OPS,
    name="files_stat",
)
_table.register(
    "POST",
    "/files/mkdir",
    _handle_files_mkdir,
    group=CapabilityGroup.FILE_OPS,
    name="files_mkdir",
)
_table.register(
    "DELETE",
    "/files",
    _handle_files_delete,
    group=CapabilityGroup.FILE_OPS,
    name="files_delete",
)
_table.register(
    "POST",
    "/files/move",
    _handle_files_move,
    group=CapabilityGroup.FILE_OPS,
    name="files_move",
)
_table.register(
    "POST",
    "/files/search",
    _handle_files_search,
    group=CapabilityGroup.FILE_OPS,
    name="files_search",
)
_table.register(
    "POST",
    "/files/upload-stream",
    _handle_files_upload_stream,
    group=CapabilityGroup.FILE_OPS,
    name="files_upload_stream",
)
_table.register(
    "GET",
    "/files/download-stream",
    _handle_files_download_stream,
    group=CapabilityGroup.FILE_OPS,
    name="files_download_stream",
)
_table.register(
    "POST",
    "/files/archive",
    _handle_files_archive,
    group=CapabilityGroup.FILE_OPS,
    name="files_archive",
)
_table.register(
    "GET",
    "/files/watch",
    _handle_files_watch,
    group=CapabilityGroup.FILE_OPS,
    streaming=True,
    name="files_watch",
)
