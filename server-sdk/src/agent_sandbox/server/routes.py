"""Built-in route handlers and dynamic route registry for the sandbox HTTP server.

Provides:
- Health check (``/health``)
- Command listing (``GET /commands``) and execution (``POST /commands/{name}``)
- File upload (``POST /upload``) and download (``GET /download``)
- Shell execution (``POST /shell``)

Which of them a caller may use is decided by the endpoint policy, not here.
"""

from __future__ import annotations

import base64
import os
import shlex
import subprocess
from typing import Any

from agent_sandbox.server._coerce import coerce_kwargs as _coerce_kwargs

from .guard import OP_READ, OP_WRITE
from .guards import check_command, check_env, check_process
from .policy import PolicyDenied
from .registry import CommandArg, CommandRegistry, default_registry  # noqa: F401
from .router import default_table
from .runtime import EndpointContext, context_of
from .types import ServerRequest, ServerResponse

__all__ = [
    "handle_health",
    "handle_list_commands",
    "handle_run_command",
    "handle_upload",
    "handle_download",
    "handle_shell",
]

# ---------------------------------------------------------------------------
# Upload / download size constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
_MAX_UPLOAD_ENV_VAR = "ABX_MAX_UPLOAD_SIZE"


def _max_upload_size() -> int:
    """Return the configured maximum upload size in bytes."""
    raw = os.environ.get(_MAX_UPLOAD_ENV_VAR, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _DEFAULT_MAX_UPLOAD_SIZE


# ---------------------------------------------------------------------------
# Route handlers — each returns ``(status_code, response_body_dict)``
# ---------------------------------------------------------------------------


def handle_health() -> tuple[int, dict[str, Any]]:
    """``GET /health`` — always 200."""
    return 200, {"status": "ok"}


def handle_list_commands(
    registry: CommandRegistry | None,
    ctx: EndpointContext,
) -> tuple[int, dict[str, Any]]:
    """``GET /commands`` — list all registered commands from the sandbox registry.

    Args:
        registry: The :class:`CommandRegistry` to query.  When ``None``,
            the module-level :func:`default_registry` is used.
        ctx: The request's policy context; commands whose scopes it lacks are hidden.
    """
    if registry is None:
        registry = default_registry()
    commands: list[dict[str, Any]] = []
    for name, cmd in registry.list_visible().items():
        if not all(ctx.identity.can(sc) for sc in cmd.scopes):
            continue
        args_list: list[dict[str, Any]] = []
        for arg in cmd.args:
            args_list.append(
                {
                    "name": arg.name,
                    "type": arg.type,
                    "required": arg.required,
                    "default": arg.default,
                    "description": arg.description,
                }
            )
        commands.append({"name": name, "args": args_list, "description": cmd.description})
    return 200, {"commands": commands}


# ---------------------------------------------------------------------------
# Coerce helper — implementation in agent_sandbox.server._coerce
# ---------------------------------------------------------------------------
# ``_coerce_kwargs`` is imported at the top of this module from
# ``agent_sandbox.server._coerce``.  The client SDK keeps a byte-identical copy
# in ``agent_sandbox.utils.coerce`` (the two distributions cannot import each
# other); the client test-suite asserts the copies stay in sync.


def handle_run_command(
    command_name: str,
    body: dict[str, Any],
    registry: CommandRegistry | None,
    ctx: EndpointContext,
) -> tuple[int, dict[str, Any]]:
    """``POST /commands/{name}`` — execute a registered command.

    Args:
        command_name: The registered command name extracted from the URL path.
        body: Parsed JSON body containing kwargs for the command.
        registry: The :class:`CommandRegistry` to look up commands from.
            When ``None``, the module-level :func:`default_registry` is used.

    Returns:
        ``(status_code, response_dict)``
    """
    if registry is None:
        registry = default_registry()
    # 1. Lookup
    cmd = registry.get(command_name)
    if cmd is None:
        all_cmds = registry.list_all()
        available = ", ".join(sorted(all_cmds)) or "(none)"
        return 404, {
            "error": f"Unknown command {command_name!r}; available: {available}",
            "type": "ValueError",
        }

    for scope in cmd.scopes:
        ctx.require_scope(scope)

    # 2. Coerce / validate kwargs
    try:
        coerced = _coerce_kwargs(cmd.args, body)
    except (ValueError, TypeError) as exc:
        return 400, {"error": str(exc), "type": type(exc).__name__}

    # 3. Execute the command function directly.
    try:
        result = cmd.fn(**coerced)
    except Exception as exc:
        return 500, {"error": str(exc), "type": type(exc).__name__}

    return 200, {"result": result}


def handle_upload(body: dict[str, Any], ctx: EndpointContext) -> tuple[int, dict[str, Any]]:
    """``POST /upload`` — write base64-encoded content to the local filesystem.

    Expected *body*::

        {"path": "/some/file.txt", "content_base64": "<base64>"}

    Returns:
        ``(status_code, response_dict)``
    """
    path = body.get("path")
    content_b64 = body.get("content_base64")
    if not path or not isinstance(path, str):
        return 400, {"error": "Missing or invalid 'path'", "type": "ValueError"}
    if not content_b64 or not isinstance(content_b64, str):
        return 400, {
            "error": "Missing or invalid 'content_base64'",
            "type": "ValueError",
        }

    try:
        data = base64.b64decode(content_b64, validate=True)
    except Exception as exc:
        return 400, {"error": f"Invalid base64: {exc}", "type": "ValueError"}

    # Enforce upload size limit (consistent with routes_files.py).
    max_size = int(ctx.limit("max_bytes", _max_upload_size()))
    if len(data) > max_size:
        return 413, {
            "error": f"File size {len(data)} exceeds limit {max_size}",
            "type": "ValueError",
            "code": "payload_too_large",
            "limit": max_size,
        }

    try:
        safe_path = ctx.resolve_path(path, OP_WRITE)
    except ValueError as exc:
        return 400, {"error": str(exc), "type": "ValueError"}

    try:
        from .routes_files import _extension_check, _write_checked

        os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
        _extension_check(ctx, safe_path)
        _write_checked(ctx, safe_path, data)
    except PolicyDenied:
        raise
    except Exception as exc:
        return 500, {"error": str(exc), "type": type(exc).__name__}

    return 200, {"path": safe_path, "bytes": len(data)}


def handle_download(path: str, ctx: EndpointContext) -> tuple[int, dict[str, Any]]:
    """``GET /download?path=...`` — read a file and return base64-encoded content.

    Args:
        path: Filesystem path to read.

    Returns:
        ``(status_code, response_dict)``
    """
    if not path:
        return 400, {"error": "Missing 'path' query parameter", "type": "ValueError"}

    try:
        safe_path = ctx.resolve_path(path, OP_READ)
    except ValueError as exc:
        return 400, {"error": str(exc), "type": "ValueError"}

    if not os.path.isfile(safe_path):
        return 404, {
            "error": f"File not found: {safe_path}",
            "type": "FileNotFoundError",
        }

    # Enforce download size limit.
    try:
        file_size = os.path.getsize(safe_path)
    except OSError as exc:
        return 500, {"error": str(exc), "type": type(exc).__name__}
    max_size = int(ctx.limit("max_bytes", _max_upload_size()))
    if file_size > max_size:
        return 413, {
            "error": f"File size {file_size} exceeds download limit {max_size}",
            "type": "ValueError",
            "code": "payload_too_large",
            "limit": max_size,
        }

    try:
        from .routes_files import _read_checked

        read_result = _read_checked(ctx, safe_path)
        if not isinstance(read_result, bytes):
            return read_result.status, read_result.body
        data = read_result
    except PolicyDenied:
        raise
    except Exception as exc:
        return 500, {"error": str(exc), "type": type(exc).__name__}

    return 200, {
        "path": safe_path,
        "content_base64": base64.b64encode(data).decode("ascii"),
    }


_DEFAULT_SHELL_TIMEOUT = 300.0


def enforce_exec_policy(
    ctx: EndpointContext,
    args: list[str],
    body: dict[str, Any],
    default_timeout: float = _DEFAULT_SHELL_TIMEOUT,
) -> tuple[str | None, float, dict[str, str] | None]:
    """Apply exec-related rules and return ``(cwd, timeout, env)`` for ``subprocess``.

    ``env`` is ``None`` (inherit) unless the caller passed ``env`` or the policy
    scrubs secrets from child environments.

    Raises:
        PolicyDenied: ``command_not_allowed``, ``path_*`` for ``cwd``,
            ``env_var_not_allowed``, plus ``env_var_denied`` / ``env_invalid`` and
            ``process_denied`` / ``process_invalid`` from the env and process guards.
        ValueError: malformed ``cwd`` / ``env`` / ``timeout`` values.
    """
    raw_cwd = body.get("cwd")
    if raw_cwd is not None and (not isinstance(raw_cwd, str)):
        raise ValueError("'cwd' must be a string")
    raw_env = body.get("env")
    if raw_env is not None and (
        not isinstance(raw_env, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw_env.items())
    ):
        raise ValueError("'env' must be an object of string values")
    raw_timeout = body.get("timeout", default_timeout)
    try:
        timeout = float(raw_timeout)
    except (ValueError, TypeError):
        timeout = default_timeout
    if timeout <= 0:
        timeout = default_timeout

    # Empty argv is left to the caller; empty env maps are admitted by ``check_env``.
    if args:
        check_process(args)
    if raw_env is not None:
        raw_env = check_env(raw_env)

    cwd: str | None = raw_cwd or None
    _check_command(ctx, args)
    if cwd is not None:
        cwd = ctx.resolve_path(cwd, "exec", field="cwd")
    cap = ctx.limit("timeout_seconds")
    if cap is not None:
        timeout = min(timeout, float(cap))
    base_env = ctx.engine.child_env()
    if raw_env:
        for name in raw_env:
            if ctx.engine.is_secret_env(name):
                raise PolicyDenied(
                    "env_var_not_allowed", f"Environment variable {name!r} is protected"
                )
    if cwd is not None and not os.path.isdir(cwd):
        raise ValueError(f"'cwd' is not a directory: {raw_cwd}")
    env: dict[str, str] | None = base_env
    if raw_env:
        env = dict(base_env if base_env is not None else os.environ)
        env.update(raw_env)
    return cwd, timeout, env


def _check_command(ctx: EndpointContext, args: list[str]) -> None:
    """Enforce ``allow_commands`` / ``deny_commands`` on ``argv[0]`` (basename and full path)."""
    if not args:
        return
    check_command(ctx, args)


def handle_shell(body: dict[str, Any], ctx: EndpointContext) -> tuple[int, dict[str, Any]]:
    """``POST /shell`` — execute a shell command via subprocess.

    Expected *body*::

        {"command": "ls -la /tmp", "cwd": "/tmp", "env": {"A": "1"}, "timeout": 30}

    ``cwd``, ``env`` and ``timeout`` are optional (default: server CWD, inherited
    environment, 300 s).

    Returns:
        ``(status_code, response_dict)``
    """
    command = body.get("command")
    if not command or not isinstance(command, str):
        return 400, {"error": "Missing or invalid 'command'", "type": "ValueError"}

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return 500, {"error": str(exc), "type": type(exc).__name__}
    try:
        cwd, timeout, env = enforce_exec_policy(ctx, args, body)
    except ValueError as exc:
        return 400, {"error": str(exc), "type": "ValueError"}

    try:
        proc = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return 500, {
            "error": f"Command timed out after {timeout:g}s",
            "type": "TimeoutError",
        }
    except Exception as exc:
        return 500, {"error": str(exc), "type": type(exc).__name__}

    stdout, stderr = proc.stdout, proc.stderr
    result: dict[str, Any] = {}
    limit = ctx.limit("max_output_bytes")
    if limit is not None:
        cap = int(limit)
        if len(stdout.encode()) > cap or len(stderr.encode()) > cap:
            result["truncated"] = True
        stdout = stdout.encode()[:cap].decode("utf-8", errors="ignore")
        stderr = stderr.encode()[:cap].decode("utf-8", errors="ignore")
    return 200, {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode, **result}


# ---------------------------------------------------------------------------
# Route-table adapters
# ---------------------------------------------------------------------------
#
# Each wrapper adapts a ``handle_*`` function (which returns a ``(status, body)``
# tuple) to the uniform route signature ``(request: ServerRequest) -> ServerResponse``.
# The active :class:`CommandRegistry` is injected by ``app.py`` under
# ``request.context["registry"]``.


def _handle_health_wrapped(request: ServerRequest) -> ServerResponse:
    """Adapt :func:`handle_health` to the route signature."""
    status, body = handle_health()
    return ServerResponse(status=status, body=body)


def _handle_commands_wrapped(request: ServerRequest) -> ServerResponse:
    """Adapt :func:`handle_list_commands` (``GET /commands``)."""
    registry = request.context.get("registry")
    status, body = handle_list_commands(registry, context_of(request))
    return ServerResponse(status=status, body=body)


def _handle_run_command_wrapped(request: ServerRequest) -> ServerResponse:
    """Adapt :func:`handle_run_command` (``POST /commands/{name}``)."""
    command_name = request.path_params.get("name", "")
    body = request.body or {}
    registry = request.context.get("registry")
    status, resp = handle_run_command(command_name, body, registry, context_of(request))
    return ServerResponse(status=status, body=resp)


def _handle_upload_wrapped(request: ServerRequest) -> ServerResponse:
    """Adapt :func:`handle_upload` (``POST /upload``)."""
    status, resp = handle_upload(request.body or {}, context_of(request))
    return ServerResponse(status=status, body=resp)


def _handle_download_wrapped(request: ServerRequest) -> ServerResponse:
    """Adapt :func:`handle_download` (``GET /download?path=...``)."""
    file_path = request.query.get("path", [""])[0]
    status, body = handle_download(file_path, context_of(request))
    return ServerResponse(status=status, body=body)


def _handle_shell_wrapped(request: ServerRequest) -> ServerResponse:
    """Adapt :func:`handle_shell` (``POST /shell``)."""
    status, resp = handle_shell(request.body or {}, context_of(request))
    return ServerResponse(status=status, body=resp)


# ---------------------------------------------------------------------------
# Register the built-in routes on the default table (import side-effect)
# ---------------------------------------------------------------------------

_table = default_table()
_table.mount("health", _handle_health_wrapped)
_table.mount("list_commands", _handle_commands_wrapped)
_table.mount("run_command", _handle_run_command_wrapped)
_table.mount("upload", _handle_upload_wrapped)
_table.mount("download", _handle_download_wrapped)
_table.mount("shell", _handle_shell_wrapped)
