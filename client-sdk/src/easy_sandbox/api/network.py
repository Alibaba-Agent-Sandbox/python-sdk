"""网络模块 — 端口 URL 计算和访问。

端口 URL 由客户端本地计算，格式为：https://{port}-{sandbox_id}.{domain}
其中 sandbox_id 已包含 "sbx-" 前缀（如 "sbx-xxxx"）。
不需要服务端 API 调用。secure 模式下端口访问需要 X-Access-Token header。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easy_sandbox.models.template import DEFAULT_CAPABILITIES
from easy_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger("api.network")


class NetworkModule:
    """高层网络接口 — 端口 URL 计算和访问 header 管理。

    所有方法均为本地计算，不涉及任何网络请求。
    端口 URL 格式参见官方文档端口访问说明。
    """

    def __init__(
        self,
        sandbox_id: str,
        domain: str,
        secure: bool = True,
        access_token: str | None = None,
        capabilities: set[str] | None = None,
        port_resolver: Callable[[int], Awaitable[tuple[str, dict[str, str]]]] | None = None,
    ) -> None:
        self._port_resolver = port_resolver
        self._sandbox_id = sandbox_id
        self._domain = domain
        self._secure = secure
        self._access_token = access_token
        self._capabilities = capabilities if capabilities is not None else set(DEFAULT_CAPABILITIES)

    def get_host(self, port: int) -> str:
        """获取端口访问的 host。

        格式：{port}-{sandbox_id}.{domain}
        其中 sandbox_id 已包含 "sbx-" 前缀。
        """
        return f"{port}-{self._sandbox_id}.{self._domain}"

    def get_url(self, port: int) -> str:
        """获取端口访问的完整 URL。

        格式：https://{port}-{sandbox_id}.{domain}（secure 模式）
        或 http://{port}-{sandbox_id}.{domain}（非 secure 模式）
        """
        scheme = "https" if self._secure else "http"
        return f"{scheme}://{self.get_host(port)}"

    def get_access_headers(self) -> dict[str, str]:
        """获取端口访问所需的 HTTP headers。

        secure 模式下需要 X-Access-Token header。
        """
        if self._secure and self._access_token:
            return {"X-Access-Token": self._access_token}
        return {}

    async def resolve(self, port: int) -> tuple[str, dict[str, str]]:
        """Return ``(url, headers)`` for *port*, asking the provider when it can answer.

        Providers that declare ``ports.url`` (plugin ``ports.url`` method) are asked for the
        authoritative URL and access headers; everything else falls back to the local
        computation of :meth:`get_url` / :meth:`get_access_headers`.
        """
        if self._port_resolver is not None:
            return await self._port_resolver(port)
        return self.get_url(port), self.get_access_headers()

    async def resolve_url(self, port: int) -> str:
        """Like :meth:`get_url`, but routed through the provider's ``ports.url`` when declared."""
        return (await self.resolve(port))[0]
