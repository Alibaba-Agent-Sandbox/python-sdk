"""Express creation uses its engine; the public Sandbox never selects this transport."""

from __future__ import annotations

import contextlib
from typing import Any


class EngineLifecycle:
    def __init__(self, http: Any, config: Any) -> None:
        from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol

        self.native = SandboxProtocol(http)
        self.config = config

    def __getattr__(self, name: str) -> Any:
        return getattr(self.native, name)

    async def create(self, config: Any, *, request_timeout: float | None = None) -> Any:
        from agent_sandbox.engine.client import Engine

        return await Engine().create(
            config.template,
            provider=self.config.provider,
            timeout=config.timeout,
            metadata=config.metadata,
            envs=config.env_vars,
            api_key=self.config.sandbox_api_key,
            api_url=self.config.sandbox_base_url,
            access_key_id=self.config.access_key_id,
            access_key_secret=self.config.access_key_secret,
            region=self.config.region,
            request_timeout=request_timeout,
            cpu=config.cpu,
            memory=config.memory,
            disk=config.disk,
            gpu=config.gpu,
            **({"volume_mounts": config.volume_mounts} if config.volume_mounts else {}),
        )

    async def kill(self, sandbox_id: str) -> None:
        from agent_sandbox.engine.client import Engine

        try:
            await self.native.kill(sandbox_id)
        finally:
            with contextlib.suppress(Exception):
                await Engine().op("release", sandbox_id=sandbox_id)
