"""envd API protocol — filesystem operations (Connect protocol + HTTP file API).

Connect RPC endpoints（已实测验证）:
- /filesystem.Filesystem/Stat — Get file/dir info
- /filesystem.Filesystem/MakeDir — Create directory
- /filesystem.Filesystem/ListDir — List directory contents
- /filesystem.Filesystem/Remove — Remove file/directory
- /filesystem.Filesystem/Move — Move/rename file
- /filesystem.Filesystem/WatchDir (streaming) — Watch for changes

HTTP file API（非 Connect RPC，已实测验证）:
- POST /files?path={path}&username=user (multipart) — Upload file → 201
- GET /files?path={path}&username=user — Download file → 200
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

import httpx

from agent_sandbox.models.errors import (
    FileNotFoundError_,
    FileOperationError,
    PermissionDeniedError,
)
from agent_sandbox.models.filesystem import FileInfo, FileType, WatchEvent, WatchEventType
from agent_sandbox.transport.codec import ConnectCodec
from agent_sandbox.transport.streaming import StreamReader
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
    from agent_sandbox.transport.http import HttpClient

logger = get_logger("protocol.filesystem")

_codec = ConnectCodec()

# RPC paths（已实测验证）
_STAT = _codec.build_rpc_path("filesystem", "Filesystem", "Stat")
_MAKE_DIR = _codec.build_rpc_path("filesystem", "Filesystem", "MakeDir")
_LIST_DIR = _codec.build_rpc_path("filesystem", "Filesystem", "ListDir")
_REMOVE = _codec.build_rpc_path("filesystem", "Filesystem", "Remove")
_MOVE = _codec.build_rpc_path("filesystem", "Filesystem", "Move")
_WATCH_DIR = _codec.build_rpc_path("filesystem", "Filesystem", "WatchDir")


def _name_from_path(path: str) -> str:
    """Extract the last valid path segment from *path*.

    Handles Unix paths, Windows-style back-slashes, trailing separators,
    and root-only paths.  Returns ``""`` when no meaningful segment exists
    (e.g. ``"/"`` or ``""`` or ``"C:\\``).
    """
    if not path:
        return ""
    stripped = path.rstrip("/\\")
    if not stripped:
        # Root-only path (e.g. "/", "//", "\\")
        return ""
    last_sep = max(stripped.rfind("/"), stripped.rfind("\\"))
    return stripped[last_sep + 1 :] if last_sep >= 0 else stripped


def _unwrap_entry(data: dict[str, Any]) -> dict[str, Any]:
    """Return an envd EntryInfo from a flat object or a ``result``/``entry`` wrapper."""
    current = data
    result = current.get("result")
    if isinstance(result, dict):
        current = result
    entry = current.get("entry")
    if isinstance(entry, dict):
        return entry
    return current


def _is_directory(data: dict[str, Any]) -> bool:
    """True for ``isDir``, ``directory``, or envd's protobuf directory type (2)."""
    if data.get("isDir"):
        return True
    raw = data.get("type")
    if isinstance(raw, bool) or raw is None:
        return False
    if isinstance(raw, int):
        return raw == 2
    if isinstance(raw, str):
        return raw.strip() in {"2", "directory", "FILE_TYPE_DIRECTORY", "dir"}
    return False


def _parse_file_info(data: dict[str, Any]) -> FileInfo:
    """Parse a file info dict from the API response.

    * **name**: prefers an explicit non-empty ``name`` from the server;
      falls back to the last path segment of ``path``.
    * **type**: DIRECTORY when ``isDir`` is truthy, ``type`` is ``directory``
      (or the envd enum ``2`` / ``FILE_TYPE_DIRECTORY``), otherwise FILE.
    * **size**: numeric strings from protobuf JSON are coerced to ``int``.
    """
    file_type = FileType.DIRECTORY if _is_directory(data) else FileType.FILE

    name = data.get("name") or ""
    if not name:
        name = _name_from_path(data.get("path", ""))

    size = data.get("size", 0)
    if isinstance(size, str) and size.strip().lstrip("-").isdigit():
        size = int(size.strip())

    return FileInfo(
        name=name,
        path=data.get("path", ""),
        type=file_type,
        size=size,
    )


def _raise_transfer_timeout(
    exc: httpx.TimeoutException, verb: str, path: str, size: int
) -> NoReturn:
    """A transfer outlived the HTTP timeout; name the operation, the size and the knob."""
    sized = f" ({size} bytes)" if size >= 0 else ""
    raise FileOperationError(
        f"{verb} {path}{sized} timed out; the transfer took longer than the HTTP timeout.",
        suggestion=(
            "Raise the HTTP timeout (ABX_HTTP_TIMEOUT / http_timeout) or transfer smaller chunks."
        ),
    ) from exc


def _raise_file_error(exc: httpx.HTTPStatusError, path: str) -> NoReturn:
    """Translate an envd HTTP error into the SDK's filesystem errors (no URL in the text)."""
    status = exc.response.status_code
    if status == 404:
        raise FileNotFoundError_(f"File or directory not found in the sandbox: {path}") from exc
    if status == 403:
        raise PermissionDeniedError(f"Permission denied in the sandbox: {path}") from exc
    detail = exc.response.text.strip()[:200]
    message = f"envd file operation failed (HTTP {status}) for {path}"
    raise FileOperationError(f"{message}: {detail}" if detail else message) from exc


def _parse_watch_event(frame: dict[str, Any]) -> WatchEvent:
    """Parse a streaming watch event frame."""
    data = frame.get("result", frame)
    filesystem = data.get("filesystem") if isinstance(data.get("filesystem"), dict) else None
    if filesystem is not None:
        raw = str(filesystem.get("type") or "")
        mapped = {
            "EVENT_TYPE_CREATE": WatchEventType.CREATED,
            "EVENT_TYPE_WRITE": WatchEventType.MODIFIED,
            "EVENT_TYPE_REMOVE": WatchEventType.DELETED,
            "EVENT_TYPE_RENAME": WatchEventType.RENAMED,
            "EVENT_TYPE_CHMOD": WatchEventType.MODIFIED,
        }.get(raw, WatchEventType.MODIFIED)
        return WatchEvent(type=mapped, path=str(filesystem.get("name") or ""))
    event_type_str = data.get("type", data.get("eventType", "modified"))

    type_map = {
        "created": WatchEventType.CREATED,
        "modified": WatchEventType.MODIFIED,
        "deleted": WatchEventType.DELETED,
        "renamed": WatchEventType.RENAMED,
        "create": WatchEventType.CREATED,
        "modify": WatchEventType.MODIFIED,
        "delete": WatchEventType.DELETED,
        "rename": WatchEventType.RENAMED,
    }
    event_type = type_map.get(event_type_str, WatchEventType.MODIFIED)

    return WatchEvent(
        type=event_type,
        path=data.get("path", ""),
        old_path=data.get("oldPath"),
    )


class FilesystemProtocol:
    """Typed wrapper for envd filesystem operations (Connect protocol + HTTP file API).

    Connect RPC 用于目录操作；HTTP API 用于文件上传/下载（已实测验证）。
    """

    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client

    async def _rpc(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        rpc_path: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Unary envd call; HTTP errors become SDK filesystem errors for *path*."""
        try:
            return await self._http.envd_request(
                envd_url,
                rpc_path,
                payload=payload if payload is not None else {"path": path},
                envd_token=envd_token,
            )
        except httpx.HTTPStatusError as exc:
            _raise_file_error(exc, path)

    # --- Connect RPC methods（已实测验证）---

    async def stat(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
    ) -> FileInfo:
        """Get info about a file or directory.

        POST envd_url + /filesystem.Filesystem/Stat（已实测验证）
        """
        response = await self._rpc(envd_url, envd_token, _STAT, path)
        return _parse_file_info(_unwrap_entry(response))

    async def list_dir(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str = "/",
    ) -> list[FileInfo]:
        """List directory contents.

        POST envd_url + /filesystem.Filesystem/ListDir（已实测验证）
        """
        response = await self._rpc(envd_url, envd_token, _LIST_DIR, path)

        entries = response.get("entries", response.get("result", {}).get("entries", []))
        if not entries:
            # envd answers HTTP 200 with no entries for a missing path; Stat tells the cases
            # apart (raises FileNotFoundError_ when the path does not exist).
            await self.stat(envd_url, envd_token, path=path)
        return [_parse_file_info(_unwrap_entry(entry)) for entry in entries]

    async def make_dir(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
    ) -> None:
        """Create a directory (and parents).

        POST envd_url + /filesystem.Filesystem/MakeDir（已实测验证）
        """
        await self._rpc(envd_url, envd_token, _MAKE_DIR, path)

    async def remove(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
    ) -> None:
        """Remove a file or directory.

        POST envd_url + /filesystem.Filesystem/Remove（已实测验证）
        """
        await self._rpc(envd_url, envd_token, _REMOVE, path)

    async def move(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        source: str,
        destination: str,
    ) -> None:
        """Move/rename a file or directory.

        POST envd_url + /filesystem.Filesystem/Move（已实测验证）
        """
        await self._rpc(
            envd_url,
            envd_token,
            _MOVE,
            source,
            payload={"source": source, "destination": destination},
        )

    async def watch_dir(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
    ) -> StreamReader[WatchEvent]:
        """Watch a directory for changes (streaming).

        POST envd_url + /filesystem.Filesystem/WatchDir (Connect streaming, 已实测验证)
        """
        raw_stream = self._http.envd_stream(
            envd_url,
            _WATCH_DIR,
            payload={"path": path},
            envd_token=envd_token,
        )
        return StreamReader(raw_stream, _parse_watch_event)

    # --- HTTP file API（非 Connect RPC，已实测验证）---

    async def upload_file(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        content: bytes,
        username: str = "user",
    ) -> None:
        """Upload a file via HTTP multipart POST.

        POST envd_url/files?path={path}&username=user → 201（已实测验证）
        """
        try:
            await self._http.envd_http_request(
                envd_url,
                "POST",
                "/files",
                envd_token=envd_token,
                params={"path": path, "username": username},
                files={"file": ("file", content)},
            )
        except httpx.TimeoutException as exc:
            _raise_transfer_timeout(exc, "Upload", path, len(content))
        except httpx.HTTPStatusError as exc:
            _raise_file_error(exc, path)

    async def download_file(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        username: str = "user",
        max_bytes: int | None = None,
    ) -> bytes:
        """Download a file via HTTP GET.

        GET envd_url/files?path={path}&username=user → 200（已实测验证）
        """
        limits: dict[str, Any] = {}
        if max_bytes is not None:
            limits["max_response_bytes"] = max_bytes
        try:
            response = await self._http.envd_http_request(
                envd_url,
                "GET",
                "/files",
                envd_token=envd_token,
                params={"path": path, "username": username},
                **limits,
            )
        except httpx.TimeoutException as exc:
            _raise_transfer_timeout(exc, "Download", path, -1)
        except httpx.HTTPStatusError as exc:
            _raise_file_error(exc, path)
        return response.content

    # --- convenience wrappers ---

    async def exists(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
    ) -> bool:
        """Check if a file or directory exists (via Stat)."""
        try:
            await self.stat(envd_url, envd_token, path=path)
            return True
        except Exception:
            return False

    async def get_info(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
    ) -> FileInfo:
        """Alias for stat(). Kept for backward compatibility."""
        return await self.stat(envd_url, envd_token, path=path)

    async def read(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        max_bytes: int | None = None,
    ) -> bytes:
        """Read file content via HTTP download API."""
        if max_bytes is None:
            return await self.download_file(envd_url, envd_token, path=path)
        return await self.download_file(envd_url, envd_token, path=path, max_bytes=max_bytes)

    async def read_text(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        encoding: str = "utf-8",
    ) -> str:
        """Read file content as text."""
        raw = await self.read(envd_url, envd_token, path=path)
        return raw.decode(encoding)

    async def write(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        content: str | bytes,
    ) -> None:
        """Write content to a file via HTTP upload API."""
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        await self.upload_file(envd_url, envd_token, path=path, content=raw_bytes)

    async def rename(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        old_path: str,
        new_path: str,
    ) -> None:
        """Deprecated: use move(). Kept for backward compatibility."""
        await self.move(envd_url, envd_token, source=old_path, destination=new_path)
