"""OpenCode 1.19.x JSON event adapter with explicit OpenAI-compatible provider config."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from .. import events as ev
from .base import AdapterCapabilities, AgentAdapter, EventParser, Invocation, TurnContext

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = ["OpenCodeAdapter", "OpenCodeParser"]


class OpenCodeParser(EventParser):
    """Consume native run JSON records; model errors never become successful turns."""

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.terminal = False

    def feed(self, line: str) -> list[ParsedEvent]:
        """Map complete native text/tool/step records without inventing token deltas."""
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            return [ev.log(line)]
        if not isinstance(obj, dict):
            return []
        out = []
        sid = obj.get("sessionID")
        if isinstance(sid, str) and sid != self.session_id:
            self.session_id = sid
            out.append(ev.session_event(sid))
        kind = obj.get("type")
        part = obj.get("part") or {}
        if not isinstance(part, dict):
            part = {}
        identity = str(part.get("id") or "native")
        if kind in {"text", "reasoning"} and isinstance(part.get("text"), str):
            out.append((ev.message if kind == "text" else ev.reasoning)(identity, part["text"]))
        elif kind == "tool_use":
            state = part.get("state") or {}
            if isinstance(state, dict):
                name = str(part.get("tool") or "tool")
                if state.get("status") in {"completed", "error"}:
                    arguments = state.get("input")
                    command = arguments.get("command") if isinstance(arguments, dict) else None
                    timing = state.get("time")
                    duration = None
                    if isinstance(timing, dict) and all(
                        isinstance(timing.get(k), (int, float)) for k in ("start", "end")
                    ):
                        duration = max(0, int(timing["end"] - timing["start"]))
                    out.append(
                        ev.ParsedEvent(
                            "tool_complete",
                            identity,
                            str(state.get("output") or ""),
                            {
                                "kind": "command" if name == "bash" else "other",
                                "name": name,
                                "arguments": arguments,
                                "command": command,
                                "ok": state.get("status") == "completed",
                                "error": str(state.get("error") or "") or None,
                                "duration_ms": duration,
                            },
                        )
                    )
        elif kind == "step_finish":
            tokens = part.get("tokens") or {}
            if isinstance(tokens, dict):
                out.append(
                    ev.usage(
                        input_tokens=int(tokens.get("input") or 0),
                        output_tokens=int(tokens.get("output") or 0),
                    )
                )
            if part.get("reason") in {"stop", "end_turn", "length"}:
                self.terminal = True
                out.append(ev.result(part.get("reason") != "length", stop_reason=part["reason"]))
        elif kind == "error":
            self.terminal = True
            error = obj.get("error") or {}
            if not isinstance(error, dict):
                error = {"name": str(error)}
            data = error.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            message = str(data.get("message") or error.get("name") or "OpenCode failed")
            out += [ev.error("native_error", message, fatal=True), ev.result(False, message)]
        return out

    def finish(self, returncode: int | None) -> list[ParsedEvent]:
        """Require a native terminal step even when the process exits zero."""
        if not self.terminal:
            return [ev.result(False, "OpenCode ended without a terminal step")]
        return []


class OpenCodeAdapter(AgentAdapter):
    """Run an isolated OpenCode headless invocation using native session persistence."""

    name: ClassVar[str] = "opencode"
    aliases: ClassVar[tuple[str, ...]] = ("open-code",)
    binary: ClassVar[str] = "opencode"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("npm", "install", "-g", "opencode-ai@1.19.5"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        mcp=False,
        base_url=True,
        system_prompt="preamble",
        experimental=True,
        tool_events="completed_only",
    )
    passthrough_env: ClassVar[tuple[str, ...]] = (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
    )
    credential_env_names: ClassVar[tuple[str, ...]] = ("OPENAI_API_KEY",)

    def validate(self, spec: AgentSpec) -> list[str]:
        """Keep custom provider and unsupported MCP behavior explicit."""
        problems = []
        if spec.permissions == "workspace_write":
            problems.append(
                "opencode adapter does not support workspace_write; choose read_only or full_access"
            )
        if spec.mcp_servers:
            problems.append("opencode managed MCP configuration is not supported")
        return problems

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Return a fresh parser for each native turn."""
        return OpenCodeParser()

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """Configure the native provider through its environment-referenced JSON config."""
        spec = ctx.spec
        if spec.permissions == "workspace_write":
            raise ValueError("opencode adapter does not support workspace_write")
        model = spec.model or "default"
        config = {
            "$schema": "https://opencode.ai/config.json",
            "model": "abx/" + model,
            "provider": {
                "abx": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Configured model",
                    "options": {
                        "baseURL": "{env:OPENAI_BASE_URL}",
                        "apiKey": "{env:OPENAI_API_KEY}",
                    },
                    "models": {model: {"name": model}},
                }
            },
            "permission": "allow",
        }
        if spec.permissions == "read_only":
            config["permission"] = {
                "*": "deny",
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
            }
        argv = ["opencode", "run", "--format", "json", "--model", "abx/" + model]
        if ctx.native_session_id:
            argv += ["--session", ctx.native_session_id]
        argv += list(spec.extra_args)
        env = {"OPENCODE_CONFIG_CONTENT": json.dumps(config), "OPENCODE_DISABLE_AUTOUPDATE": "true"}
        if spec.provider.api_key:
            env["OPENAI_API_KEY"] = spec.provider.api_key
        if spec.provider.base_url:
            env["OPENAI_BASE_URL"] = spec.provider.base_url
        return Invocation(argv=argv, env=env, stdin=self.prompt_stdin(ctx))
