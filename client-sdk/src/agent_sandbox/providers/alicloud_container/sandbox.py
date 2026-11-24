"""Sandbox-manager lifecycle and gateway routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from agent_sandbox.models.errors import (
    NetworkError,
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderProtocolError,
    QuotaExceededError,
    SandboxCreationError,
    SandboxNotFoundError,
    TemplateNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxInfo, SandboxStatus
from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol
from agent_sandbox.providers.shared.e2b.url import ENVD_PORT

if TYPE_CHECKING:
    from agent_sandbox.models.sandbox import SandboxConfig
    from agent_sandbox.protocol.port_contract import PortContext
    from agent_sandbox.transport.http import HttpClient

PROVIDER_ID = "alicloud-container"
_TRAFFIC_HEADER = "e2b-traffic-access-token"
_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")


def _valid_id(value: str) -> str:
    if _ID.fullmatch(value) is None:
        raise ProviderConfigError("Container Edition requires a DNS-label sandbox ID.")
    return value


@dataclass(frozen=True)
class Gateway:
    api: str
    domain: str
    private_root: str | None = None

    def url(self, sandbox_id: str, port: int) -> str:
        _valid_id(sandbox_id)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Port must be an integer from 1 through 65535.")
        if self.private_root is not None:
            return f"{self.private_root}/kruise/{sandbox_id}/{port}"
        return f"https://{port}-{sandbox_id}.{self.domain}"


@dataclass(frozen=True)
class PortAccess:
    gateway: Gateway
    context: PortContext

    def get_host(self, port: int) -> str:
        return urlsplit(self.get_url(port)).netloc

    def get_url(self, port: int) -> str:
        return self.gateway.url(self.context.sandbox_id, port)

    def get_access_headers(self) -> dict[str, str]:
        if self.context.traffic_access_token:
            return {_TRAFFIC_HEADER: self.context.traffic_access_token}
        if self.context.access_token:
            return {"X-Access-Token": self.context.access_token}
        return {}

    get_server_headers = get_access_headers


class ContainerToken(EnvdTokenManager):
    """Keep gateway and runtime credentials scoped to one sandbox handle."""

    def __init__(self, info: SandboxInfo) -> None:
        super().__init__(info.envd_access_token, info.sandbox_id, allow_missing=True)
        self.traffic_token = info.traffic_access_token
        self._routing_id = info.sandbox_id

    def get_headers(self) -> dict[str, str]:
        headers = super().get_headers()
        headers["E2b-Sandbox-Id"] = self._routing_id
        if self.traffic_token:
            headers[_TRAFFIC_HEADER] = self.traffic_token
        return headers


class ContainerSandboxProtocol(SandboxProtocol):
    def __init__(self, http: HttpClient, gateway: Gateway) -> None:
        super().__init__(http, unknown_if_absent=True)
        self.gateway = gateway
        self._token: ContainerToken | None = None

    def _info(self, data: Any) -> SandboxInfo:
        if not isinstance(data, dict):
            raise ProviderProtocolError("Container Edition returned an invalid sandbox object.")
        data = dict(data)
        for field in ("startedAt", "endAt"):
            if data.get(field) in ("", "<unknown>"):
                data[field] = None
        if "metadata" in data and data["metadata"] is None:
            data["metadata"] = {}
        data["envdUrl"] = None
        try:
            info = super()._info(data)
            info.model_fields_set.difference_update({"region", "timeout"} - data.keys())
            # Use the bound gateway even if a response advertises another data-plane URL.
            info.envd_url = self.gateway.url(info.sandbox_id, ENVD_PORT)
        except (ValidationError, ProviderConfigError):
            raise ProviderProtocolError(
                "Container Edition returned invalid sandbox data."
            ) from None
        return info

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise ProviderProtocolError("Container Edition returned invalid JSON.") from None

    async def prepare_session(self, info: SandboxInfo) -> dict[str, Any]:
        self._token = ContainerToken(info)
        return {"envd_token": self._token}

    def create_port_access(self, context: PortContext) -> PortAccess:
        return PortAccess(self.gateway, context)

    async def create(
        self, config: SandboxConfig, *, request_timeout: float | None = None
    ) -> SandboxInfo:
        for key in ("cpu", "memory", "disk", "gpu", "secure", "network", "allow_internet_access"):
            if getattr(config, key) is not None:
                raise ProviderFeatureNotSupportedError(PROVIDER_ID, f"sandbox.create.{key}")
        if config.volume_mounts:
            raise ProviderFeatureNotSupportedError(PROVIDER_ID, "storage.mount")
        if not config.template.strip():
            raise ProviderConfigError("Specify the name of an existing SandboxSet.")
        try:
            response = await self._http.platform_request(
                "POST",
                "/sandboxes",
                json=config.to_create_payload(),
                request_timeout=request_timeout,
            )
            return self._info(self._json(response))
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404:
                raise TemplateNotFoundError("Container Edition SandboxSet was not found.") from None
            if status == 429:
                raise QuotaExceededError(
                    "Container Edition creation reached a quota limit."
                ) from None
            if status < 500:
                raise SandboxCreationError(
                    f"Container Edition creation was rejected (HTTP {status})."
                ) from None
        except (httpx.TransportError, NetworkError, ProviderProtocolError):
            pass
        error = ProviderProtocolError(
            "Container Edition creation did not return a valid receipt. "
            "Check the cluster before retrying."
        )
        error.outcome = "unknown_outcome"  # type: ignore[attr-defined]
        raise error

    async def _sandbox_request(
        self, method: str, sandbox_id: str, suffix: str = "", **kwargs: Any
    ) -> httpx.Response:
        return await super()._sandbox_request(method, _valid_id(sandbox_id), suffix, **kwargs)

    async def kill(self, sandbox_id: str) -> None:
        await super().kill(_valid_id(sandbox_id))

    def _matching_info(self, data: Any, sandbox_id: str) -> SandboxInfo:
        info = self._info(data)
        if info.sandbox_id != sandbox_id:
            raise ProviderProtocolError("Container Edition returned a different sandbox identity.")
        if self._token is not None and "traffic_access_token" in info.model_fields_set:
            self._token.traffic_token = info.traffic_access_token
        return info

    async def get_info(self, sandbox_id: str) -> SandboxInfo:
        response = await self._sandbox_request("GET", sandbox_id)
        return self._matching_info(self._json(response), sandbox_id)

    async def connect(self, sandbox_id: str) -> SandboxInfo:
        path = f"/sandboxes/{_valid_id(sandbox_id)}/connect"
        try:
            response = await self._http.platform_request("POST", f"/v2{path}", json={})
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # Go's mux returns a plain 404 for an absent route. A sandbox-level
            # 404 returns a structured error; do not replay there.
            if status == 405 or (
                status == 404 and exc.response.text.strip() == "404 page not found"
            ):
                response = await self._sandbox_request(
                    "POST", sandbox_id, "/connect", json={"timeout": 300}
                )
            elif status == 404:
                raise SandboxNotFoundError("Container Edition sandbox was not found.") from None
            else:
                raise
        if response.status_code == 204:
            return await self.get_info(sandbox_id)
        return self._matching_info(self._json(response), sandbox_id)

    async def resume(self, sandbox_id: str) -> SandboxInfo:
        return await self.connect(sandbox_id)

    async def list(
        self, *, status: SandboxStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[SandboxInfo]:
        if offset:
            raise ProviderFeatureNotSupportedError(PROVIDER_ID, "sandbox.list.offset")
        if not 1 <= limit <= 100:
            raise ValueError("Container Edition list limit must be from 1 through 100.")
        params: dict[str, Any] = {"limit": limit}
        if status is not None:
            if status not in (SandboxStatus.RUNNING, SandboxStatus.PAUSED):
                raise ValueError("Container Edition sandbox state must be running or paused.")
            params["state"] = status.value
        response = await self._http.platform_request("GET", "/v2/sandboxes", params=params)
        data = self._json(response)
        if isinstance(data, dict):
            data = data.get("sandboxes", data.get("data"))
        if not isinstance(data, list):
            raise ProviderProtocolError("Container Edition returned an invalid sandbox list.")
        return [self._info(item) for item in data]

    list_v2 = list
