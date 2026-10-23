"""Code Interpreter 协议层。

注意：当前实现基于 E2B SDK 逆向推断，阿里云官方文档未公开
Code Interpreter 的底层传输细节。需实测验证。

Uses Connect RPC over HTTP with application/connect+json content type.

RPC endpoints:
- /code.CodeInterpreter/Execute — Execute code in a context
- /code.CodeInterpreter/CreateContext — Create an execution context
- /code.CodeInterpreter/ListContexts — List execution contexts
- /code.CodeInterpreter/RestartContext — Restart an execution context
- /code.CodeInterpreter/RemoveContext — Remove an execution context
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError
from agent_sandbox.transport.codec import ConnectCodec
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
    from agent_sandbox.transport.http import HttpClient

logger = get_logger("protocol.code_interpreter")

# Extra seconds added to the caller-supplied timeout to derive the HTTP read
# timeout.  Mirrors the constant in protocol.process.
_HTTP_TIMEOUT_BUFFER: float = 5.0

_codec = ConnectCodec()

# RPC paths — 注意：路径基于 E2B SDK 逆向推断，未经官方文档确认
_EXECUTE = _codec.build_rpc_path("code", "CodeInterpreter", "Execute")
_CREATE_CONTEXT = _codec.build_rpc_path("code", "CodeInterpreter", "CreateContext")
_LIST_CONTEXTS = _codec.build_rpc_path("code", "CodeInterpreter", "ListContexts")
_RESTART_CONTEXT = _codec.build_rpc_path("code", "CodeInterpreter", "RestartContext")
_REMOVE_CONTEXT = _codec.build_rpc_path("code", "CodeInterpreter", "RemoveContext")


class CodeInterpreterProtocol:
    """Code Interpreter Connect RPC 协议客户端。

    注意：当前实现基于 E2B SDK 逆向推断，阿里云官方文档未公开
    Code Interpreter 的底层传输细节。所有 RPC 路径和请求/响应格式
    均需实测验证。
    """

    def __init__(
        self,
        http_client: HttpClient,
        *,
        operations: frozenset[str] = frozenset(),
        provider_id: str = "unknown",
    ) -> None:
        self._http = http_client
        self.operations = operations
        self._provider_id = provider_id

    def _require(self, operation: str) -> None:
        if operation not in self.operations:
            raise ProviderFeatureNotSupportedError(self._provider_id, operation)

    async def run_code(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        code: str,
        language: str = "python",
        context_id: str | None = None,
        mode: Literal["stateless", "default-context"] = "stateless",
        timeout: int = 30,
        envs: dict[str, str] | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        """执行代码。对应官方 sandbox.runCode() / sandbox.run_code()。

        POST envd_url + /code.CodeInterpreter/Execute (Connect unary)
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认

        Unary transport has no incremental event stream. Callback requests fail
        before I/O; this wire adapter owns temporary contexts for stateless calls.
        """
        if mode not in {"stateless", "default-context"}:
            raise ValueError("mode must be stateless or default-context")
        if context_id:
            self._require("code.context.execute")
        elif mode == "default-context":
            self._require("code.default-context.execute")
        else:
            self._require("code.execute")
        if on_stdout or on_stderr or on_result:
            raise ProviderFeatureNotSupportedError(self._provider_id, "code.stream")
        owned_context: str | None = None
        if not context_id and mode == "stateless":
            created = await self._http.envd_request(
                envd_url,
                _CREATE_CONTEXT,
                payload={"language": language},
                envd_token=envd_token,
            )
            owned_context = created.get("contextId", created.get("id"))
            if not isinstance(owned_context, str) or not owned_context:
                raise ValueError("Interpreter returned no temporary context identity")
            context_id = owned_context
        payload: dict[str, Any] = {
            "code": code,
            "language": language,
            "timeout": timeout,
        }
        if context_id:
            payload["contextId"] = context_id
        if envs:
            payload["envVars"] = envs

        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        # Derive the HTTP read timeout from the code-execution timeout so
        # that long-running code is not killed by the HTTP layer's default
        # 30 s timeout before the server-side timeout fires.
        http_timeout = float(timeout) + _HTTP_TIMEOUT_BUFFER

        try:
            response = await self._http.envd_request(
                envd_url,
                _EXECUTE,
                payload=payload,
                envd_token=envd_token,
                request_timeout=http_timeout,
            )
            return response
        finally:
            if owned_context:
                await self._http.envd_request(
                    envd_url,
                    _REMOVE_CONTEXT,
                    payload={"contextId": owned_context},
                    envd_token=envd_token,
                )

    async def create_context(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        language: str = "python",
    ) -> dict[str, Any]:
        """创建执行上下文。对应官方 sandbox.createCodeContext()。

        POST envd_url + /code.CodeInterpreter/CreateContext (Connect unary)
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        """
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        self._require("code.context.create")
        response = await self._http.envd_request(
            envd_url,
            _CREATE_CONTEXT,
            payload={"language": language},
            envd_token=envd_token,
        )
        return response

    async def list_contexts(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
    ) -> list[dict[str, Any]]:
        """查询执行上下文列表。对应官方 sandbox.listCodeContexts()。

        POST envd_url + /code.CodeInterpreter/ListContexts (Connect unary)
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        """
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        self._require("code.context.list")
        response = await self._http.envd_request(
            envd_url,
            _LIST_CONTEXTS,
            payload={},
            envd_token=envd_token,
        )
        contexts = response.get("contexts", response.get("result", {}).get("contexts", []))
        return contexts  # type: ignore[no-any-return]

    async def restart_context(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        context_id: str,
    ) -> dict[str, Any]:
        """重启执行上下文。对应官方 sandbox.restartCodeContext()。

        POST envd_url + /code.CodeInterpreter/RestartContext (Connect unary)
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        """
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        self._require("code.context.restart")
        response = await self._http.envd_request(
            envd_url,
            _RESTART_CONTEXT,
            payload={"contextId": context_id},
            envd_token=envd_token,
        )
        return response

    async def remove_context(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        context_id: str,
    ) -> None:
        """删除执行上下文。对应官方 sandbox.removeCodeContext()。

        POST envd_url + /code.CodeInterpreter/RemoveContext (Connect unary)
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        """
        # 注意：RPC 路径基于 E2B SDK 逆向推断，未经官方文档确认
        self._require("code.context.delete")
        await self._http.envd_request(
            envd_url,
            _REMOVE_CONTEXT,
            payload={"contextId": context_id},
            envd_token=envd_token,
        )
