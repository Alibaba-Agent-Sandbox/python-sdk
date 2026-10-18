"""Express control-plane and session assembly for the generic local engine."""

from __future__ import annotations

import inspect
from typing import Any

from agent_sandbox.providers.engine_contract import Session


def _opt(value: str) -> str | None:
    return value or None


async def _close(http: Any) -> None:
    result = http.close()
    if inspect.isawaitable(result):
        await result


async def create_engine_session(request: Any) -> tuple[Any, Session]:
    from agent_sandbox.models.sandbox import SandboxConfig

    from .provider import AlicloudExpressProvider

    _build_infra = AlicloudExpressProvider().build_legacy_infra
    from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
    from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol
    from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
    from agent_sandbox.transport.http import stream_envelope_for_envd

    sandbox_config = SandboxConfig.model_validate(
        {
            "template": request.template or "base",
            "timeout": request.timeout or 300,
            "metadata": dict(request.metadata),
            "env_vars": dict(request.envs),
            "cpu": request.cpu or None,
            "memory": request.memory or None,
            "disk": request.disk or None,
            "gpu": request.gpu or None,
            "volume_mounts": dict(getattr(request, "volume_mounts", {})),
        }
    )
    _config, _auth, http_client, protocol = _build_infra(
        api_key=_opt(request.api_key),
        api_url=_opt(request.api_url),
        access_key_id=_opt(request.access_key_id),
        access_key_secret=_opt(request.access_key_secret),
        region=_opt(request.region),
    )
    try:
        info = await protocol.create(
            sandbox_config,
            request_timeout=request.request_timeout or None,
        )
    except Exception:
        await _close(http_client)
        raise
    if not info.envd_url and info.sandbox_id:
        info.envd_url = _config.build_envd_url(info.sandbox_id)
    http_client._stream_envelope = stream_envelope_for_envd(info.envd_version)
    token = EnvdTokenManager(info.envd_access_token, sandbox_id=info.sandbox_id)
    from agent_sandbox.providers.shared.e2b.engine_terminal import stream_terminal

    session = Session(
        sandbox_id=info.sandbox_id,
        provider="alicloud-express",
        envd_url=info.envd_url or "",
        token=token,
        http=http_client,
        process=ProcessProtocol(http_client),
        files=FilesystemProtocol(http_client),
        sandbox_protocol=protocol,
        terminal=stream_terminal,
    )
    return info, session


async def kill_engine_resource(request: Any) -> None:
    from .provider import AlicloudExpressProvider

    config, auth, http, protocol = AlicloudExpressProvider().build_legacy_infra(
        api_key=_opt(request.api_key),
        api_url=_opt(request.api_url),
        access_key_id=_opt(request.access_key_id),
        access_key_secret=_opt(request.access_key_secret),
        region=_opt(request.region),
    )
    try:
        await protocol.kill(request.sandbox_id)
    finally:
        await _close(http)
