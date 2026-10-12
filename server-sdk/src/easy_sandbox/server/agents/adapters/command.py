"""Generic command adapter: any "prompt in, text/JSONL out" program.

Declarative configuration (``spec.command``)::

    command:
      argv: ["aider", "--message", "{prompt}", "--yes"]   # {prompt} {model} {session_id} {workdir}
      resume_argv: ["aider", "--message", "{prompt}", "--yes", "--restore-chat-history"]
      prompt: argv | stdin            # default: stdin unless {prompt} appears in argv
      parser: text | jsonl-claude | jsonl-codex | jsonl-cursor    # default: text
      binary: aider                   # for health checks (default: argv[0])
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from .. import events as ev
from .base import AdapterCapabilities, AgentAdapter, EventParser, Invocation, TurnContext
from .codex import CodexParser
from .cursor import CursorParser
from .stream_json import StreamJsonParser

if TYPE_CHECKING:
    from ..config import AgentSpec
    from ..events import ParsedEvent

__all__ = ["CommandAdapter", "TextParser"]

_PARSERS: dict[str, Any] = {
    "jsonl-claude": StreamJsonParser,
    "jsonl-codex": CodexParser,
    "jsonl-cursor": CursorParser,
}


class TextParser(EventParser):
    """Every stdout line is assistant text; the whole output is one message."""

    def __init__(self) -> None:
        self._parts: list[str] = []

    def feed(self, line: str) -> list[ParsedEvent]:
        """Collect *line* as text."""
        self._parts.append(line + "\n")
        return [ev.text_delta("text", line + "\n")]

    def finish(self, returncode: int | None) -> list[ParsedEvent]:
        """Emit the complete message and a result record."""
        text = "".join(self._parts).rstrip("\n")
        out: list[ParsedEvent] = []
        if text:
            out.append(ev.message("text", text))
        out.append(ev.result(returncode == 0, text or None))
        return out


class CommandAdapter(AgentAdapter):
    """Adapter driven entirely by ``spec.command``."""

    name: ClassVar[str] = "command"
    aliases: ClassVar[tuple[str, ...]] = ("custom",)
    binary: ClassVar[str] = ""
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        resume=False, partial_deltas=True, mcp=False, system_prompt="preamble", base_url=False
    )
    passthrough_env: ClassVar[tuple[str, ...]] = ()

    def validate(self, spec: AgentSpec) -> list[str]:
        """Check the ``command`` block."""
        problems: list[str] = []
        command = spec.command
        if not command:
            return ["command: required for runtime 'command' (argv, parser, ...)"]
        argv = command.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            problems.append("command.argv: required non-empty list of strings")
        parser = command.get("parser", "text")
        if parser != "text" and parser not in _PARSERS:
            problems.append(f"command.parser: must be one of text, {', '.join(sorted(_PARSERS))}")
        resume = command.get("resume_argv")
        if resume is not None and (
            not isinstance(resume, list) or not all(isinstance(a, str) for a in resume)
        ):
            problems.append("command.resume_argv: expected a list of strings")
        if spec.mcp_servers:
            problems.append("mcp_servers is not supported by the generic command runtime")
        return problems

    def _command(self, ctx: TurnContext) -> dict[str, Any]:
        assert ctx.spec.command is not None
        return ctx.spec.command

    def new_parser(self, ctx: TurnContext) -> EventParser:
        """Parser selected by ``command.parser``."""
        name = self._command(ctx).get("parser", "text")
        factory = _PARSERS.get(name)
        return factory() if factory else TextParser()

    def health_argv(self) -> list[str]:
        """The generic adapter has no fixed binary."""
        return []

    def build_invocation(self, ctx: TurnContext) -> Invocation:
        """Expand the argv template."""
        command = self._command(ctx)
        resume = ctx.native_session_id is not None and command.get("resume_argv")
        template: list[str] = list(command["resume_argv"] if resume else command["argv"])
        prompt = self.effective_prompt(ctx)
        values = {
            "prompt": prompt,
            "model": ctx.spec.model or "",
            "session_id": ctx.native_session_id or "",
            "workdir": ctx.workdir,
        }
        uses_argv = any("{prompt}" in part for part in template) or command.get("prompt") == "argv"
        argv = [_expand(part, values) for part in template]
        argv += list(ctx.spec.extra_args)
        if command.get("prompt") == "argv" and not any("{prompt}" in p for p in template):
            argv.append(prompt if not prompt.startswith("-") else f"Task: {prompt}")
        return Invocation(argv=argv, stdin=None if uses_argv else prompt.encode("utf-8"))


def _expand(part: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        part = part.replace("{" + key + "}", value)
    return part
