"""Official DeepSeek Harness headless adapter (not a project-owned model loop)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, ClassVar

from .. import events as ev
from .base import (
    AdapterCapabilities,
    AgentAdapter,
    EventParser,
    Invocation,
    InvocationFile,
    TurnContext,
)

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = ["DeepSeekHarnessAdapter", "DeepSeekHarnessParser"]


class DeepSeekHarnessParser(EventParser):
    """Read committed-step events and require the authoritative final reason."""

    def __init__(self) -> None:
        self.final = False
        self.sequence = 0

    def feed(self, line: str) -> list[ParsedEvent]:
        """Normalize native JSON without presenting step text as token deltas."""
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            return [ev.log(line)]
        if not isinstance(obj, dict):
            return []
        kind = obj.get("type")
        self.sequence += 1
        identity = "dsh-" + str(self.sequence)
        if kind == "session" and isinstance(obj.get("sessionId"), str):
            return [ev.session_event(obj["sessionId"])]
        if kind in {"text", "thinking"} and isinstance(obj.get("text"), str):
            return [(ev.message if kind == "text" else ev.reasoning)(identity, obj["text"])]
        if kind == "tool_call":
            return [
                ev.tool_start(
                    str(obj.get("callId") or identity),
                    "other",
                    str(obj.get("tool") or "tool"),
                    arguments=obj.get("input"),
                )
            ]
        if kind == "tool_result":
            return [
                ev.tool_end(
                    str(obj.get("callId") or identity),
                    ok=obj.get("status") == "completed",
                    output=str(obj.get("result") or ""),
                )
            ]
        if kind == "status" and obj.get("phase") == "step_end":
            usage = obj.get("usage")
            if isinstance(usage, dict):
                return [
                    ev.usage(
                        input_tokens=int(usage.get("inputTokens") or 0),
                        output_tokens=int(usage.get("outputTokens") or 0),
                        cached_tokens=int(usage.get("cacheReadTokens") or 0),
                        reasoning_tokens=int(usage.get("reasoningTokens") or 0),
                    )
                ]
        if kind == "final":
            self.final = True
            reason = obj.get("reason")
            ok = isinstance(reason, dict) and reason.get("kind") == "completed"
            return [
                ev.result(
                    ok,
                    str(obj.get("text") or ""),
                    reason.get("kind") if isinstance(reason, dict) else "missing_reason",
                )
            ]
        if kind == "error":
            return [
                ev.error(
                    "native_error", str(obj.get("message") or "DeepSeek Harness failed"), fatal=True
                )
            ]
        return []

    def finish(self, returncode: int | None) -> list[ParsedEvent]:
        """A stream without final cannot represent a completed native turn."""
        return [] if self.final else [ev.result(False, "DeepSeek Harness ended without final")]


class DeepSeekHarnessAdapter(AgentAdapter):
    """Invoke the official dsh package and preserve its home for exact native resume."""

    name: ClassVar[str] = "deepseek-harness"
    aliases: ClassVar[tuple[str, ...]] = ("deepseekharness", "dsh")
    binary: ClassVar[str] = "dsh"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("npm", "install", "-g", "@deepseek-ai/dsh@0.2.2-rc.1"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        mcp=False,
        base_url=True,
        system_prompt="preamble",
        experimental=True,
    )
    passthrough_env: ClassVar[tuple[str, ...]] = (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
    )
    credential_env_names: ClassVar[tuple[str, ...]] = ("DEEPSEEK_API_KEY",)

    def validate(self, spec: AgentSpec) -> list[str]:
        """Reject unsupported external MCP mapping instead of silently dropping it."""
        return (
            ["deepseek-harness managed MCP configuration is not supported"]
            if spec.mcp_servers
            else []
        )

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Return a fresh committed-step parser."""
        return DeepSeekHarnessParser()

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """Select a model through the native profile overlay; secrets remain in env."""
        spec = ctx.spec
        patch = [
            {
                "id": "agent-default-model",
                "config": {
                    "provider": "deepseek-official",
                    "model": spec.model or "deepseek-flash",
                },
            }
        ]
        path = os.path.join(ctx.turn_dir, "dsh.patch.yml")
        modes = {
            "read_only": "read-only",
            "workspace_write": "workspace-write",
            "full_access": "danger-full-access",
        }
        argv = [
            "dsh",
            "--profile",
            "headless",
            "--patch",
            path,
            "--json",
            "--permission-mode",
            modes[spec.permissions],
            "--approval-policy",
            "never",
        ]
        if ctx.native_session_id:
            argv += ["--session-id", ctx.native_session_id]
        argv += list(spec.extra_args) + ["-"]
        env = {
            "DSH_HOME": os.path.join(ctx.workdir, ".agent-sandbox", "dsh"),
            "DSH_TELEMETRY_DISABLED": "1",
        }
        if spec.provider.api_key:
            env["DEEPSEEK_API_KEY"] = spec.provider.api_key
        if spec.provider.base_url:
            env["DEEPSEEK_BASE_URL"] = spec.provider.base_url
        return Invocation(
            argv=argv,
            env=env,
            stdin=self.prompt_stdin(ctx),
            files=[InvocationFile(path, json.dumps(patch).encode())],
        )
