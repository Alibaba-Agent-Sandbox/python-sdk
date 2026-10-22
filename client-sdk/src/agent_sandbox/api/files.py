"""Files module — filesystem operations in sandboxes."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from agent_sandbox.models.template import DEFAULT_CAPABILITIES
from agent_sandbox.utils.async_bridge import make_sync
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from agent_sandbox.models.filesystem import FileInfo, WatchEvent
    from agent_sandbox.protocol.contracts import FilesystemProtocol, SandboxProtocol
    from agent_sandbox.transport.auth_contract import DataPlaneAuth as EnvdTokenManager
    from agent_sandbox.transport.streaming import StreamReader

logger = get_logger("api.files")


class FilesModule:
    """High-level interface for filesystem operations in a sandbox.

    Wraps FilesystemProtocol and provides convenient file I/O methods
    including upload/download between local and sandbox filesystems.
    """

    def __init__(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        filesystem_protocol: FilesystemProtocol,
        sandbox_protocol: SandboxProtocol | None = None,
        sandbox_id: str | None = None,
        capabilities: set[str] | None = None,
        provider_id: str = "provider",
    ) -> None:
        self._envd_url = envd_url
        self._envd_token = envd_token
        self._fs = filesystem_protocol
        self._provider_id = provider_id
        self._sandbox_protocol = sandbox_protocol
        self._sandbox_id = sandbox_id
        self._capabilities = capabilities if capabilities is not None else set(DEFAULT_CAPABILITIES)

    async def read(self, path: str, *, encoding: str = "utf-8") -> str:
        """Read a file as text.

        Args:
            path: Absolute path in the sandbox.
            encoding: Text encoding (default: utf-8).

        Returns:
            File contents as string.
        """
        return await self._fs.read_text(
            self._envd_url,
            self._envd_token,
            path=path,
            encoding=encoding,
        )

    async def read_bytes(self, path: str, *, max_bytes: int | None = None) -> bytes:
        """Read a file as raw bytes.

        Args:
            path: Absolute path in the sandbox.
            max_bytes: Optional nonnegative streamed response limit. None preserves
                the existing unlimited read. Overflow raises FileSizeLimitError.

        Returns:
            File contents as bytes.
        """
        return await self._fs.read(
            self._envd_url,
            self._envd_token,
            path=path,
            **({"max_bytes": max_bytes} if max_bytes is not None else {}),
        )

    async def write(self, path: str, content: str | bytes) -> None:
        """Write content to a file in the sandbox.

        Args:
            path: Absolute path in the sandbox.
            content: String or bytes to write.
        """
        await self._fs.write(
            self._envd_url,
            self._envd_token,
            path=path,
            content=content,
        )

    async def list(self, path: str = "/") -> list[FileInfo]:
        """List directory contents.

        Args:
            path: Directory path (default: root).

        Returns:
            List of FileInfo entries.
        """
        return await self._fs.list_dir(
            self._envd_url,
            self._envd_token,
            path=path,
        )

    async def remove(self, path: str) -> None:
        """Remove a file or directory.

        Args:
            path: Absolute path in the sandbox.
        """
        await self._fs.remove(
            self._envd_url,
            self._envd_token,
            path=path,
        )

    async def exists(self, path: str) -> bool:
        """Check if a file or directory exists.

        Args:
            path: Absolute path in the sandbox.

        Returns:
            True if the path exists.
        """
        return await self._fs.exists(
            self._envd_url,
            self._envd_token,
            path=path,
        )

    async def make_dir(self, path: str) -> None:
        """Create a directory (including parents).

        Args:
            path: Directory path to create.
        """
        await self._fs.make_dir(
            self._envd_url,
            self._envd_token,
            path=path,
        )

    async def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to the sandbox.

        Reads the local file and writes its contents to the sandbox.

        Args:
            local_path: Path on the local filesystem.
            remote_path: Destination path in the sandbox.
        """
        data = pathlib.Path(local_path).read_bytes()
        await self.write(remote_path, data)
        logger.debug("Uploaded %s -> %s", local_path, remote_path)

    async def download(self, remote_path: str, local_path: str) -> None:
        """Download a file from the sandbox to local filesystem.

        Reads from the sandbox and writes to a local file.

        Args:
            remote_path: Path in the sandbox.
            local_path: Destination path on local filesystem.
        """
        data = await self.read_bytes(remote_path)
        pathlib.Path(local_path).write_bytes(data)
        logger.debug("Downloaded %s -> %s", remote_path, local_path)

    async def watch(self, path: str) -> StreamReader[WatchEvent]:
        """Watch a directory for filesystem changes.

        Args:
            path: Directory path to watch.

        Returns:
            StreamReader yielding WatchEvent items.
        """
        return await self._fs.watch_dir(
            self._envd_url,
            self._envd_token,
            path=path,
        )

    async def move(self, source: str, destination: str) -> None:
        """Move/rename a file or directory.

        Args:
            source: Current path.
            destination: New path.
        """
        await self._fs.move(
            self._envd_url,
            self._envd_token,
            source=source,
            destination=destination,
        )

    async def get_info(self, path: str) -> FileInfo:
        """Get info about a file or directory.

        Args:
            path: Absolute path in the sandbox.

        Returns:
            FileInfo with name, path, type, size.
        """
        return await self._fs.stat(
            self._envd_url,
            self._envd_token,
            path=path,
        )

    async def upload_url(self, path: str) -> str:
        """Ask the filesystem adapter for an upload URL and its access requirements."""
        return await self._transfer_url(path, "upload")

    async def download_url(self, path: str) -> str:
        """Ask the filesystem adapter for a download URL."""
        return await self._transfer_url(path, "download")

    async def _transfer_url(self, path: str, operation: str) -> str:
        from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

        resolver = getattr(self._fs, "transfer_url", None)
        if not callable(resolver):
            raise ProviderFeatureNotSupportedError(self._provider_id, "files.transfer")
        return str(await resolver(self._envd_url, self._envd_token, path=path, operation=operation))

    # Sync variants
    read_sync = make_sync(read)
    read_bytes_sync = make_sync(read_bytes)
    write_sync = make_sync(write)
    list_sync = make_sync(list)
    remove_sync = make_sync(remove)
    exists_sync = make_sync(exists)
    make_dir_sync = make_sync(make_dir)
    upload_sync = make_sync(upload)
    download_sync = make_sync(download)
    move_sync = make_sync(move)
    upload_url_sync = make_sync(upload_url)
    download_url_sync = make_sync(download_url)
