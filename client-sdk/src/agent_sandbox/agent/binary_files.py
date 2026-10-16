"""Bounded binary MCP transfers over the SDK's existing sandbox file API."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_sandbox.agent.mcp import SandboxManager

MAX_FILE_BYTES = 1024 * 1024
MAX_BASE64_CHARS = 4 * ((MAX_FILE_BYTES + 2) // 3)


class BinaryFileInputError(ValueError):
    """A static validation error with no caller-supplied values."""


def _arguments(params: dict[str, Any], *, upload: bool) -> tuple[str, str | None]:
    allowed = {"path", "sandbox_id"} | ({"content_base64"} if upload else set())
    if set(params) - allowed:
        raise BinaryFileInputError("Unknown binary transfer argument.")
    path = params.get("path")
    try:
        path_size = len(path.encode("utf-8")) if isinstance(path, str) else 0
    except UnicodeError:
        raise BinaryFileInputError("path must contain valid UTF-8 characters.") from None
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or "\0" in path
        or ".." in path.split("/")
        or path_size > 4096
    ):
        raise BinaryFileInputError(
            "path must be an absolute sandbox path of at most 4096 UTF-8 bytes, "
            "without NUL or parent traversal."
        )
    sandbox_id = params.get("sandbox_id")
    if "sandbox_id" in params and (
        not isinstance(sandbox_id, str) or not sandbox_id.strip() or len(sandbox_id) > 1024
    ):
        raise BinaryFileInputError(
            "sandbox_id must be a nonempty string of at most 1024 characters."
        )
    return path, sandbox_id


async def upload_file(params: dict[str, Any], manager: SandboxManager) -> dict[str, Any]:
    """Decode one bounded Base64 payload and write bytes to the selected sandbox."""
    path, sandbox_id = _arguments(params, upload=True)
    encoded = params.get("content_base64")
    if not isinstance(encoded, str) or len(encoded) > MAX_BASE64_CHARS:
        raise BinaryFileInputError("content_base64 must encode at most 1048576 bytes.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise BinaryFileInputError("content_base64 must use strict standard Base64.") from None
    if len(data) > MAX_FILE_BYTES:
        raise BinaryFileInputError("content_base64 must encode at most 1048576 bytes.")
    sandbox = await manager.get_sandbox(sandbox_id)
    await asyncio.wait_for(sandbox.files.write(path, data), timeout=120)
    return {"success": True, "bytes_written": len(data), "sha256": hashlib.sha256(data).hexdigest()}


async def download_file(params: dict[str, Any], manager: SandboxManager) -> dict[str, Any]:
    """Download at most 1 MiB; never expose a partial or host-local file."""
    path, sandbox_id = _arguments(params, upload=False)
    sandbox = await manager.get_sandbox(sandbox_id)
    data = await asyncio.wait_for(
        sandbox.files.read_bytes(path, max_bytes=MAX_FILE_BYTES), timeout=120
    )
    if len(data) > MAX_FILE_BYTES:
        from agent_sandbox.models.errors import FileSizeLimitError

        raise FileSizeLimitError(MAX_FILE_BYTES)
    return {
        "content_base64": base64.b64encode(data).decode("ascii"),
        "bytes_read": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def format_error(exc: BaseException) -> dict[str, Any]:
    """Return a stable category without upstream exception text or file contents."""
    import httpx

    from agent_sandbox.models.errors import (
        FileNotFoundError_,
        FileSizeLimitError,
        PermissionDeniedError,
        ProviderFeatureNotSupportedError,
        SandboxNotFoundError,
    )

    if isinstance(exc, BinaryFileInputError):
        return {"error": str(exc), "error_category": "invalid_input"}
    category = "file_transfer"
    if isinstance(exc, FileSizeLimitError):
        category = "size_limit"
    elif isinstance(exc, FileNotFoundError_):
        category = "not_found"
    elif isinstance(exc, PermissionDeniedError):
        category = "permission_denied"
    elif isinstance(exc, SandboxNotFoundError):
        category = "sandbox_not_found"
    elif isinstance(exc, ProviderFeatureNotSupportedError):
        category = "unsupported"
    elif isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        category = "timeout"
    return {"error": "Binary file transfer failed.", "error_category": category}
