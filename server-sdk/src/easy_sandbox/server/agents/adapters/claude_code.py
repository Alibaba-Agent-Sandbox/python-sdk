"""Claude Code adapter (``claude -p --output-format stream-json``)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, ClassVar

from .base import (
    AdapterCapabilities,
    AgentAdapter,
    EventParser,
    Invocation,
    InvocationFile,
    TurnContext,
)
from .stream_json import StreamJsonParser

if TYPE_CHECKING:
    from ..config import AgentSpec

__all__ = ["ClaudeCodeAdapter"]


class ClaudeCodeAdapter(AgentAdapter):
    """Adapter for Anthropic's Claude Code CLI."""

    name: ClassVar[str] = "claude-code"
    aliases: ClassVar[tuple[str, ...]] = ("claude", "claude_code", "claudecode")
    binary: ClassVar[str] = "claude"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("npm", "install", "-g", "@anthropic-ai/claude-code"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        partial_deltas=True,
        mcp=True,
        system_prompt="flag",
        base_url=True,
        max_turns=True,
        budget=True,
    )
    prompt_transport: ClassVar[str] = "stdin"
    passthrough_env: ClassVar[tuple[str, ...]] = (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_OAUTH_TOKEN",
    )
    credential_env_names: ClassVar[tuple[str, ...]] = (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
    )

    def validate(self, spec: AgentSpec) -> list[str]:
        """Claude-specific configuration checks."""
        return []

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Fresh stream-json parser."""
        return StreamJsonParser()

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """``claude -p`` with the prompt on stdin."""
        spec = ctx.spec
        argv = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        env: dict[str, str] = {}
        files: list[InvocationFile] = []
        if ctx.native_session_id:
            argv += ["--resume", ctx.native_session_id]
        if spec.model:
            argv += ["--model", spec.model]

        if spec.permissions == "read_only":
            argv += ["--permission-mode", "plan"]
        elif spec.permissions == "workspace_write":
            argv += [
                "--permission-mode",
                "acceptEdits",
                "--allowedTools",
                "Read,Edit,Write,Bash,Glob,Grep",
            ]
        else:
            argv += ["--permission-mode", "bypassPermissions"]
            if ctx.is_root:
                env["IS_SANDBOX"] = "1"

        if spec.instructions:
            argv += ["--append-system-prompt", spec.instructions]
        if spec.limits.max_turns:
            argv += ["--max-turns", str(spec.limits.max_turns)]
        if spec.limits.max_budget_usd:
            argv += ["--max-budget-usd", str(spec.limits.max_budget_usd)]

        provider = spec.provider
        if provider.base_url:
            env["ANTHROPIC_BASE_URL"] = provider.base_url
        if provider.api_key:
            env["ANTHROPIC_AUTH_TOKEN" if provider.auth == "bearer" else "ANTHROPIC_API_KEY"] = (
                provider.api_key
            )

        if spec.mcp_servers:
            path = os.path.join(ctx.turn_dir, "mcp.json")
            files.append(InvocationFile(path, json.dumps(_mcp_config(spec), indent=2).encode()))
            argv += ["--mcp-config", path]

        argv += list(spec.extra_args)
        return Invocation(argv=argv, env=env, stdin=self.prompt_stdin(ctx), files=files)


def _mcp_config(spec: AgentSpec) -> dict[str, Any]:
    servers: dict[str, Any] = {}
    for server in spec.mcp_servers.values():
        if server.is_remote:
            entry: dict[str, Any] = {"type": server.transport or "http", "url": server.url}
            if server.headers:
                entry["headers"] = {h: "${" + server.header_var(h) + "}" for h in server.headers}
        else:
            entry = {"command": server.command, "args": list(server.args)}
            if server.env:
                entry["env"] = {k: "${" + server.env_var(k) + "}" for k in server.env}
        servers[server.name] = entry
    return {"mcpServers": servers}
