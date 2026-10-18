"""Structural protocol contracts. Core never constructs a backend wire implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import builtins
    from collections.abc import AsyncIterator, Callable

    from agent_sandbox.models.filesystem import FileInfo, WatchEvent
    from agent_sandbox.models.process import ProcessChunk, ProcessInfo
    from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo, SandboxStatus
    from agent_sandbox.transport.auth_contract import DataPlaneAuth as EnvdTokenManager
    from agent_sandbox.transport.config import TransportConfig
    from agent_sandbox.transport.streaming import StreamReader


class SandboxProtocol(Protocol):
    async def create(
        self, config: SandboxConfig, *, request_timeout: float | None = None
    ) -> SandboxInfo: ...

    async def list(
        self, *, status: SandboxStatus | None = None, limit: int = 100, offset: int = 0
    ) -> builtins.list[SandboxInfo]: ...

    async def list_v2(
        self, *, status: SandboxStatus | None = None, limit: int = 100, offset: int = 0
    ) -> builtins.list[SandboxInfo]: ...

    async def get_info(self, sandbox_id: str) -> SandboxInfo: ...

    async def kill(self, sandbox_id: str) -> None: ...

    async def set_timeout(self, sandbox_id: str, timeout: int) -> None: ...

    async def connect(self, sandbox_id: str) -> SandboxInfo: ...

    async def is_running(self, sandbox_id: str) -> bool: ...

    async def pause(self, sandbox_id: str) -> None: ...

    async def resume(self, sandbox_id: str) -> None: ...


class ProcessProtocol(Protocol):
    async def start(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        cmd: str,
        args: builtins.list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str = "",
        timeout: int = 60,
        user: str = "",
    ) -> StreamReader[ProcessChunk]: ...

    async def list_processes(
        self, envd_url: str, envd_token: EnvdTokenManager
    ) -> builtins.list[ProcessInfo]: ...

    async def connect_to_process(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str
    ) -> StreamReader[ProcessChunk]: ...

    async def update(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, **kwargs: Any
    ) -> dict[str, Any]: ...

    async def send_input(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, data: str
    ) -> None: ...

    async def send_signal(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        pid: int | str,
        signal: int = 15,
        request_timeout: float | None = None,
    ) -> None: ...

    async def send_stdin(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str, data: str
    ) -> None: ...

    async def kill(
        self, envd_url: str, envd_token: EnvdTokenManager, *, pid: int | str
    ) -> None: ...


class FilesystemProtocol(Protocol):
    async def stat(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> FileInfo: ...

    async def list_dir(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str = "/"
    ) -> builtins.list[FileInfo]: ...

    async def make_dir(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> None: ...

    async def remove(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> None: ...

    async def move(
        self, envd_url: str, envd_token: EnvdTokenManager, *, source: str, destination: str
    ) -> None: ...

    async def watch_dir(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str
    ) -> StreamReader[WatchEvent]: ...

    async def upload_file(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        content: bytes,
        username: str = "user",
    ) -> None: ...

    async def download_file(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        username: str = "user",
        max_bytes: int | None = None,
    ) -> bytes: ...

    async def exists(self, envd_url: str, envd_token: EnvdTokenManager, *, path: str) -> bool: ...

    async def get_info(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str
    ) -> FileInfo: ...

    async def read(
        self,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        path: str,
        max_bytes: int | None = None,
    ) -> bytes: ...

    async def read_text(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str, encoding: str = "utf-8"
    ) -> str: ...

    async def write(
        self, envd_url: str, envd_token: EnvdTokenManager, *, path: str, content: str | bytes
    ) -> None: ...

    async def rename(
        self, envd_url: str, envd_token: EnvdTokenManager, *, old_path: str, new_path: str
    ) -> None: ...


class CodeInterpreterProtocol(Protocol):
    async def run_code(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        code: str,
        language: str = "python",
        context_id: str | None = None,
        timeout: int = 30,
        envs: dict[str, str] | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[..., None] | None = None,
    ) -> dict[str, Any]: ...

    async def create_context(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        language: str = "python",
    ) -> dict[str, Any]: ...

    async def list_contexts(
        self, sandbox_id: str, envd_url: str, envd_token: EnvdTokenManager
    ) -> builtins.list[dict[str, Any]]: ...

    async def restart_context(
        self, sandbox_id: str, envd_url: str, envd_token: EnvdTokenManager, *, context_id: str
    ) -> dict[str, Any]: ...

    async def remove_context(
        self, sandbox_id: str, envd_url: str, envd_token: EnvdTokenManager, *, context_id: str
    ) -> None: ...


class TerminalSession(Protocol):
    @classmethod
    async def create(
        cls,
        envd_url: str,
        envd_token: EnvdTokenManager,
        config: TransportConfig,
        *,
        cols: int = 80,
        rows: int = 24,
        shell: str = "/bin/bash",
    ) -> TerminalSession: ...

    async def send(self, data: str) -> None: ...

    async def send_bytes(self, data: bytes) -> None: ...

    async def receive(self, timeout: float | None = None) -> str | bytes: ...

    async def output_stream(self) -> AsyncIterator[str | bytes]: ...

    async def resize(self, cols: int, rows: int) -> None: ...

    @property
    def is_connected(self) -> bool: ...

    async def close(self) -> None: ...
