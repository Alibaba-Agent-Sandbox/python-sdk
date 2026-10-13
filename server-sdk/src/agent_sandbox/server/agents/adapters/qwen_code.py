"""Qwen Code adapter (``qwen <prompt> --output-format stream-json``)."""

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

__all__ = ["QwenCodeAdapter"]

# Exit codes documented by qwen-code (see client ``api/deploy.py``).
_EXIT_CODES = {
    53: ("session_budget_exceeded", "qwen-code stopped: session turn limit exceeded"),
    55: ("session_budget_exceeded", "qwen-code stopped: budget exceeded"),
}


class QwenCodeAdapter(AgentAdapter):
    """Adapter for Alibaba's Qwen Code CLI."""

    name: ClassVar[str] = "qwen-code"
    aliases: ClassVar[tuple[str, ...]] = ("qwen", "qwen_code", "qwencode")
    binary: ClassVar[str] = "qwen"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("npm", "install", "-g", "@qwen-code/qwen-code"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        partial_deltas=True,
        mcp=True,
        system_prompt="flag",
        base_url=True,
        max_turns=True,
        budget=False,
        experimental=True,
    )
    prompt_transport: ClassVar[str] = "argv"
    passthrough_env: ClassVar[tuple[str, ...]] = (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
    )
    credential_env_names: ClassVar[tuple[str, ...]] = ("OPENAI_API_KEY",)

    def validate(self, spec: AgentSpec) -> list[str]:
        """Qwen-specific configuration checks."""
        if spec.provider.auth == "bearer":
            return ["provider.auth='bearer' is not supported by qwen-code"]
        return []

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Fresh stream-json parser."""
        return StreamJsonParser()

    def classify_failure(self, returncode: int | None, stderr_tail: str) -> tuple[str, str]:
        """Use qwen-code's documented exit codes before falling back to stderr patterns."""
        if returncode in _EXIT_CODES:
            return _EXIT_CODES[returncode]
        return super().classify_failure(returncode, stderr_tail)

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """``qwen <prompt> …`` — the prompt is positional (``-p`` is deprecated upstream)."""
        spec = ctx.spec
        argv = [
            "qwen",
            self.prompt_argv_value(ctx),
            "--output-format",
            "stream-json",
            "--include-partial-messages",
        ]
        env: dict[str, str] = {}
        files: list[InvocationFile] = []
        if ctx.native_session_id:
            argv += ["--resume", ctx.native_session_id]
        if spec.model:
            argv += ["--model", spec.model]
            env["OPENAI_MODEL"] = spec.model
        if spec.permissions == "full_access":
            argv.append("--yolo")
        elif spec.permissions == "workspace_write":
            argv += ["--approval-mode", "auto-edit"]
        else:
            argv += ["--approval-mode", "plan"]
        if spec.instructions:
            argv += ["--append-system-prompt", spec.instructions]
        if spec.limits.max_turns:
            argv += ["--max-session-turns", str(spec.limits.max_turns)]

        if spec.provider.base_url:
            env["OPENAI_BASE_URL"] = spec.provider.base_url
        if spec.provider.api_key:
            env["OPENAI_API_KEY"] = spec.provider.api_key

        if spec.mcp_servers:
            path = os.path.join(ctx.workdir, ".qwen", "settings.json")
            files.append(
                InvocationFile(
                    path,
                    json.dumps({"mcpServers": _mcp_servers(spec)}, indent=2).encode(),
                    mode=0o644,
                    merge_key="mcpServers",
                    git_exclude=True,
                )
            )
        argv += list(spec.extra_args)
        return Invocation(argv=argv, env=env, stdin=None, files=files)


def _mcp_servers(spec: AgentSpec) -> dict[str, Any]:
    servers: dict[str, Any] = {}
    for server in spec.mcp_servers.values():
        if server.is_remote:
            key = "url" if server.transport == "sse" else "httpUrl"
            entry: dict[str, Any] = {key: server.url}
            if server.headers:
                entry["headers"] = {h: "${" + server.header_var(h) + "}" for h in server.headers}
        else:
            entry = {"command": server.command, "args": list(server.args)}
            if server.env:
                entry["env"] = {k: "${" + server.env_var(k) + "}" for k in server.env}
        servers[server.name] = entry
    return servers
