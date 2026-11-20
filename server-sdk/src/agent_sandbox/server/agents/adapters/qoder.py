"""Qoder native headless adapter; PAT authentication is separate from model API keys."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .. import events as ev
from .base import AdapterCapabilities, AgentAdapter, EventParser, Invocation, TurnContext
from .stream_json import StreamJsonParser

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = ["QoderAdapter", "QoderParser"]


class QoderParser(StreamJsonParser):
    """Use Qoder's native message envelope and require its terminal result."""

    def __init__(self) -> None:
        super().__init__()
        self.terminal = False

    def feed(self, line: str) -> list[ParsedEvent]:
        """Preserve native parser results and remember terminal delivery."""
        events = super().feed(line)
        self.terminal = self.terminal or any(event.kind == "result" for event in events)
        return events

    def finish(self, returncode: int | None) -> list[ParsedEvent]:
        """Do not infer success from an empty successful process exit."""
        return [] if self.terminal else [ev.result(False, "Qoder ended without result")]


class QoderAdapter(AgentAdapter):
    """Run Qoder's structured one-shot command and restore its native session."""

    name: ClassVar[str] = "qoder"
    aliases: ClassVar[tuple[str, ...]] = ("qodercli",)
    binary: ClassVar[str] = "qoder"
    install_steps: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("npm", "install", "-g", "@qoder-ai/qodercli@1.1.90"),
    )
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=True,
        mcp=False,
        base_url=False,
        system_prompt="flag",
        max_turns=False,
        experimental=True,
    )
    prompt_transport: ClassVar[str] = "argv"
    passthrough_env: ClassVar[tuple[str, ...]] = ("QODER_PERSONAL_ACCESS_TOKEN",)
    credential_env_names: ClassVar[tuple[str, ...]] = ("QODER_PERSONAL_ACCESS_TOKEN",)

    def validate(self, spec: AgentSpec) -> list[str]:
        """Reject unimplemented BYOK/MCP configuration instead of ignoring it."""
        problems = []
        if spec.provider.base_url:
            problems.append("qoder uses native PAT authentication, not provider.base_url")
        if spec.limits.max_turns:
            problems.append("qoder 1.1.90 does not expose a max-turns flag")
        if spec.mcp_servers:
            problems.append("qoder managed MCP configuration is not supported")
        return problems

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Read Qoder's stream-json message envelope."""
        return QoderParser()

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """Keep the PAT in the child environment and use exact session continuation."""
        spec = ctx.spec
        argv = ["qoder", "--print", "--output-format", "stream-json"]
        if ctx.native_session_id:
            argv += ["--resume", ctx.native_session_id]
        if spec.model:
            argv += ["--model", spec.model]
        modes = {
            "read_only": "dont_ask",
            "workspace_write": "accept_edits",
            "full_access": "bypass_permissions",
        }
        argv += ["--permission-mode", modes[spec.permissions]]
        if spec.instructions:
            argv += ["--append-system-prompt", spec.instructions]
        if spec.permissions == "read_only":
            argv += ["--tools", "Read,Glob,Grep", "--strict-mcp-config"]
        argv += list(spec.extra_args) + [self.prompt_argv_value(ctx)]
        env = (
            {"QODER_PERSONAL_ACCESS_TOKEN": spec.provider.api_key} if spec.provider.api_key else {}
        )
        return Invocation(argv=argv, env=env)
