"""External model loop with remote tools and a narrow sandbox-local adapter.

No generated code is executed in this trusted process. Factories and model
implementations are trusted application code; shell/file calls target only the
exclusive sandbox returned by the deployment's sandbox factory.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import httpx

from .models import Artifact, ExecutionResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .runtime import ExecutionContext


class Model(Protocol):
    """One tool-capable model step using a Chat Completions-shaped message."""

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Return an assistant message with content and/or function tool calls."""
        ...


class ChatCompletionsModel:
    """Optional HTTP model adapter; endpoint/model/key are trusted deployment inputs.

    Redirects and environment proxy inheritance are disabled. Keys are never
    stored in snapshots, public events or exception messages by this runtime.
    """

    def __init__(self, endpoint: str, model: str, api_key: str, *, timeout: float = 60) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("The model endpoint must use HTTPS")
        self.endpoint, self.model, self._key, self.timeout = endpoint, model, api_key, timeout

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Call the configured model, with bounded response bytes and no retries."""
        async with (
            httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client,
            client.stream(
                "POST",
                self.endpoint,
                headers={"Authorization": "Bearer " + self._key},
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                },
            ) as response,
        ):
            response.raise_for_status()
            data = bytearray()
            async for part in response.aiter_bytes():
                data.extend(part)
                if len(data) > 1048576:
                    raise ValueError("Model response exceeds budget")
        value = json.loads(data)["choices"][0]["message"]
        if not isinstance(value, dict):
            raise ValueError("Model did not return an assistant message")
        return value


_TOOL_PARAMETERS: dict[str, dict[str, Any]] = {
    "shell": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"command": {"type": "string", "maxLength": 16384}},
        "required": ["command"],
    },
    "read_file": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "write_file": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string", "maxLength": 65536},
        },
        "required": ["path", "content"],
    },
    "artifact": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"path": {"type": "string"}, "name": {"type": "string"}},
        "required": ["path", "name"],
    },
}


class RemoteSandboxTools:
    """Standard async sandbox shell/files tools; never local subprocesses.

    Shell is intentionally unrestricted *inside* the exclusive sandbox. The
    workspace path constrains file convenience tools; it is not an OS boundary.
    """

    def __init__(
        self,
        sandbox: Any,
        context: ExecutionContext,
        *,
        workspace: str = "/home/user",
        tool_seconds: float = 60,
        output_bytes: int = 65536,
        allowed: frozenset[str] = frozenset({"shell", "read_file", "write_file", "artifact"}),
    ) -> None:
        if not allowed <= _TOOL_PARAMETERS.keys():
            raise ValueError("Unsupported remote tool")
        self.sandbox, self.context = sandbox, context
        self.workspace, self.tool_seconds, self.output_bytes = workspace, tool_seconds, output_bytes
        self.allowed = allowed
        self.artifacts: list[Artifact] = []

    def definitions(self) -> list[dict[str, Any]]:
        """Return only deployment-authorized function tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Run {name} in the isolated remote sandbox",
                    "parameters": _TOOL_PARAMETERS[name],
                },
            }
            for name in sorted(self.allowed)
        ]

    def _path(self, value: Any) -> str:
        if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
            raise ValueError("Invalid sandbox path")
        root, path = PurePosixPath(self.workspace), PurePosixPath(value)
        if not path.is_absolute():
            path = root / path
        if ".." in path.parts or not path.is_relative_to(root):
            raise ValueError("File tool path must be in the configured workspace")
        return str(path)

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute one bounded tool after checking current run authorization/state."""
        self.context.check()
        if name not in self.allowed or not isinstance(arguments, dict):
            raise ValueError("Tool is not authorized")
        spec = _TOOL_PARAMETERS[name]
        if set(arguments) != set(spec["required"]):
            raise ValueError("Invalid tool arguments")
        self.context.emit("tool.started", {"name": name})
        if name == "shell":
            command = arguments["command"]
            if not isinstance(command, str) or not command or len(command) > 16384:
                raise ValueError("Invalid command")
            result = await asyncio.wait_for(
                self.sandbox.commands.run(command, timeout=self.tool_seconds), self.tool_seconds + 1
            )
            output = json.dumps(
                {"stdout": result.stdout, "stderr": result.stderr, "exitCode": result.exit_code}
            )
        elif name == "write_file":
            value = arguments["content"]
            if not isinstance(value, str) or len(value.encode()) > self.output_bytes:
                raise ValueError("File write exceeds budget")
            await asyncio.wait_for(
                self.sandbox.files.write(self._path(arguments["path"]), value), self.tool_seconds
            )
            output = "written"
        else:
            # The standard read API has no bounded-range contract. Sandbox egress
            # and file sizes remain provider/account limits; reject oversized data.
            content = await asyncio.wait_for(
                self.sandbox.files.read(self._path(arguments["path"])), self.tool_seconds
            )
            if not isinstance(content, str) or len(content.encode()) > self.output_bytes:
                raise ValueError("File read exceeds budget")
            output = content
            if name == "artifact":
                title = arguments["name"]
                if not isinstance(title, str) or not title or len(title) > 256:
                    raise ValueError("Invalid artifact name")
                self.artifacts.append(Artifact(title, content.encode(), "text/plain"))
                output = "artifact captured"
        if len(output.encode()) > self.output_bytes:
            raise ValueError("Tool output exceeds budget")
        self.context.emit("tool.completed", {"name": name})
        return output


class ExternalAgentExecutor:
    """Run the model loop externally, with all untrusted operations remote.

    Sandbox creation must tag the resource with the run ID for operator cleanup
    after ambiguous creation. Each executor owns a fresh sandbox exclusively.
    """

    def __init__(
        self,
        model: Model,
        sandbox_factory: Callable[[ExecutionContext], Awaitable[Any]],
        *,
        system_prompt: str = "Use the remote sandbox tools to complete the task.",
        max_steps: int = 30,
        tools: frozenset[str] = frozenset(_TOOL_PARAMETERS),
        workspace: str = "/home/user",
        tool_seconds: float = 60,
    ) -> None:
        self.model, self.factory, self.system_prompt = model, sandbox_factory, system_prompt
        self.max_steps, self.allowed = max_steps, tools
        self.workspace, self.tool_seconds = workspace, tool_seconds
        if max_steps < 1 or max_steps > 100 or tool_seconds <= 0:
            raise ValueError("Invalid Agent step/tool budget")
        self.sandbox: Any = None
        self._creation_started = False

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Drive a finite tool loop, saving exclusive sandbox ownership first."""
        context.check()
        self._creation_started = True
        self.sandbox = await self.factory(context)
        sandbox_id = getattr(self.sandbox, "sandbox_id", None) or getattr(self.sandbox, "id", None)
        if not isinstance(sandbox_id, str) or not sandbox_id:
            raise ValueError("Sandbox factory must return an identifiable sandbox")
        context.resource(
            {"sandboxId": sandbox_id, "ownership": "exclusive", "runId": context.run_id}
        )
        remote = RemoteSandboxTools(
            self.sandbox,
            context,
            allowed=self.allowed,
            workspace=self.workspace,
            tool_seconds=self.tool_seconds,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context.prompt},
        ]
        for _ in range(self.max_steps):
            context.check()
            message = await self.model.complete(messages, remote.definitions())
            context.check()
            if message.get("role") != "assistant":
                raise ValueError("Model response must be an assistant message")
            messages.append(message)
            calls = message.get("tool_calls", [])
            if not isinstance(calls, list) or len(calls) > 16:
                raise ValueError("Invalid model tool calls")
            if not calls:
                text = message.get("content") or ""
                if not isinstance(text, str):
                    raise ValueError("Model text must be a string")
                context.emit("output.delta", {"text": text})
                return ExecutionResult(text, tuple(remote.artifacts))
            for call in calls:
                arguments = call["function"]["arguments"]
                if not isinstance(arguments, str) or len(arguments) > 131072:
                    raise ValueError("Invalid tool arguments")
                output = await remote.call(call["function"]["name"], json.loads(arguments))
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        raise ValueError("Model step budget exhausted")

    async def close(self) -> bool:
        """Kill the exclusive sandbox; uncertain creation/kill requires reconciliation."""
        if self.sandbox is None:
            return not self._creation_started
        await self.sandbox.kill()
        return True


class InSandboxAgentExecutor:
    """Narrow managed B adapter: own session, submit once, poll authoritative turns.

    This P0 adapter deliberately publishes final output only; it does not claim a
    complete relay of the local in-memory event buffer. No local endpoint proxy
    or control-plane credential is exposed to the business caller.
    """

    required_endpoints: ClassVar[frozenset[str]] = frozenset(
        {
            "agents_sessions_create",
            "agents_sessions_events_create",
            "agents_sessions_turns_list",
            "agents_sessions_items_list",
        }
    )

    def __init__(
        self,
        sandbox_factory: Callable[[ExecutionContext], Awaitable[Any]],
        *,
        runtime: str = "codex",
        poll_seconds: float = 0.5,
    ) -> None:
        self.factory, self.runtime, self.poll_seconds = sandbox_factory, runtime, poll_seconds
        self.sandbox: Any = None
        self._creation_started = False

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Create an owned core Agents session and collect its terminal output."""
        context.check()
        self._creation_started = True
        self.sandbox = await self.factory(context)
        server = self.sandbox.server
        sandbox_id = getattr(self.sandbox, "id", None)
        context.resource(
            {"sandboxId": sandbox_id, "ownership": "exclusive", "runId": context.run_id}
        )
        # Actual discovery is explicit; a declaration alone does not grant access.
        caps = await server.discover()
        if not all(caps.can(endpoint) for endpoint in self.required_endpoints):
            raise ValueError("Required core Agents endpoints are unavailable")
        async with httpx.AsyncClient(
            base_url=server.base_url,
            headers=server.auth_headers(),
            timeout=30,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            context.check()
            response = await client.post("/v1/agents/sessions", json={"runtime": self.runtime})
            response.raise_for_status()
            session_id = response.json()["id"]
            # IDs are response data; validate before incorporating them in paths.
            if not isinstance(session_id, str) or not session_id.replace("_", "").isalnum():
                raise ValueError("Invalid core session ID")
            prefix = "/v1/agents/sessions/" + session_id
            context.resource(
                {
                    "sandboxId": sandbox_id,
                    "sessionId": session_id,
                    "ownership": "exclusive",
                    "runId": context.run_id,
                }
            )
            context.check()
            response = await client.post(
                prefix + "/events",
                json={"input": context.prompt},
                headers={"Idempotency-Key": context.run_id},
            )
            response.raise_for_status()
            while True:
                context.check()
                response = await client.get(prefix + "/turns", params={"limit": 1, "order": "desc"})
                response.raise_for_status()
                turns = response.json().get("data", [])
                if turns and turns[0]["status"] in {"completed", "failed", "cancelled"}:
                    if turns[0]["status"] != "completed":
                        raise ValueError("Local Agent turn did not succeed")
                    break
                await asyncio.sleep(self.poll_seconds)
            texts: list[str] = []
            params: dict[str, str | int] = {"limit": 100, "order": "asc"}
            total_bytes = 0
            for _ in range(100):
                context.check()
                response = await client.get(prefix + "/items", params=params)
                response.raise_for_status()
                page = response.json()
                for item in page.get("data", []):
                    if item.get("type") != "message" or item.get("role") != "assistant":
                        continue
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            text_part = part.get("text", "")
                            if not isinstance(text_part, str):
                                raise ValueError("Invalid core output text")
                            total_bytes += len(text_part.encode()) + 1
                            if total_bytes > min(context.snapshot["limits"]["outputBytes"], 65536):
                                raise ValueError("Core output exceeds run budget")
                            texts.append(text_part)
                if not page.get("has_more"):
                    break
                cursor = page.get("last_id")
                if not isinstance(cursor, str) or cursor == params.get("after"):
                    raise ValueError("Invalid core items cursor")
                params["after"] = cursor
            else:
                raise ValueError("Core items exceed pagination budget")
            text = "\n".join(texts)
            context.emit("output.delta", {"text": text})
            return ExecutionResult(text)

    async def close(self) -> bool:
        """Terminate the whole exclusively owned sandbox to confirm local CLI stop."""
        if self.sandbox is None:
            return not self._creation_started
        await self.sandbox.kill()
        return True
