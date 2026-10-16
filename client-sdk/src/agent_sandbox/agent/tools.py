"""MCP tools for sandbox execution, files, and lifecycle management.

每个 Tool 包含：
- TOOL_SCHEMA: MCP Tool schema（name, description, inputSchema）
- handler 异步函数：接收参数 + sandbox manager，返回 dict 结果
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.models.sandbox import SandboxInfo

from agent_sandbox.utils.logging import get_logger

logger = get_logger("agent.tools")

_LIFECYCLE_TOOLS = frozenset(
    {"create_sandbox", "list_sandboxes", "get_sandbox", "set_sandbox_timeout"}
)


class _ToolInputError(ValueError):
    """An internally generated message containing no caller or provider values."""


# ---------------------------------------------------------------------------
# Tool schemas (MCP format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "create_sandbox",
        "description": (
            "创建一个云端沙箱，并将其设为当前会话的默认沙箱。"
            "之后省略 sandbox_id 的工具调用都作用在这只沙箱上。"
            "省略 template 时使用 MCP server 配置的模板"
            "（abx mcp start 默认为 code-interpreter-v1）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "\\S",
                    "description": "沙箱模板名称，省略时使用 server 配置的模板",
                },
                "timeout": {
                    "type": "integer",
                    "description": "沙箱超时时间（秒），默认 300",
                    "default": 300,
                    "minimum": 1,
                    "maximum": 86400,
                },
                "region": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "cpu": {"type": "integer", "minimum": 1},
                "memory": {"type": "integer", "minimum": 1, "description": "内存大小（MB）"},
                "provider": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "\\S",
                    "description": "已配置的 provider ID，省略时使用 SDK 默认值",
                },
                "envs": {
                    "type": "object",
                    "description": "环境变量键值对",
                    "additionalProperties": {"type": "string"},
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_sandboxes",
        "description": (
            "列出当前授权账户及 provider 可见的沙箱，不会创建沙箱或改变会话默认沙箱。"
            "返回安全元数据，不包含环境变量、凭据或用户 metadata。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [
                        "creating",
                        "running",
                        "paused",
                        "pausing",
                        "stopping",
                        "stopped",
                        "error",
                    ],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "provider": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "region": {"type": "string", "minLength": 1, "pattern": "\\S"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_sandbox",
        "description": (
            "从平台刷新沙箱安全元数据，不延长生命周期。省略 sandbox_id 时查询现有默认沙箱；"
            "无默认沙箱则返回错误，不会创建沙箱。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sandbox_id": {"type": "string", "minLength": 1, "pattern": "\\S"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "set_sandbox_timeout",
        "description": (
            "设置沙箱从现在起的生命周期（秒），并更新后续工具调用自动续期使用的时长。"
            "省略 sandbox_id 时使用现有默认沙箱；无默认沙箱则返回错误。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "minLength": 1, "pattern": "\\S"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 86400},
            },
            "required": ["timeout"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_code",
        "description": (
            "在沙箱中执行代码（通过 Code Interpreter）。"
            "支持 Python、JavaScript 等语言。省略 sandbox_id 时使用默认沙箱。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的代码"},
                "language": {
                    "type": "string",
                    "description": "编程语言，默认 python",
                    "default": "python",
                    "enum": ["python", "javascript", "shell", "typescript", "r"],
                },
                "sandbox_id": {
                    "type": "string",
                    "description": "沙箱 ID，省略时使用默认沙箱",
                },
                "timeout": {
                    "type": "integer",
                    "description": "执行超时（秒），默认 30",
                    "default": 30,
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "在沙箱中通过 sh -c 执行命令，因此支持管道、&&、$VAR 和 cd。"
            "省略 sandbox_id 时使用默认沙箱。"
            "省略 cwd 时使用镜像自己的工作目录。"
            "timeout 是本次调用等待的秒数；非零退出码会标成工具错误。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "交给 sh -c 的命令"},
                "sandbox_id": {"type": "string", "description": "沙箱 ID"},
                "cwd": {
                    "type": "string",
                    "description": "工作目录，省略时使用镜像工作目录",
                },
                "timeout": {
                    "type": "integer",
                    "description": "执行超时（秒），默认 60",
                    "default": 60,
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "读取沙箱中的文件内容。省略 sandbox_id 时使用默认沙箱。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "sandbox_id": {"type": "string", "description": "沙箱 ID"},
                "encoding": {
                    "type": "string",
                    "description": "文件编码，默认 utf-8",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "在沙箱中创建或覆写文件。省略 sandbox_id 时使用默认沙箱。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "content": {"type": "string", "description": "文件内容"},
                "sandbox_id": {"type": "string", "description": "沙箱 ID"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "列出沙箱中指定目录的文件和子目录。省略 sandbox_id 时使用默认沙箱。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径，省略时列出 /",
                    "default": "/",
                },
                "sandbox_id": {"type": "string", "description": "沙箱 ID"},
            },
        },
    },
    {
        "name": "kill_sandbox",
        "description": (
            "销毁指定沙箱。省略 sandbox_id 时销毁默认沙箱；当前没有默认沙箱时返回错误，而不是成功。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "要销毁的沙箱 ID，省略时销毁默认沙箱",
                },
            },
        },
    },
]

# Quick lookup by name
TOOL_SCHEMA_MAP: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOL_SCHEMAS}


# ---------------------------------------------------------------------------
# Tool handler functions
# ---------------------------------------------------------------------------


async def handle_create_sandbox(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle create_sandbox tool call."""
    _check_properties("create_sandbox", params)
    template = _optional_string(params, "template")
    timeout = _integer(params, "timeout", default=300, minimum=1, maximum=86400)
    envs = params.get("envs", {})
    if not isinstance(envs, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in envs.items()
    ):
        raise _ToolInputError("envs must be an object of string values")
    options: dict[str, Any] = {}
    for name in ("region", "provider"):
        if name in params:
            options[name] = _optional_string(params, name)
    for name in ("cpu", "memory"):
        if name in params:
            options[name] = _integer(params, name, minimum=1)

    sandbox = await manager.create_sandbox(
        template=template,
        timeout=timeout,
        envs=envs,
        **options,
    )
    return {
        "sandbox_id": sandbox.id,
        "status": sandbox.status.value,
        "url": sandbox.url,
    }


def _check_properties(name: str, params: dict[str, Any]) -> None:
    """Reject unsupported arguments rather than silently implying support."""
    properties = TOOL_SCHEMA_MAP[name]["inputSchema"]["properties"]
    if params.keys() - properties.keys():
        raise _ToolInputError(f"Unsupported argument for {name}; see its inputSchema")


def _integer(
    params: dict[str, Any],
    name: str,
    *,
    default: int | None = None,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    """Validate actual integers, including direct calls without schema validation."""
    value = params.get(name, default)
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        bound = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise _ToolInputError(f"{name} must be an integer in {bound}")
    return value


def _optional_string(params: dict[str, Any], name: str) -> str | None:
    """Accept an omitted string; reject empty or mistyped explicit values."""
    if name not in params:
        return None
    value = params[name]
    if not isinstance(value, str) or not value.strip():
        raise _ToolInputError(f"{name} must be a non-empty string")
    return value


def _safe_sandbox_info(info: SandboxInfo) -> dict[str, Any]:
    """Serialize a fixed allowlist; never serialize an entire SDK model."""
    return {
        "sandbox_id": info.sandbox_id,
        "template": info.template,
        "status": info.status.value,
        "region": info.region,
        "started_at": info.started_at.isoformat() if info.started_at else None,
        "end_at": info.end_at.isoformat() if info.end_at else None,
        "cpu_count": info.cpu_count,
        "memory_mb": info.memory_mb,
        "disk_size_mb": info.disk_size_mb,
    }


async def handle_list_sandboxes(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """List platform sandboxes with bounded pagination and safe metadata."""
    _check_properties("list_sandboxes", params)
    limit = _integer(params, "limit", default=100, minimum=1, maximum=100)
    offset = _integer(params, "offset", default=0, minimum=0)
    status = _optional_string(params, "status")
    if status is not None:
        from agent_sandbox.models.sandbox import SandboxStatus

        try:
            SandboxStatus(status)
        except ValueError:
            raise _ToolInputError("status must be a supported sandbox state") from None
    infos = await manager.list_sandboxes(
        status=status,
        limit=limit,
        offset=offset,
        provider=_optional_string(params, "provider"),
        region=_optional_string(params, "region"),
    )
    return {
        "sandboxes": [_safe_sandbox_info(info) for info in infos],
        "limit": limit,
        "offset": offset,
    }


async def handle_get_sandbox(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Refresh an existing sandbox without implicit creation or renewal."""
    _check_properties("get_sandbox", params)
    info = await manager.inspect_sandbox(_optional_string(params, "sandbox_id"))
    return _safe_sandbox_info(info)


async def handle_set_sandbox_timeout(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Update a sandbox's TTL and the session renewal policy."""
    _check_properties("set_sandbox_timeout", params)
    timeout = _integer(params, "timeout", minimum=1, maximum=86400)
    sandbox_id = await manager.set_sandbox_timeout(
        timeout,
        _optional_string(params, "sandbox_id"),
    )
    return {"success": True, "sandbox_id": sandbox_id, "timeout": timeout}


async def handle_run_code(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle run_code tool call."""
    code = params["code"]
    language = params.get("language", "python")
    timeout = params.get("timeout", 30)
    sandbox_id = params.get("sandbox_id") or None

    sandbox = await manager.get_sandbox(sandbox_id)
    result = await sandbox.run_code(code, language=language, timeout=timeout)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "output_files": [
            {"name": f.name, "path": f.path, "size": f.size} for f in result.output_files
        ],
    }


async def handle_run_command(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle run_command tool call."""
    command = params["command"]
    timeout = params.get("timeout", 60)
    cwd = params.get("cwd") or ""
    sandbox_id = params.get("sandbox_id") or None

    sandbox = await manager.get_sandbox(sandbox_id)
    result = await sandbox.commands.run(command, timeout=timeout, cwd=cwd, shell=True)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
    }


async def handle_read_file(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle read_file tool call."""
    path = params["path"]
    encoding = params.get("encoding", "utf-8")
    sandbox_id = params.get("sandbox_id") or None

    sandbox = await manager.get_sandbox(sandbox_id)
    content = await sandbox.files.read(path, encoding=encoding)
    return {"content": content}


async def handle_write_file(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle write_file tool call."""
    path = params["path"]
    content = params["content"]
    sandbox_id = params.get("sandbox_id") or None

    sandbox = await manager.get_sandbox(sandbox_id)
    await sandbox.files.write(path, content)
    return {"success": True, "bytes_written": len(content.encode("utf-8"))}


async def handle_list_files(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle list_files tool call."""
    path = params.get("path") or "/"
    sandbox_id = params.get("sandbox_id") or None

    sandbox = await manager.get_sandbox(sandbox_id)
    files = await sandbox.files.list(path)
    return {
        "files": [
            {
                "name": f.name,
                "path": f.path,
                "type": f.type.value,
                "size": f.size,
            }
            for f in files
        ],
    }


async def handle_kill_sandbox(
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Handle kill_sandbox tool call."""
    raw_id = params.get("sandbox_id")
    sandbox_id = raw_id if isinstance(raw_id, str) and raw_id else None
    killed = await manager.kill_sandbox(sandbox_id)
    if not killed:
        return {
            "success": False,
            "error": (
                "No sandbox to destroy. Call create_sandbox or another tool "
                "before kill_sandbox without sandbox_id."
            ),
        }
    return {"success": True, "sandbox_id": killed}


# Handler dispatch table
TOOL_HANDLERS: dict[str, Any] = {
    "create_sandbox": handle_create_sandbox,
    "list_sandboxes": handle_list_sandboxes,
    "get_sandbox": handle_get_sandbox,
    "set_sandbox_timeout": handle_set_sandbox_timeout,
    "run_code": handle_run_code,
    "run_command": handle_run_command,
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "list_files": handle_list_files,
    "kill_sandbox": handle_kill_sandbox,
}


async def dispatch_tool(
    name: str,
    params: dict[str, Any],
    manager: SandboxManager,
) -> dict[str, Any]:
    """Dispatch a tool call to its handler.

    Args:
        name: Tool name.
        params: Tool parameters.
        manager: Sandbox manager instance.

    Returns:
        Tool result dict.

    Raises:
        ValueError: If the tool name is not recognized.
    """
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    try:
        return await handler(params, manager)  # type: ignore[no-any-return]
    except Exception as exc:
        if name in _LIFECYCLE_TOOLS:
            payload = _format_lifecycle_error(exc)
            # Exception strings and tracebacks can include request URLs, model
            # validation inputs, provider credentials, or caller-supplied envs.
            logger.error("Tool %s failed: %s", name, payload["error"])
            return payload
        logger.error("Tool %s failed: %s", name, exc, exc_info=True)
        return _format_tool_error(exc)


def _format_lifecycle_error(exc: BaseException) -> dict[str, Any]:
    """Describe failure categories without echoing untrusted exception contents."""
    import httpx
    from pydantic import ValidationError

    from agent_sandbox.models.errors import (
        AuthenticationError,
        ProviderFeatureNotSupportedError,
        ProviderResourceNotFoundError,
        QuotaExceededError,
        SandboxError,
        SandboxNotFoundError,
        TemplateNotFoundError,
    )

    if type(exc) is _ToolInputError:
        return {"error": str(exc)}
    if isinstance(exc, ValidationError):
        return {"error": "The platform returned invalid sandbox metadata."}
    if isinstance(exc, httpx.HTTPStatusError):
        return {"error": f"Sandbox lifecycle request failed (HTTP {exc.response.status_code})."}
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return {"error": "Sandbox lifecycle request timed out."}
    if isinstance(exc, httpx.RequestError):
        return {"error": "Sandbox lifecycle request could not reach the platform."}
    if isinstance(exc, SandboxError):
        message = "Sandbox lifecycle operation failed."
        suggestion = "Check the sandbox, provider configuration, and platform permissions."
        if isinstance(exc, AuthenticationError):
            message = "Sandbox authentication failed."
            suggestion = "Check the authorized provider credential configuration."
        elif isinstance(exc, (SandboxNotFoundError, ProviderResourceNotFoundError)):
            message = "Sandbox was not found."
            suggestion = "List sandboxes and use an existing sandbox ID."
        elif isinstance(exc, ProviderFeatureNotSupportedError):
            message = "The provider does not support this lifecycle operation."
            suggestion = "Choose a provider that supports this operation."
        elif isinstance(exc, QuotaExceededError):
            message = "Sandbox quota exceeded."
            suggestion = "Remove unused sandboxes or request additional quota."
        elif isinstance(exc, TemplateNotFoundError):
            message = "Sandbox template was not found."
            suggestion = "Choose an available template."
        code = exc.code
        if (
            isinstance(code, str)
            and len(code) == 5
            and code[0] == "E"
            and all(char in "0123456789" for char in code[1:])
        ):
            message = f"[{code}] {message}"
        return {"error": message, "suggestion": suggestion}
    return {"error": "Sandbox lifecycle operation failed."}


def _format_tool_error(exc: BaseException) -> dict[str, Any]:
    """Turn an exception into a short tool payload for the model.

    SDK errors keep their code, message, and suggestion. Transport errors
    drop the trailing HTTP documentation link that ``httpx`` appends.
    """
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    suggestion = getattr(exc, "suggestion", None)
    if isinstance(code, str) and isinstance(message, str) and message:
        payload: dict[str, Any] = {"error": f"[{code}] {message}"}
        if isinstance(suggestion, str) and suggestion:
            payload["suggestion"] = suggestion
        return payload
    text = str(exc)
    marker = "For more information check:"
    if marker in text:
        text = text.split(marker, 1)[0].strip()
    return {"error": text or type(exc).__name__}
