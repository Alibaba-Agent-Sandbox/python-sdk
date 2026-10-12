"""Parser for the Claude-Code-style ``--output-format stream-json`` protocol.

Shared by the Claude Code and Qwen Code adapters (Qwen Code's headless mode
emits the same message shapes).
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any

from .. import events as ev
from .base import EventParser, classify_text

if TYPE_CHECKING:
    from ..events import ParsedEvent

__all__ = ["StreamJsonParser", "tool_event"]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return "" if content is None else str(content)


def tool_event(block: dict[str, Any]) -> ParsedEvent:
    """Build a ``tool_start`` event from a ``tool_use`` content block."""
    name = str(block.get("name") or "tool")
    args = block.get("input")
    item_id = str(block.get("id") or "")
    if name == "Bash" and isinstance(args, dict):
        return ev.tool_start(
            item_id,
            "command",
            "command_execution",
            arguments=args,
            command=str(args.get("command") or ""),
        )
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            return ev.tool_start(item_id, "mcp", parts[2], arguments=args, server=parts[1])
    return ev.tool_start(item_id, "other", name, arguments=args)


class StreamJsonParser(EventParser):
    """Parse Claude-Code-compatible stream-json lines."""

    def __init__(self) -> None:
        self._message_id: str | None = None
        # message id -> queue of streamed item ids still waiting for their final block
        self._streamed_text: dict[str, deque[str]] = defaultdict(deque)
        self._streamed_thinking: dict[str, deque[str]] = defaultdict(deque)
        self._blocks: dict[int, tuple[str, str]] = {}
        self._counter = 0
        self._seen_tools: set[str] = set()
        self._agent_tools: dict[str, dict[str, Any]] = {}
        self._subagents_seen: set[str] = set()

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}:{self._counter}"

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
        if kind in ("assistant", "user", "stream_event") and obj.get("parent_tool_use_id"):
            return self._subagent(obj)
        if kind == "system":
            if obj.get("subtype") in ("init", "session_start") and obj.get("session_id"):
                return [ev.session_event(str(obj["session_id"]))]
            return []
        if kind == "stream_event":
            return self._stream_event(obj)
        if kind == "assistant":
            return self._assistant(obj)
        if kind == "user":
            return self._user(obj)
        if kind == "result":
            return self._result(obj)
        return []

    def _subagent(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        """Events tagged with ``parent_tool_use_id`` belong to that subagent, not the parent."""
        if obj.get("type") == "stream_event":
            return []
        parent = str(obj["parent_tool_use_id"])
        meta = self._agent_tools.get(parent, {})
        common = {"name": meta.get("name"), "prompt": meta.get("prompt")}
        role = "user" if obj.get("type") == "user" else "assistant"
        content = (obj.get("message") or {}).get("content")
        out: list[ParsedEvent] = []

        def emit(entry: dict[str, Any]) -> None:
            out.append(ev.subagent("event", [parent], entry=entry, **common))

        if isinstance(content, str) and content:
            emit({"kind": "message", "role": role, "text": content})
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                emit({"kind": "message", "role": role, "text": str(block["text"])})
            elif btype == "thinking" and block.get("thinking"):
                emit({"kind": "reasoning", "role": "assistant", "text": str(block["thinking"])})
            elif btype == "tool_use":
                emit(
                    {
                        "kind": "tool_call",
                        "role": "assistant",
                        "call_id": str(block.get("id") or ""),
                        "name": str(block.get("name") or "tool"),
                        "arguments": block.get("input"),
                        "output": None,
                        "ok": None,
                    }
                )
            elif btype == "tool_result":
                emit(
                    {
                        "kind": "tool_result",
                        "call_id": str(block.get("tool_use_id") or ""),
                        "output": _content_text(block.get("content")),
                        "ok": not block.get("is_error"),
                    }
                )
        if not out:
            out.append(ev.subagent("open", [parent], **common))
        self._subagents_seen.add(parent)
        return out

    def _stream_event(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        if obj.get("parent_tool_use_id"):
            return []
        event = obj.get("event")
        if not isinstance(event, dict):
            return []
        et = event.get("type")
        if et == "message_start":
            message = event.get("message") or {}
            self._message_id = str(message.get("id") or self._next_id("msg"))
            self._blocks.clear()
            return []
        mid = self._message_id or "msg"
        index = int(event.get("index") or 0)
        if et == "content_block_start":
            block = event.get("content_block") or {}
            btype = str(block.get("type") or "")
            item_id = f"{mid}:{index}"
            self._blocks[index] = (btype, item_id)
            if btype == "text":
                self._streamed_text[mid].append(item_id)
            elif btype == "thinking":
                self._streamed_thinking[mid].append(item_id)
            return []
        if et == "content_block_delta":
            delta = event.get("delta") or {}
            btype, item_id = self._blocks.get(index, ("", f"{mid}:{index}"))
            if delta.get("type") == "text_delta" and delta.get("text"):
                return [ev.text_delta(item_id, str(delta["text"]))]
            if delta.get("type") == "thinking_delta" and delta.get("thinking"):
                return [ev.reasoning_delta(item_id, str(delta["thinking"]))]
        return []

    def _assistant(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        message = obj.get("message") or {}
        mid = str(message.get("id") or "msg")
        sub_agent = bool(obj.get("parent_tool_use_id"))
        out: list[ParsedEvent] = []
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and not sub_agent:
                queue = self._streamed_text.get(mid)
                item_id = queue.popleft() if queue else self._next_id(mid)
                out.append(ev.message(item_id, str(block.get("text") or "")))
            elif btype == "thinking" and not sub_agent:
                queue = self._streamed_thinking.get(mid)
                item_id = queue.popleft() if queue else self._next_id(mid)
                if block.get("thinking"):
                    out.append(ev.reasoning(item_id, str(block["thinking"])))
            elif btype == "tool_use":
                tool_id = str(block.get("id") or "")
                if tool_id and tool_id not in self._seen_tools:
                    self._seen_tools.add(tool_id)
                    self._note_agent_tool(tool_id, block)
                    out.append(tool_event(block))
        return out

    def _note_agent_tool(self, tool_id: str, block: dict[str, Any]) -> None:
        name = str(block.get("name") or "").lower()
        args = block.get("input")
        if name in ("agent", "task") and isinstance(args, dict):
            label = args.get("description") or args.get("subagent_type")
            prompt = args.get("prompt")
            self._agent_tools[tool_id] = {
                "name": str(label) if label else None,
                "prompt": str(prompt) if prompt else None,
            }

    def _user(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        message = obj.get("message") or {}
        content = message.get("content")
        out: list[ParsedEvent] = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    ok = not block.get("is_error")
                    text = _content_text(block.get("content"))
                    result_id = str(block.get("tool_use_id") or "")
                    if result_id in self._subagents_seen:
                        out.append(ev.subagent("close", [result_id]))
                    out.append(
                        ev.tool_end(
                            str(block.get("tool_use_id") or ""),
                            ok=ok,
                            output=text,
                            error_text=None if ok else text,
                        )
                    )
        return out

    def _result(self, obj: dict[str, Any]) -> list[ParsedEvent]:
        out: list[ParsedEvent] = []
        usage = obj.get("usage")
        if isinstance(usage, dict):
            out.append(
                ev.usage(
                    input_tokens=int(usage.get("input_tokens") or 0)
                    + int(usage.get("cache_creation_input_tokens") or 0)
                    + int(usage.get("cache_read_input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cached_tokens=int(usage.get("cache_read_input_tokens") or 0),
                    cost_usd=obj.get("total_cost_usd"),
                )
            )
        subtype = obj.get("subtype")
        text = obj.get("result")
        text = text if isinstance(text, str) else None
        ok = not obj.get("is_error") and subtype in (None, "success")
        if not ok:
            if subtype in ("error_max_turns", "error_max_budget_usd", "error_max_session_turns"):
                code = "session_budget_exceeded"
            else:
                code = classify_text(text or str(subtype or ""))
            out.append(ev.error(code, text or str(subtype or "agent error"), fatal=True))
        out.append(ev.result(ok, text, stop_reason=str(subtype) if subtype else None))
        return out
