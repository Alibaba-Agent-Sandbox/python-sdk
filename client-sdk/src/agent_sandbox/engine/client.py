"""SDK client for the local provider engine."""

from __future__ import annotations

import asyncio
import os
import stat
import subprocess  # nosec B404 - fixed local Python module launcher, no shell
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import grpc
import grpc.aio

from agent_sandbox.engine import engine_pb2 as pb2
from agent_sandbox.engine import engine_pb2_grpc as pb2_grpc
from agent_sandbox.engine.rpcutil import reraise
from agent_sandbox.engine.server import ProviderEngine
from agent_sandbox.models.sandbox import SandboxInfo, SandboxStatus, validate_volume_mounts

_pb2: Any = pb2
_grpc_mod: Any = pb2_grpc
_grpc: Any = grpc

_lock = threading.Lock()
_bound: set[str] = set()


def socket_path() -> Path:
    """Unix socket the engine listens on.

    pytest gets a per-process socket so a live engine from another run cannot
    swallow the mocked HTTP client.
    """
    override = os.environ.get("ABX_ENGINE_SOCKET")
    if override:
        return Path(override)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Test-only Unix socket; _harden applies owner-only permissions after binding.
        return Path(f"/tmp/abx-pytest-{os.getpid()}.sock")  # nosec B108
    return Path.home() / ".abx" / "engine.sock"


def _target(path: Path | None = None) -> str:
    return f"unix://{path or socket_path()}"


def _inprocess() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ABX_ENGINE_INPROCESS"))


def _health_ok(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with _grpc.insecure_channel(_target(path)) as channel:
            status = _grpc_mod.ProviderEngineStub(channel).Health(_pb2.Empty(), timeout=0.3)
        return status.protocol == "abx.engine.v1"
    except Exception:
        return False


def _harden(path: Path, *, created_parent: bool) -> None:
    """Owner-only socket. The default directory is owner-only too."""
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    parent = path.parent
    if created_parent or parent == Path.home() / ".abx":
        os.chmod(parent, stat.S_IRWXU)


def ensure_engine() -> None:
    """Attach to a live engine, or start one. A live socket is never replaced."""
    path = socket_path()
    raw = os.fspath(path)
    if len(raw.encode()) > 104:
        raise RuntimeError(f"engine socket path is longer than 104 bytes: {raw}")
    if ":" in path.name:
        raise RuntimeError("engine socket must be a filesystem path, not host:port")
    key = str(path)
    if _health_ok(path):
        _harden(path, created_parent=False)
        with _lock:
            _bound.add(key)
        return
    with _lock:
        if key in _bound and _health_ok(path):
            return
        if _health_ok(path):
            _bound.add(key)
            return
        created_parent = not path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        if _inprocess():
            _start_thread(path)
        else:
            _spawn(path)
        _harden(path, created_parent=created_parent)
        _bound.add(key)


def _start_thread(path: Path) -> None:
    ready = threading.Event()
    error: list[BaseException] = []

    def _run() -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            server = loop.run_until_complete(_serve(path))
            ready.set()
            loop.run_forever()
            del server
        except BaseException as exc:  # pragma: no cover - thread boundary
            error.append(exc)
            ready.set()

    threading.Thread(target=_run, name="abx-engine", daemon=True).start()
    if not ready.wait(10):
        raise RuntimeError("provider engine did not start")
    if error:
        raise RuntimeError(str(error[0])) from error[0]


def _spawn(path: Path) -> None:
    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE")
        if key in os.environ
    }
    env["ABX_ENGINE_SOCKET"] = str(path)
    env["ABX_ENGINE_PARENT"] = "1"
    # Fixed local module argv and a constrained environment; no shell interpretation.
    subprocess.Popen(  # noqa: S603  # nosec B603 - fixed Python module argv, no shell
        [sys.executable, "-m", "agent_sandbox.engine"],
        env=env,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(50):
        if _health_ok(path):
            return
        threading.Event().wait(0.1)
    raise RuntimeError("provider engine did not become healthy")


async def _serve(path: Path) -> Any:
    server = _grpc.aio.server()
    _grpc_mod.add_ProviderEngineServicer_to_server(ProviderEngine(), server)
    bound = server.add_insecure_port(f"unix://{path}")
    if bound == 0:
        raise RuntimeError(f"provider engine failed to bind {path}")
    await server.start()
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return server


def _channel() -> Any:
    ensure_engine()
    return _grpc.aio.insecure_channel(_target())


def _state(message: Any) -> SandboxInfo:
    status = message.status or SandboxStatus.RUNNING.value
    return SandboxInfo(
        sandbox_id=message.sandbox_id,
        template=message.template,
        status=status,
        envd_url=message.envd_url or None,
        envd_access_token=message.envd_access_token or None,
        envd_version=message.envd_version or None,
    )


class Engine:
    """Python client of the provider engine."""

    async def create(
        self,
        template: str = "base",
        *,
        timeout: int = 300,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        region: str | None = None,
        request_timeout: float | None = None,
        cpu: int | None = None,
        memory: int | None = None,
        disk: int | None = None,
        gpu: str | None = None,
        provider: str | None = None,
        volume_mounts: dict[str, str] | None = None,
    ) -> SandboxInfo:
        """Create a sandbox. The engine performs the platform HTTP call."""
        mounts = validate_volume_mounts(volume_mounts)
        if mounts and provider not in {None, "", "alicloud-express"}:
            from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

            raise ProviderFeatureNotSupportedError(provider, "volume_mounts")
        request = _pb2.CreateRequest(
            template=template,
            timeout=timeout,
            metadata=metadata or {},
            envs=envs or {},
            api_key=api_key or "",
            api_url=api_url or "",
            access_key_id=access_key_id or "",
            access_key_secret=access_key_secret or "",
            region=region or "",
            request_timeout=request_timeout or 0,
            cpu=cpu or 0,
            memory=memory or 0,
            disk=disk or 0,
            gpu=gpu or "",
            provider=provider or "",
            **({"volume_mounts": mounts} if mounts else {}),
        )
        try:
            async with _channel() as channel:
                stub = _grpc_mod.ProviderEngineStub(channel)
                if mounts:
                    health = await stub.Health(_pb2.Empty(), timeout=5.0)
                    if "volume_mounts" not in getattr(health, "supported_create_options", ()):
                        from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

                        raise ProviderFeatureNotSupportedError(
                            "alicloud-express",
                            "volume_mounts",
                            message="The running Python engine does not support volume_mounts.",
                            suggestion="Upgrade and restart the local Python provider engine.",
                        )
                state = await stub.Create(request)
        except grpc.aio.AioRpcError as exc:
            reraise(exc)
        return _state(state)

    async def op(
        self,
        op: str,
        *,
        sandbox_id: str,
        provider: str = "",
        api_key: str = "",
        api_url: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Unary helper (release, pause, port URL, process signal)."""
        import json

        request = _pb2.OpRequest(
            op=op,
            sandbox_id=sandbox_id,
            provider=provider,
            api_key=api_key,
            api_url=api_url,
            json=json.dumps(payload or {}),
        )
        try:
            async with _channel() as channel:
                result = await _grpc_mod.ProviderEngineStub(channel).Op(request)
        except grpc.aio.AioRpcError as exc:
            reraise(exc)
        return json.loads(result.json or "{}")

    async def exec_start(
        self,
        sandbox_id: str,
        *,
        cmd: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str = "",
        user: str = "",
        timeout: int = 60,
    ) -> AsyncIterator[Any]:
        """Run a command. The engine owns the SSE or Connect stream."""
        request = _pb2.ExecStartRequest(
            sandbox_id=sandbox_id,
            cmd=cmd,
            args=args or [],
            env=env or {},
            cwd=cwd,
            user=user,
            timeout=timeout,
        )
        channel = _channel()
        try:
            call = _grpc_mod.ProviderEngineStub(channel).ExecStart(request)
            async for event in call:
                yield event
        except grpc.aio.AioRpcError as exc:
            reraise(exc)
        finally:
            await channel.close()

    async def file_read(self, sandbox_id: str, path: str) -> bytes:
        """Read a file in 64 KiB chunks. Bytes are not base64."""
        channel = _channel()
        parts: list[bytes] = []
        try:
            call = _grpc_mod.ProviderEngineStub(channel).FileRead(
                _pb2.FilePath(sandbox_id=sandbox_id, path=path)
            )
            async for chunk in call:
                parts.append(bytes(chunk.data))
        except grpc.aio.AioRpcError as exc:
            reraise(exc)
        finally:
            await channel.close()
        return b"".join(parts)

    async def file_write(self, sandbox_id: str, path: str, content: bytes) -> None:
        """Write a file. The first frame carries the path; later frames are bytes."""

        async def outgoing() -> AsyncIterator[Any]:
            step = 65536
            if not content:
                yield _pb2.FileChunk(sandbox_id=sandbox_id, path=path, data=b"", eof=True)
                return
            for index in range(0, len(content), step):
                piece = content[index : index + step]
                yield _pb2.FileChunk(
                    sandbox_id=sandbox_id,
                    path=path if index == 0 else "",
                    data=piece,
                    eof=index + step >= len(content),
                )

        try:
            async with _channel() as channel:
                await _grpc_mod.ProviderEngineStub(channel).FileWrite(outgoing())
        except grpc.aio.AioRpcError as exc:
            reraise(exc)

    async def file_op(
        self, sandbox_id: str, op: str, path: str, destination: str = ""
    ) -> list[dict[str, Any]]:
        """stat, list, mkdir, remove, or move."""
        request = _pb2.FileOpRequest(
            sandbox_id=sandbox_id, op=op, path=path, destination=destination
        )
        try:
            async with _channel() as channel:
                result = await _grpc_mod.ProviderEngineStub(channel).FileOp(request)
        except grpc.aio.AioRpcError as exc:
            reraise(exc)
        return [
            {"name": row.name, "path": row.path, "type": row.type, "size": int(row.size)}
            for row in result.entries
        ]

    async def exec_sse(self, sse_url: str) -> AsyncIterator[str]:
        """Read an SSE URL from inside the engine and yield each data line."""
        async with _channel() as channel:
            call = _grpc_mod.ProviderEngineStub(channel).Exec(_pb2.ExecRequest(sse_url=sse_url))
            async for chunk in call:
                yield str(chunk.data)

    async def terminal(self, websocket_url: str, payload: bytes) -> bytes:
        """Send one payload over the engine's WebSocket and return the first reply."""

        async def outgoing() -> AsyncIterator[Any]:
            yield _pb2.TerminalFrame(websocket_url=websocket_url, data=payload)

        async with _channel() as channel:
            call = _grpc_mod.ProviderEngineStub(channel).Terminal(outgoing())
            frame = None
            async for item in call:
                frame = item
                break
        if frame is None:
            raise RuntimeError("terminal stream ended without a frame")
        return bytes(frame.data)
