"""Reconnectable MCP tasks backed by sandbox-owned, bounded records."""

from __future__ import annotations

import json
import os
import re
import shlex
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_sandbox.agent.tools import _ToolInputError

if TYPE_CHECKING:
    from agent_sandbox.agent.mcp import SandboxManager

_RUNTIME = Path(__file__).with_name("task_runtime.py").read_text(encoding="utf-8")


def _required(params: dict[str, Any], name: str, maximum: int = 4096) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise _ToolInputError(f"{name} must be a non-empty bounded string")
    return value


def _validate(params: dict[str, Any], allowed: set[str]) -> None:
    if set(params) - allowed:
        raise _ToolInputError("Unsupported task argument")


def _integer(params: dict[str, Any], name: str, default: int, maximum: int) -> int:
    value = params.get(name, default)
    if type(value) is not int or not 0 <= value <= maximum:
        raise _ToolInputError(f"{name} must be an integer in 0..{maximum}")
    return value


def _redact(text: str, manager: SandboxManager) -> str:
    secrets = {manager._api_key or ""}
    secrets.update(
        value
        for name, value in os.environ.items()
        if any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
    )
    for value in sorted(secrets, key=len, reverse=True):
        if len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    return text


def _command(request: dict[str, Any]) -> str:
    command = "python3 -c " + shlex.quote(_RUNTIME) + " " + shlex.quote(json.dumps(request))
    # Linux's per-argument bound applies after JSON/quoting expansion. Leave
    # headroom below 128 KiB, including the copied supervisor program.
    if len(command.encode("utf-8")) > 96 * 1024:
        raise _ToolInputError("Encoded task request exceeds the 96 KiB command limit")
    return command


async def _operate(
    sandbox: Any, request: dict[str, Any], manager: SandboxManager
) -> dict[str, Any]:
    command = _command(request)
    result = await sandbox.commands.run(command, timeout=10)
    if result.exit_code != 0:
        raise RuntimeError("Task operation failed")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("Invalid task response") from None
    if not isinstance(payload, dict) or "error" in payload:
        raise RuntimeError("Task operation failed")
    if payload.get("task_id") != request["task_id"] or payload.get("state") not in {
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "timed_out",
        "unknown",
    }:
        raise RuntimeError("Invalid task response")
    allowed = {
        "task_id",
        "state",
        "exit_code",
        "started_at",
        "finished_at",
        "stdout",
        "stderr",
        "stdout_offset",
        "stderr_offset",
        "stdout_size",
        "stderr_size",
        "stdout_truncated",
        "stderr_truncated",
    }
    payload = {k: v for k, v in payload.items() if k in allowed}
    for name in ("stdout", "stderr"):
        if name in payload:
            if not isinstance(payload[name], str) or len(payload[name]) > 65536:
                raise RuntimeError("Invalid task output")
            payload[name] = _redact(payload[name], manager)
    return payload


async def start_task(params: dict[str, Any], manager: SandboxManager) -> dict[str, Any]:
    """Start explicit background work and preserve its sandbox until platform TTL."""
    _validate(params, {"command", "sandbox_id", "cwd", "timeout"})
    command = _required(params, "command", 65536)
    timeout = _integer(params, "timeout", 300, 3600)
    if timeout == 0:
        raise _ToolInputError("timeout must be an integer in 1..3600")
    sandbox_id = _required(params, "sandbox_id") if "sandbox_id" in params else None
    cwd = _required(params, "cwd") if "cwd" in params else ""
    task_id = uuid.uuid4().hex
    request = {
        "action": "start",
        "task_id": task_id,
        "command": command,
        "cwd": cwd,
        "timeout": timeout,
        "runtime": _RUNTIME,
    }
    _command(request)  # Validate expansion before even connecting to a sandbox.
    async with manager._state_lock:
        manager._require_open()
        temporary = sandbox_id is not None and manager._cached_sandbox(sandbox_id) is None
    if temporary:
        from agent_sandbox.api.sandbox import Sandbox

        sandbox = await Sandbox.connect(**manager._connect_kwargs(sandbox_id=sandbox_id))
    else:
        sandbox = await manager.get_sandbox(
            sandbox_id, refresh_lifetime=False, create_default=False
        )
    try:
        async with manager._state_lock:
            manager._require_open()
        try:
            result = await _operate(sandbox, request, manager)
        except _ToolInputError:
            raise
        except Exception:
            # Submission may have reached the sandbox before a transport error.
            # Return the actual chosen handle so callers can inspect or destroy
            # the sandbox; never blindly submit the command a second time.
            result = {
                "task_id": task_id,
                "state": "unknown",
                "error": "Task submission unconfirmed. Inspect the handle or destroy its sandbox.",
            }
        # Retention applies only to a sandbox already owned by this manager.
        # Qualified provider IDs can connect to a sandbox already owned under
        # its canonical SDK ID. Retain that original owner, not the temporary
        # connection, so disconnect cannot destroy accepted background work.
        owned = manager._sandboxes.get(manager._sandbox_key(sandbox))
        retained = await manager.retain_task_sandbox(owned) if owned is not None else temporary
        return {
            **result,
            "sandbox_id": manager._sandbox_key(sandbox),
            "retained_until_sandbox_ttl": retained,
        }
    finally:
        if temporary:
            await sandbox.close()


async def task_operation(
    params: dict[str, Any], manager: SandboxManager, *, cancel: bool = False
) -> dict[str, Any]:
    """Read/cancel only an opaque task handle, without adopting its sandbox."""
    _validate(params, {"task_id", "sandbox_id", "stdout_offset", "stderr_offset", "limit"})
    sandbox_id = _required(params, "sandbox_id")
    task_id = _required(params, "task_id", 32)
    if re.fullmatch(r"[0-9a-f]{32}", task_id) is None:
        raise _ToolInputError("task_id must contain exactly 32 lowercase hexadecimal characters")
    request = {
        "action": "cancel" if cancel else "get",
        "task_id": task_id,
        "stdout_offset": _integer(params, "stdout_offset", 0, 1024 * 1024),
        "stderr_offset": _integer(params, "stderr_offset", 0, 1024 * 1024),
        "limit": _integer(params, "limit", 16384, 65536),
    }
    if request["limit"] == 0:
        raise _ToolInputError("limit must be an integer in 1..65536")
    from agent_sandbox.api.sandbox import Sandbox

    sandbox = await Sandbox.connect(**manager._connect_kwargs(sandbox_id=sandbox_id))
    try:
        result = await _operate(sandbox, request, manager)
        return {**result, "sandbox_id": sandbox_id}
    finally:
        await sandbox.close()
