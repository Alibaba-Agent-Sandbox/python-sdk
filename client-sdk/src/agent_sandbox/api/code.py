"""Exact interpreter operations; missing runtimes never fall back to shell."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError
from agent_sandbox.models.process import CodeResult
from agent_sandbox.utils.async_bridge import make_sync

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from agent_sandbox.protocol.contracts import CodeInterpreterProtocol
    from agent_sandbox.transport.auth_contract import DataPlaneAuth as EnvdTokenManager


class CodeContextModule:
    """Interpreter API with separate stateless, persistent and context operations."""

    def __init__(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        code_interpreter_protocol: CodeInterpreterProtocol,
        *,
        operations: Iterable[str] = (),
        provider_id: str = "unknown",
    ) -> None:
        self._sandbox_id = sandbox_id
        self._envd_url = envd_url
        self._envd_token = envd_token
        self._code = code_interpreter_protocol
        self._operations = frozenset(operations)
        self._provider_id = provider_id

    def _require(self, operation: str) -> None:
        if operation not in self._operations:
            raise ProviderFeatureNotSupportedError(self._provider_id, operation)

    async def run(
        self,
        code: str,
        *,
        language: str = "python",
        timeout: int = 30,
        context_id: str | None = None,
        mode: Literal["stateless", "default-context"] = "stateless",
        envs: dict[str, str] | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[..., None] | None = None,
    ) -> CodeResult:
        """Execute exactly the selected mode, rejecting unsupported semantics first.

        The provider protocol implements stateless isolation without requiring
        public context-management operations from the caller.
        ``default-context`` explicitly selects the platform's persistent default.
        A supplied context ID selects ``code.context.execute``.
        """
        if mode not in {"stateless", "default-context"}:
            raise ValueError("mode must be stateless or default-context")
        if context_id is not None and (not context_id or mode != "stateless"):
            raise ValueError("context_id must be nonempty and cannot use default-context mode")
        operation = (
            "code.context.execute"
            if context_id
            else "code.default-context.execute"
            if mode == "default-context"
            else "code.execute"
        )
        self._require(operation)
        if on_stdout or on_stderr or on_result:
            self._require("code.stream")
        response = await self._code.run_code(
            self._sandbox_id,
            self._envd_url,
            self._envd_token,
            code=code,
            language=language,
            context_id=context_id,
            mode=mode,
            timeout=timeout,
            envs=envs,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_result=on_result,
        )
        result = response.get("result", response)
        return CodeResult(
            text=result.get("text", result.get("stdout", "")).strip(),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exitCode", result.get("exit_code", 0)),
            execution_time=result.get("executionTime", result.get("execution_time", 0.0)),
        )

    async def create_context(self, *, language: str = "python") -> dict[str, Any]:
        """Create an explicitly owned persistent execution context."""
        self._require("code.context.create")
        return await self._code.create_context(
            self._sandbox_id, self._envd_url, self._envd_token, language=language
        )

    async def list_contexts(self) -> list[dict[str, Any]]:
        self._require("code.context.list")
        return await self._code.list_contexts(self._sandbox_id, self._envd_url, self._envd_token)

    async def restart_context(self, context_id: str) -> dict[str, Any]:
        self._require("code.context.restart")
        return await self._code.restart_context(
            self._sandbox_id, self._envd_url, self._envd_token, context_id=context_id
        )

    async def remove_context(self, context_id: str) -> None:
        self._require("code.context.delete")
        await self._code.remove_context(
            self._sandbox_id, self._envd_url, self._envd_token, context_id=context_id
        )

    run_sync = make_sync(run)
    create_context_sync = make_sync(create_context)
    list_contexts_sync = make_sync(list_contexts)
    restart_context_sync = make_sync(restart_context)
    remove_context_sync = make_sync(remove_context)
