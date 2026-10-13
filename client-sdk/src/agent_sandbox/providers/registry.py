"""Provider registry: built-in, SDK-registered, entry-point and installed providers."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from agent_sandbox.models.errors import ProviderConflictError, ProviderNotFoundError
from agent_sandbox.providers import store
from agent_sandbox.providers.base import Provider, ordered_features
from agent_sandbox.providers.builtin import AlicloudExpressProvider
from agent_sandbox.utils.config_keys import (
    BUILTIN_PROVIDER_ID,
    validate_provider_id,
)
from agent_sandbox.utils.logging import get_logger

logger = get_logger("providers.registry")

ENTRY_POINT_GROUP = "agent_sandbox.providers"

_lock = threading.Lock()
_registered: dict[str, Provider] = {}
_builtin: AlicloudExpressProvider | None = None
_entry_points_loaded = False
_entry_point_providers: dict[str, Provider] = {}


def builtin_provider() -> AlicloudExpressProvider:
    global _builtin
    if _builtin is None:
        _builtin = AlicloudExpressProvider()
    return _builtin


def register_provider(provider: Provider, *, replace: bool = False) -> Provider:
    """Register an SDK-side (Python) provider object under ``provider.id``."""
    problem = validate_provider_id(provider.id)
    if problem:
        raise ProviderConflictError(f"Cannot register provider '{provider.id}': {problem}.")
    with _lock:
        if provider.id in _registered and not replace:
            raise ProviderConflictError(f"Provider id '{provider.id}' is already registered.")
        _registered[provider.id] = provider
    return provider


def unregister_provider(provider_id: str) -> None:
    with _lock:
        _registered.pop(provider_id, None)


def forget(provider_id: str) -> None:
    """Drop cached state about *provider_id* (after uninstall)."""
    unregister_provider(provider_id)


def reset_registry() -> None:
    """Forget every registered/entry-point provider (tests)."""
    global _entry_points_loaded
    with _lock:
        _registered.clear()
        _entry_point_providers.clear()
        _entry_points_loaded = False


def _load_entry_points() -> None:
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # pragma: no cover - metadata failures are non-fatal
        return
    for ep in eps:
        try:
            obj: Any = ep.load()
            provider = obj() if callable(obj) and not isinstance(obj, Provider) else obj
            if isinstance(provider, Provider) and not validate_provider_id(provider.id):
                _entry_point_providers[provider.id] = provider
            else:
                logger.warning("Entry point %s did not yield a valid Provider", ep.name)
        except Exception as exc:
            logger.warning("Failed to load provider entry point %s: %s", ep.name, exc)


def plugin_root(provider_id: str, receipt: dict[str, Any]) -> Path:
    if receipt.get("trust") == "link":
        return Path(receipt["source"]["path"])
    return store.provider_dir(provider_id)


def load_installed(provider_id: str) -> Provider:
    """Build a provider object from the store (verifies the receipt, not the tree digest)."""
    from agent_sandbox.providers.exec_provider import ExecProvider
    from agent_sandbox.providers.manifest import load_manifest
    from agent_sandbox.providers.rest_provider import RestProvider

    receipt = store.read_receipt(provider_id)
    if receipt is None:
        raise ProviderNotFoundError(f"Provider '{provider_id}' is not installed.")
    root = plugin_root(provider_id, receipt)
    manifest = load_manifest(root)
    if manifest.id != provider_id:
        raise ProviderNotFoundError(f"Provider '{provider_id}' is not installed.")
    if manifest.kind == "rest":
        if receipt.get("trust") != "link":
            store.verify_integrity(provider_id)
        return RestProvider(manifest, receipt)
    return ExecProvider(manifest, root, receipt)


def get_provider(provider_id: str | None = None) -> Provider:
    """The provider object for *provider_id* (default: the configured default)."""
    if provider_id is None:
        provider_id = resolve_provider_id()
    if provider_id == BUILTIN_PROVIDER_ID:
        return builtin_provider()
    with _lock:
        if provider_id in _registered:
            return _registered[provider_id]
    _load_entry_points()
    if provider_id in _entry_point_providers:
        return _entry_point_providers[provider_id]
    if validate_provider_id(provider_id) is not None:
        raise ProviderNotFoundError(
            f"Provider '{provider_id}' is not installed.", suggestion=_hint(provider_id)
        )
    try:
        return load_installed(provider_id)
    except ProviderNotFoundError as exc:
        raise ProviderNotFoundError(
            f"Provider '{provider_id}' is not installed.", suggestion=_hint(provider_id)
        ) from exc


def _hint(wanted: str) -> str:
    import difflib

    known = [p["id"] for p in list_providers()]
    close = difflib.get_close_matches(wanted, known, n=1, cutoff=0.6)
    base = "Run 'abx provider list'; install with 'abx provider install <path-or-git-url>'."
    return f"Did you mean '{close[0]}'? {base}" if close else base


def list_providers() -> list[dict[str, Any]]:
    """Summaries of every known provider: built-in first, then others sorted by id."""
    out: list[dict[str, Any]] = [_summary(builtin_provider(), trust="builtin")]
    seen = {BUILTIN_PROVIDER_ID}
    others: list[dict[str, Any]] = []
    with _lock:
        registered = dict(_registered)
    _load_entry_points()
    for pid, prov in {**_entry_point_providers, **registered}.items():
        if pid not in seen:
            seen.add(pid)
            others.append(_summary(prov, trust="python"))
    for pid in store.list_installed_ids():
        if pid in seen:
            continue
        receipt = store.read_receipt(pid) or {}
        try:
            prov = load_installed(pid)
            summary = _summary(prov, trust=str(receipt.get("trust", "local")))
        except Exception as exc:
            summary = {
                "id": pid,
                "name": pid,
                "name_zh": "",
                "version": str(receipt.get("version", "")),
                "kind": "exec",
                "trust": str(receipt.get("trust", "local")),
                "features": [],
                "error": str(exc),
            }
        seen.add(pid)
        others.append(summary)
    others.sort(key=lambda s: s["id"])
    return out + others


def _summary(provider: Provider, *, trust: str) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.display_name,
        "name_zh": provider.display_name_zh,
        "version": provider.version,
        "kind": provider.kind,
        "trust": trust,
        "features": ordered_features(provider.features),
    }


def resolve_provider_id(explicit: str | None = None) -> str:
    """explicit > ``ABX_PROVIDER`` > ``./.env`` > ``~/.abx/.env`` > ``[core]`` > built-in."""
    from agent_sandbox.transport.config import collect_sources, select_provider_id

    overrides = {"provider": explicit} if explicit else {}
    return select_provider_id(collect_sources(overrides))


def ambient_provider_id() -> str:
    """The configured default, ignoring any explicit per-call choice."""
    return resolve_provider_id(None)


def parse_sandbox_ref(ref: str) -> tuple[str | None, str]:
    """Split ``provider:sandbox_id``; the prefix counts only if it names a known provider."""
    if ":" in ref:
        prefix, _, rest = ref.partition(":")
        valid = prefix == BUILTIN_PROVIDER_ID or validate_provider_id(prefix) is None
        if rest and valid:
            try:
                get_provider(prefix)
            except ProviderNotFoundError:
                return None, ref
            return prefix, rest
    return None, ref


def qualify(provider_id: str, sandbox_id: str, *, ambient: str | None = None) -> str:
    """Printable sandbox reference (design §7.7): bare only in the legacy single-provider case."""
    ambient = ambient if ambient is not None else ambient_provider_id()
    if provider_id == BUILTIN_PROVIDER_ID and ambient == BUILTIN_PROVIDER_ID:
        return sandbox_id
    return f"{provider_id}:{sandbox_id}"
