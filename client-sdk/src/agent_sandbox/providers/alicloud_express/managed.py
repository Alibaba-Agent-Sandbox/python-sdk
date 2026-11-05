"""Explicit managed Express lifecycle; no ambient provider discovery."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from agent_sandbox.managed_agents.models import ManagedError

if TYPE_CHECKING:
    from collections.abc import Callable


class ExpressBackend:
    """Create only owned Express sandboxes using fully resolved service configuration."""

    def __init__(self, provider: dict[str, Any], model: dict[str, Any] | None = None) -> None:
        if (
            set(provider) != {"provider", "apiKey", "baseUrl", "domain", "region"}
            or provider["provider"] != "alicloud-express"
        ):
            raise ValueError(
                "Explicit Express provider, Key, API URL, domain and region are required"
            )
        if model is not None and (
            set(model) != {"apiKey", "baseUrl", "model", "adapter"}
            or model["adapter"] not in {"codex", "qwen-code"}
        ):
            raise ValueError("Explicit model credentials, endpoint, model and adapter are required")
        if any(
            not isinstance(v, str) or not v.strip()
            for v in (*provider.values(), *(model or {}).values())
        ):
            raise ValueError("Service credentials and endpoint values cannot be empty")
        for url in [provider["baseUrl"], *([model["baseUrl"]] if model else [])]:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
            ):
                raise ValueError(
                    "Service endpoints must be explicit HTTPS URLs without embedded credentials"
                )
        self.provider, self.model = dict(provider), dict(model) if model else None

    async def _infra(self) -> Any:
        from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider
        from agent_sandbox.transport.config import TransportConfig

        # Construct the immutable value directly; do not call load_config or
        # discover a provider from environment/CWD/HOME/global entrypoints.
        config = TransportConfig(
            provider="alicloud-express",
            sandbox_api_key=self.provider["apiKey"],
            sandbox_base_url=self.provider["baseUrl"],
            sandbox_domain=self.provider["domain"],
            region=self.provider["region"],
            access_key_id=None,
            access_key_secret=None,
            security_token=None,
            http_timeout=30,
            provider_options={},
        )
        return await AlicloudExpressProvider().build_infra(config)

    async def create(
        self, session: dict[str, Any], token: str, on_created: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]:
        """Prepare native lifecycle and app/gateway auth, persisting ownership immediately."""
        from agent_sandbox.models.sandbox import SandboxConfig
        from agent_sandbox.protocol.port_contract import PortContext
        from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider

        if (
            self.model is None
            or session["agent"]["model"] != self.model["model"]
            or session["agent"]["x_agent_sandbox"]["adapter"] != self.model["adapter"]
        ):
            raise ManagedError(
                400, "model_binding_mismatch", "This Worker has no matching model binding"
            )
        settings = session["_settings"]
        if set(settings.get("modelEnvAllowlist", [])) != {
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
        }:
            raise ManagedError(
                400, "model_env_not_allowed", "Required model variables are not allowed"
            )
        infra = await self._infra()
        try:
            config = SandboxConfig(
                templateID=settings["template"],
                timeout=settings["sessions"]["maxLifetimeSeconds"],
                secure=True,
                metadata={
                    "abx-managed": "true",
                    "abx-session": session["id"],
                    "abx-revision": session["_revision"],
                },
                envVars={
                    "ABX_SERVER_TOKEN": token,
                    "ABX_MANAGED_WORKSPACE": settings["workspace"],
                    "OPENAI_API_KEY": self.model["apiKey"],
                    "OPENAI_BASE_URL": self.model["baseUrl"],
                    "OPENAI_MODEL": self.model["model"],
                },
            )
            info = await infra.sandbox_protocol.create(config, request_timeout=30)
            resource = {"sandbox_id": info.sandbox_id, "token": token, "ownership": "owned"}
            on_created(resource)
            context = PortContext(
                info.sandbox_id,
                self.provider["domain"],
                True,
                info.envd_access_token,
                info.traffic_access_token,
            )
            endpoint = await AlicloudExpressProvider().application_endpoint(
                context, settings["port"]
            )
            resource.update(url=endpoint["url"], headers=endpoint["headers"])
            on_created(resource)
            provider = AlicloudExpressProvider()
            binding = await provider.prepare_session(
                infra, info, operation="create", template=settings["template"]
            )
            process_env = {
                **config.env_vars,
                "ABX_MANAGED_PORT": str(settings["port"]),
                "ABX_MANAGED_STATE_DIR": "/home/user/.agent-sandbox/managed-bridge",
            }
            # Fixed trusted bootstrap, with all instance credentials in env only.
            # A prepared template does not imply a running application process.
            script = (
                'umask 077; mkdir -p "$ABX_MANAGED_STATE_DIR" "$ABX_MANAGED_WORKSPACE"; '
                'nohup python3 -m agent_sandbox.server.managed --port "$ABX_MANAGED_PORT" '
                '>"$ABX_MANAGED_STATE_DIR/bridge.log" 2>&1 </dev/null &'
            )
            reader = await infra.process_protocol.start(
                provider.resolve_session_url(info, infra.config),
                binding["envd_token"],
                cmd="/bin/sh",
                args=["-c", script],
                env=process_env,
                user="user",
                timeout=15,
            )
            acknowledged = False
            try:
                async for chunk in reader:
                    if chunk.pid:
                        acknowledged = True
                    if chunk.exit_code is not None and chunk.exit_code != 0:
                        raise ManagedError(
                            503, "bridge_bootstrap_failed", "The private runtime could not start"
                        )
            finally:
                await reader.cancel()
            if not acknowledged:
                raise ManagedError(
                    503,
                    "bridge_bootstrap_unconfirmed",
                    "Private runtime startup was not acknowledged",
                )
            return resource
        finally:
            await infra.http_client.close()

    async def kill(self, resource: dict[str, Any]) -> bool:
        """Delete only a recorded owned Sandbox and independently confirm NotFound."""
        from agent_sandbox.models.errors import SandboxNotFoundError

        if resource.get("ownership") != "owned" or not resource.get("sandbox_id"):
            return False
        infra = await self._infra()
        try:
            with contextlib.suppress(SandboxNotFoundError):
                await infra.sandbox_protocol.kill(resource["sandbox_id"])
            try:
                await infra.sandbox_protocol.get_info(resource["sandbox_id"])
            except SandboxNotFoundError:
                return True
            return False
        finally:
            await infra.http_client.close()
