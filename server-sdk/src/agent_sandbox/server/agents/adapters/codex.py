"""OpenAI Codex CLI adapter (``codex exec --json``)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from .. import events as ev
from .base import (
    AdapterCapabilities,
    AgentAdapter,
    EventParser,
    Invocation,
    TurnContext,
    toml_key,
    toml_value,
)

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = ["CodexAdapter", "CodexParser"]

_SANDBOX_MODES = {
    "read_only": "read-only",
    "workspace_write": "workspace-write",
    "full_access": "danger-full-access",
}

PROVIDER_KEY_ENV = "ABX_PROVIDER_API_KEY"


class CodexParser(EventParser):
    """Parse the JSONL stream of ``codex exec --json``."""

    def __init__(self) -> None:
        self._started: set[str] = set()
        self._buffered_text: dict[str, str] = {}

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
        if kind == "thread.started" and obj.get("thread_id"):
            return [ev.session_event(str(obj["thread_id"]))]
        if kind in ("item.started", "item.updated", "item.completed"):
            item = obj.get("item")
            if isinstance(item, dict):
                return self._item(kind, item)
            return []
        if kind == "turn.completed":
            usage = obj.get("usage") or {}
            out: list[ParsedEvent] = []
            if isinstance(usage, dict) and usage:
                out.append(
                    ev.usage(
                        input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cached_tokens=int(usage.get("cached_input_tokens") or 0),
                        reasoning_tokens=int(usage.get("reasoning_output_tokens") or 0),
                    )
                )
            out.append(ev.result(True))
            return out
        if kind == "turn.failed":
            error = obj.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            return [
                ev.error("internal_error", str(message or "turn failed"), fatal=True),
                ev.result(False),
            ]
        if kind == "error":
            return [ev.error("internal_error", str(obj.get("message") or "error"), fatal=False)]
        return []

    def _item(self, event_type: str, item: dict[str, Any]) -> list[ParsedEvent]:
        item_id = str(item.get("id") or "")
        itype = item.get("type")
        done = event_type == "item.completed"
        out: list[ParsedEvent] = []
        if itype == "agent_message":
            if done:
                out.append(ev.message(item_id, str(item.get("text") or "")))
        elif itype == "reasoning":
            if done and item.get("text"):
                out.append(ev.reasoning(item_id, str(item["text"])))
        elif itype == "command_execution":
            if item_id not in self._started:
                self._started.add(item_id)
                out.append(
                    ev.tool_start(
                        item_id,
                        "command",
                        "command_execution",
                        arguments={"command": item.get("command")},
                        command=str(item.get("command") or ""),
                    )
                )
            if done:
                status = item.get("status")
                code = item.get("exit_code")
                out.append(
                    ev.tool_end(
                        item_id,
                        ok=status not in ("failed", "declined") and code in (None, 0),
                        output=str(item.get("aggregated_output") or ""),
                        exit_code=code if isinstance(code, int) else None,
                    )
                )
        elif itype == "mcp_tool_call":
            if item_id not in self._started:
                self._started.add(item_id)
                out.append(
                    ev.tool_start(
                        item_id,
                        "mcp",
                        str(item.get("tool") or "tool"),
                        arguments=item.get("arguments"),
                        server=str(item.get("server") or ""),
                    )
                )
            if done:
                err = item.get("error")
                result = item.get("result")
                out.append(
                    ev.tool_end(
                        item_id,
                        ok=item.get("status") != "failed" and not err,
                        output=_json_text(result) if result is not None else None,
                        error_text=(err.get("message") if isinstance(err, dict) else str(err))
                        if err
                        else None,
                    )
                )
        elif itype == "file_change":
            if done:
                changes = item.get("changes") or []
                summary = "\n".join(
                    f"{c.get('kind')}: {c.get('path')}" for c in changes if isinstance(c, dict)
                )
                out.append(
                    ev.tool_start(
                        item_id, "file_change", "file_change", arguments={"changes": changes}
                    )
                )
                out.append(ev.tool_end(item_id, ok=item.get("status") != "failed", output=summary))
        elif itype == "collab_tool_call":
            if done:
                out.extend(_collab_events(item))
        elif itype == "web_search":
            if done:
                out.append(
                    ev.tool_start(
                        item_id, "web_search", "web_search", arguments={"query": item.get("query")}
                    )
                )
                out.append(ev.tool_end(item_id, ok=True, output=str(item.get("query") or "")))
        elif itype == "error" and done:
            out.append(ev.error("internal_error", str(item.get("message") or "error"), fatal=False))
        return out


def _collab_events(item: dict[str, Any]) -> list[ParsedEvent]:
    """Subagent ids of a ``collab_tool_call`` item (``receiver_thread_ids`` / ``agents_states``)."""
    tool = str(item.get("tool") or "")
    ids = [str(i) for i in item.get("receiver_thread_ids") or [] if i]
    states = item.get("agents_states")
    closed: list[str] = []
    if isinstance(states, dict):
        for thread_id, state in states.items():
            if str(thread_id) not in ids:
                ids.append(str(thread_id))
            if isinstance(state, dict) and state.get("status") in ("shutdown", "closed"):
                closed.append(str(thread_id))
    if tool == "close_agent":
        closed = list(dict.fromkeys([*closed, *ids]))
    prompt = item.get("prompt") if tool == "spawn_agent" else None
    out: list[ParsedEvent] = []
    if ids:
        out.append(ev.subagent("open", ids, prompt=str(prompt) if prompt else None))
    if closed:
        out.append(ev.subagent("close", closed))
    return out


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


class CodexAdapter(AgentAdapter):
    """Adapter for the OpenAI Codex CLI."""

    name: ClassVar[str] = "codex"
    aliases: ClassVar[tuple[str, ...]] = ("openai-codex",)
    binary: ClassVar[str] = "codex"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("npm", "install", "-g", "@openai/codex"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        partial_deltas=False,
        mcp=True,
        system_prompt="preamble",
        base_url=True,
        max_turns=False,
        budget=False,
    )
    prompt_transport: ClassVar[str] = "stdin"
    passthrough_env: ClassVar[tuple[str, ...]] = (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "OPENAI_BASE_URL",
    )
    credential_env_names: ClassVar[tuple[str, ...]] = ("CODEX_API_KEY", "OPENAI_API_KEY")

    def validate(self, spec: AgentSpec) -> list[str]:
        """Codex-specific configuration checks."""
        problems: list[str] = []
        if spec.provider.auth == "bearer":
            problems.append("provider.auth='bearer' is not supported by codex (use api_key)")
        return problems

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Fresh JSONL parser."""
        return CodexParser()

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """``codex exec [resume ID] --json … -`` with the prompt on stdin."""
        spec = ctx.spec
        resume = ctx.native_session_id is not None
        env: dict[str, str] = {}
        argv = ["codex", "exec"]
        if resume:
            argv += ["resume", str(ctx.native_session_id)]
        argv += ["--json", "--skip-git-repo-check"]
        if not resume:
            argv += ["-C", ctx.workdir]
        if spec.model:
            argv += ["-m", spec.model]

        overrides: list[tuple[str, Any]] = [
            ("sandbox_mode", _SANDBOX_MODES[spec.permissions]),
            ("approval_policy", "never"),
        ]
        if spec.reasoning_effort:
            overrides.append(("model_reasoning_effort", spec.reasoning_effort))

        provider = spec.provider
        custom_provider = bool(provider.base_url) or provider.api_key_env is not None
        if custom_provider:
            overrides += [
                ("model_provider", "abx"),
                ("model_providers.abx.name", "abx"),
                ("model_providers.abx.wire_api", provider.wire_api),
            ]
            if provider.base_url:
                overrides.append(("model_providers.abx.base_url", provider.base_url))
            key_env = provider.api_key_env or PROVIDER_KEY_ENV
            overrides.append(("model_providers.abx.env_key", key_env))
            if provider.api_key:
                env[key_env] = provider.api_key
        elif provider.api_key:
            env["CODEX_API_KEY"] = provider.api_key
            env["OPENAI_API_KEY"] = provider.api_key

        for server in spec.mcp_servers.values():
            base = f"mcp_servers.{toml_key(server.name)}"
            if server.is_remote:
                overrides.append((f"{base}.url", server.url))
                if server.headers:
                    overrides.append(
                        (
                            f"{base}.env_http_headers",
                            {h: server.header_var(h) for h in server.headers},
                        )
                    )
            else:
                overrides.append((f"{base}.command", server.command))
                if server.args:
                    overrides.append((f"{base}.args", list(server.args)))
                if server.env:
                    overrides.append((f"{base}.env_vars", list(server.env)))
                    env.update(server.env)

        for key, value in overrides:
            argv += ["-c", f"{key}={toml_value(value)}"]
        argv += list(spec.extra_args)
        argv.append("-")
        return Invocation(argv=argv, env=env, stdin=self.prompt_stdin(ctx))
