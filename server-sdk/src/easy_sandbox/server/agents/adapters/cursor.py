"""Cursor CLI adapter (``cursor-agent -p --output-format stream-json``)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, ClassVar

from .. import events as ev
from .base import (
    AdapterCapabilities,
    AgentAdapter,
    EventParser,
    Invocation,
    InvocationFile,
    TurnContext,
    classify_text,
)

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = ["CursorAdapter", "CursorParser"]


def _clip(value: Any, limit: int = 16000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


class CursorParser(EventParser):
    """Parse ``cursor-agent`` stream-json output (with ``--stream-partial-output``).

    Partial output delivers text deltas (events carrying ``timestamp_ms``) and
    then a consolidated duplicate; duplicates are dropped by text comparison.
    """

    def __init__(self) -> None:
        self._cur: str | None = None
        self._acc = ""
        self._counter = 0
        self._finalized: set[str] = set()
        self._tools: dict[str, tuple[str, str]] = {}

    def _flush(self) -> list[ParsedEvent]:
        if self._cur is None:
            return []
        out = [ev.message(self._cur, self._acc)] if self._acc else []
        if self._acc:
            self._finalized.add(self._acc)
        self._cur, self._acc = None, ""
        return out

    def feed(self, line: str) -> list[ParsedEvent]:
        """Parse one JSONL line."""
        line = line.strip()
        if not line:
            return []
        try:
            obj = json.loads(line)
        except ValueError:
            return [ev.log(line)]
        if not isinstance(obj, dict):
            return []
        kind = obj.get("type")
        if kind == "system":
            if obj.get("subtype") == "init" and obj.get("session_id"):
                return [ev.session_event(str(obj["session_id"]))]
            return []
        if kind == "assistant":
            return self._assistant(obj)
        if kind == "tool_call":
            return self._tool_call(obj)
        if kind == "result":
            out = self._flush()
            ok = not obj.get("is_error") and obj.get("subtype") in (None, "success")
            text = obj.get("result") if isinstance(obj.get("result"), str) else None
            if not ok:
                out.append(ev.error(classify_text(text or ""), text or "agent error", fatal=True))
            out.append(ev.result(ok, text, stop_reason=obj.get("subtype")))
            return out
        return []

    def _assistant(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        message = obj.get("message") or {}
        text = "".join(
            str(b.get("text") or "")
            for b in message.get("content") or []
            if isinstance(b, dict) and b.get("type") == "text"
        )
        if not text:
            return []
        is_delta = "timestamp_ms" in obj
        out: list[ParsedEvent] = []
        if is_delta:
            if self._cur is None:
                self._counter += 1
                self._cur = f"msg-{self._counter}"
            self._acc += text
            return [ev.text_delta(self._cur, text)]
        if text in self._finalized and self._cur is None:
            return []
        if self._cur is not None and text == self._acc:
            return self._flush()
        if self._cur is None:
            self._counter += 1
            self._cur = f"msg-{self._counter}"
        elif not text.startswith(self._acc):
            out.extend(self._flush())
            self._counter += 1
            self._cur = f"msg-{self._counter}"
        self._acc = text
        out.extend(self._flush())
        return out

    def _tool_call(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        call_id = str(obj.get("call_id") or "")
        payload = obj.get("tool_call")
        if not isinstance(payload, dict) or not payload:
            return []
        key = next(iter(payload))
        body = payload[key] if isinstance(payload[key], dict) else {}
        args = body.get("args") if isinstance(body, dict) else None
        out: list[ParsedEvent] = []
        if obj.get("subtype") == "started":
            out.extend(self._flush())
            name = key[: -len("ToolCall")] if key.endswith("ToolCall") else key
            if name in ("shell", "bash") and isinstance(args, dict):
                out.append(
                    ev.tool_start(
                        call_id,
                        "command",
                        "command_execution",
                        arguments=args,
                        command=str(args.get("command") or ""),
                    )
                )
            else:
                out.append(ev.tool_start(call_id, "other", name, arguments=args))
            self._tools[call_id] = (name, key)
        elif obj.get("subtype") == "completed":
            if call_id not in self._tools:
                name = key[: -len("ToolCall")] if key.endswith("ToolCall") else key
                out.append(ev.tool_start(call_id, "other", name, arguments=args))
            result = body.get("result") if isinstance(body, dict) else None
            success = result.get("success") if isinstance(result, dict) else None
            failed = isinstance(result, dict) and ("error" in result or "failure" in result)
            exit_code = success.get("exitCode") if isinstance(success, dict) else None
            output = (
                _clip(success if success is not None else result) if result is not None else None
            )
            if isinstance(success, dict) and ("stdout" in success or "stderr" in success):
                output = f"{success.get('stdout') or ''}{success.get('stderr') or ''}"
            out.append(
                ev.tool_end(
                    call_id,
                    ok=not failed and exit_code in (None, 0),
                    output=output,
                    exit_code=exit_code if isinstance(exit_code, int) else None,
                )
            )
        return out


class CursorAdapter(AgentAdapter):
    """Adapter for Cursor's headless CLI agent."""

    name: ClassVar[str] = "cursor"
    aliases: ClassVar[tuple[str, ...]] = ("cursor-agent", "cursor_agent")
    binary: ClassVar[str] = "cursor-agent"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("sh", "-c", "curl -fsS https://cursor.com/install | bash"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        partial_deltas=True,
        mcp=True,
        system_prompt="preamble",
        base_url=False,
        max_turns=False,
        budget=False,
        experimental=True,
    )
    prompt_transport: ClassVar[str] = "argv"
    passthrough_env: ClassVar[tuple[str, ...]] = ("CURSOR_API_KEY",)
    credential_env_names: ClassVar[tuple[str, ...]] = ("CURSOR_API_KEY",)

    def validate(self, spec: AgentSpec) -> list[str]:
        """Cursor-specific configuration checks."""
        problems: list[str] = []
        if spec.provider.base_url:
            problems.append("provider.base_url is not supported by the cursor runtime")
        if spec.provider.auth == "bearer":
            problems.append("provider.auth='bearer' is not supported by the cursor runtime")
        return problems

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Fresh stream-json parser."""
        return CursorParser()

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """``cursor-agent -p … <prompt>`` (the CLI cannot read the prompt from stdin)."""
        spec = ctx.spec
        argv = ["cursor-agent", "-p", "--output-format", "stream-json", "--stream-partial-output"]
        env: dict[str, str] = {}
        files: list[InvocationFile] = []
        if ctx.native_session_id:
            argv += ["--resume", ctx.native_session_id]
        if spec.model:
            argv += ["--model", spec.model]
        if spec.permissions == "read_only":
            argv += ["--mode", "ask"]
        else:
            argv.append("--force")
        if spec.provider.api_key:
            env["CURSOR_API_KEY"] = spec.provider.api_key
        if spec.mcp_servers:
            argv.append("--approve-mcps")
            files.append(
                InvocationFile(
                    os.path.join(ctx.workdir, ".cursor", "mcp.json"),
                    json.dumps({"mcpServers": _mcp_servers(spec)}, indent=2).encode(),
                    mode=0o644,
                    merge_key="mcpServers",
                    git_exclude=True,
                )
            )
        argv += list(spec.extra_args)
        argv.append(self.prompt_argv_value(ctx))
        return Invocation(argv=argv, env=env, stdin=None, files=files)


def _mcp_servers(spec: AgentSpec) -> dict[str, Any]:
    servers: dict[str, Any] = {}
    for server in spec.mcp_servers.values():
        if server.is_remote:
            entry: dict[str, Any] = {"url": server.url}
            if server.headers:
                entry["headers"] = {
                    h: "${env:" + server.header_var(h) + "}" for h in server.headers
                }
        else:
            entry = {"command": server.command, "args": list(server.args)}
            if server.env:
                entry["env"] = {k: "${env:" + server.env_var(k) + "}" for k in server.env}
        servers[server.name] = entry
    return servers
