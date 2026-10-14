"""Provider health checks: integrity, configuration and the plugin ``initialize`` handshake."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from agent_sandbox.models.errors import (
    InvalidAPIKeyError,
    InvalidCredentialsError,
    ProviderConfigError,
    SandboxError,
)
from agent_sandbox.providers import registry, store
from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


async def _close_infra(infra: Any) -> None:
    """Release whatever ``build_infra`` opened. ``close`` is optional."""
    close = getattr(infra, "close", None)
    if close is not None:
        await close()
        return
    http_client = getattr(infra, "http_client", None)
    if http_client is not None:
        await http_client.close()


async def doctor_async(provider_id: str, *, handshake: bool = True) -> dict[str, Any]:
    """Run every check for *provider_id*; never raises for provider failures.

    Returns ``{"id", "ok", "checks": [{"name", "ok", "detail"}...]}``. Plugin processes are started
    only when *handshake* is true and the configuration check passed.
    """
    from agent_sandbox.transport.config import load_config

    checks: list[dict[str, Any]] = []

    def finish() -> dict[str, Any]:
        return {"id": provider_id, "ok": all(c["ok"] for c in checks), "checks": checks}

    try:
        provider = registry.get_provider(provider_id)
        checks.append(_check("installed", True, f"{provider.display_name} {provider.version}"))
    except SandboxError as exc:
        checks.append(_check("installed", False, exc.message))
        return finish()

    receipt = store.read_receipt(provider_id) if provider_id != BUILTIN_PROVIDER_ID else None
    if receipt is not None and receipt.get("trust") != "link":
        try:
            store.verify_integrity(provider_id)
            checks.append(_check("integrity", True, str(receipt.get("tree_sha256", ""))[:16]))
        except SandboxError as exc:
            checks.append(_check("integrity", False, exc.message))
            return finish()

    try:
        config = load_config(provider=provider_id)
        provider.validate_config(config)
        checks.append(_check("config", True))
    except SandboxError as exc:
        checks.append(_check("config", False, exc.message))
        return finish()

    if handshake and provider_id != BUILTIN_PROVIDER_ID:
        try:
            infra = await provider.build_infra(config)
        except (InvalidAPIKeyError, InvalidCredentialsError, ProviderConfigError) as exc:
            # Install must succeed before the operator has a key. Create reports this.
            checks.append(_check("config", False, exc.message))
            return finish()
        except SandboxError as exc:
            checks.append(_check("handshake", False, exc.message))
            return finish()
        try:
            checks.append(_check("handshake", True))
        finally:
            await _close_infra(infra)
    return finish()


def doctor(provider_id: str, *, handshake: bool = True) -> dict[str, Any]:
    """Synchronous wrapper around :func:`doctor_async` (safe inside a running event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(doctor_async(provider_id, handshake=handshake))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            lambda: asyncio.run(doctor_async(provider_id, handshake=handshake))
        ).result()


def verify_handshake(provider_id: str) -> None:
    """``verify`` callback for install/update: raise when the plugin fails to start."""
    from agent_sandbox.models.errors import ProviderInstallError

    registry.forget(provider_id)
    report = doctor(provider_id)
    for check in report["checks"]:
        if check["name"] in ("installed", "integrity", "handshake") and not check["ok"]:
            raise ProviderInstallError(
                f"Provider '{provider_id}' failed {check['name']}: {check['detail']}"
            )
