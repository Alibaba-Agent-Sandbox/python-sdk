"""Capability discovery for the in-sandbox SandboxServer.

:class:`ServerCapabilities` is a read-only snapshot of ``GET /capabilities``.  It answers
"may I call this endpoint, with which limits, on which paths" *before* the request is made.
The server stays authoritative: every denial is also enforced (and reported with the same typed
exceptions) on the server side, so a stale snapshot can only cause a late error, never a bypass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.models.errors import EndpointNotAvailableError, PolicyDeniedError
from agent_sandbox.models.server import EndpointInfo, EndpointPaths, PathDecision
from agent_sandbox.utils.async_bridge import make_sync

if TYPE_CHECKING:
    from agent_sandbox.api.server_client import ServerClient


class ServerCapabilities:
    """Snapshot of what the current identity may do on the sandbox server.

    Attributes:
        groups: ``{group: any endpoint of the group is enabled}``.  A derived view; the
            switch is the endpoint rule (a group is only an alias for its endpoints).
        group_summary: ``{group: {"enabled": n, "total": m}}`` endpoint counts per group.
        revision: Hash of the effective policy; compare to detect a changed configuration.
    """

    def __init__(self, document: dict[str, Any], client: ServerClient | None = None) -> None:
        self._document = document
        self._client = client
        raw_endpoints = document.get("endpoints")
        self.api_version: int = int(document.get("api_version", 0) or 0)
        self.server_version: str = str(document.get("server_version", ""))
        identity = document.get("identity") or {}
        self.identity_id: str = str(identity.get("id", "")) if isinstance(identity, dict) else ""
        self.scopes: frozenset[str] = frozenset(
            str(s) for s in (identity.get("scopes", []) if isinstance(identity, dict) else [])
        )
        policy = document.get("policy") or {}
        self.preset: str = str(policy.get("preset", "")) if isinstance(policy, dict) else ""
        self.revision: str = str(policy.get("revision", "")) if isinstance(policy, dict) else ""
        self.configured: bool = bool(policy.get("configured", False)) if policy else False
        self.warnings: list[str] = [str(w) for w in document.get("warnings", []) or []]
        groups = document.get("groups")
        self.groups: dict[str, bool] = (
            {str(k): bool(v) for k, v in groups.items()} if isinstance(groups, dict) else {}
        )
        summary = document.get("group_summary")
        self.group_summary: dict[str, dict[str, int]] = (
            {
                str(k): {"enabled": int(v.get("enabled", 0)), "total": int(v.get("total", 0))}
                for k, v in summary.items()
                if isinstance(v, dict)
            }
            if isinstance(summary, dict)
            else {}
        )
        self.endpoints: dict[str, EndpointInfo] = {}
        if isinstance(raw_endpoints, dict):
            for name, info in raw_endpoints.items():
                if isinstance(info, dict):
                    self.endpoints[str(name)] = EndpointInfo.model_validate({**info, "name": name})

    # -- queries -------------------------------------------------------------- #

    def info(self, endpoint: str) -> EndpointInfo | None:
        """The disclosed rule of *endpoint* (``None`` when the server does not know it)."""
        return self.endpoints.get(endpoint)

    def can(self, endpoint: str) -> bool:
        """Whether *endpoint* is enabled and the current identity holds its scopes.

        Endpoints the server does not list are unavailable.
        """
        info = self.endpoints.get(endpoint)
        return info is not None and info.enabled and info.allowed

    def denial(self, endpoint: str) -> str | None:
        """Why *endpoint* is unavailable (``endpoint_disabled``, ``missing_scope``, ...) or None."""
        if self.can(endpoint):
            return None
        info = self.endpoints.get(endpoint)
        if info is None:
            return "unknown_endpoint"
        if not info.enabled:
            return info.reason or "endpoint_disabled"
        return info.reason or "missing_scope"

    def rule(self, endpoint: str) -> str | None:
        """The rule code that disabled *endpoint* (``policy:groups.file_ops``, ...) or ``None``."""
        info = self.endpoints.get(endpoint)
        return info.rule if info is not None else None

    def require(self, endpoint: str) -> EndpointInfo | None:
        """Return the rule of *endpoint* or raise the typed error the server would answer with.

        Raises:
            EndpointNotAvailableError: Disabled by policy/group or unknown to this server.
            PolicyDeniedError: Enabled, but the identity lacks a required scope.
        """
        reason = self.denial(endpoint)
        if reason is None:
            return self.endpoints.get(endpoint)
        info = self.endpoints.get(endpoint)
        if reason == "missing_scope" and info is not None:
            held = ", ".join(sorted(self.scopes)) or "-"
            raise PolicyDeniedError(
                f"Endpoint '{endpoint}' needs scope(s) {', '.join(info.scopes)}; "
                f"identity {self.identity_id!r} holds: {held}",
                status_code=403,
                error_type="PolicyDenied",
                error_code="missing_scope",
                endpoint=endpoint,
                scope=info.scopes[0] if info.scopes else "",
            )
        rule = info.rule if info is not None else None
        raise EndpointNotAvailableError(
            endpoint,
            message=(
                f"Endpoint '{endpoint}' is disabled by rule {rule}"
                if rule
                else f"Server endpoint '{endpoint}' is not available on this sandbox server."
            ),
            status_code=404,
            error_code=reason,
            rule=rule or "",
        )

    def limit(self, endpoint: str, key: str, default: Any = None) -> Any:
        """A configured limit (``max_bytes``, ``timeout_seconds``, ...) or *default*."""
        info = self.endpoints.get(endpoint)
        if info is None:
            return default
        return info.limits.get(key, default)

    def param(self, endpoint: str, key: str, default: Any = None) -> Any:
        """A configured policy parameter (``overwrite``, ``shells``, ...) or *default*."""
        info = self.endpoints.get(endpoint)
        if info is None:
            return default
        return info.params.get(key, default)

    def paths(self, endpoint: str) -> EndpointPaths | None:
        """Disclosed path scoping of *endpoint* (``None`` when unscoped or unknown)."""
        info = self.endpoints.get(endpoint)
        return info.paths if info is not None else None

    def endpoints_for(self, scope: str) -> list[str]:
        """Endpoint IDs requiring *scope* (exact match), sorted."""
        return sorted(n for n, i in self.endpoints.items() if scope in i.scopes)

    def available(self) -> list[str]:
        """Sorted endpoint IDs the current identity may call."""
        return sorted(n for n, i in self.endpoints.items() if i.enabled and i.allowed)

    # -- server-authoritative path check ------------------------------------- #

    async def check_path(self, endpoint: str, path: str, op: str | None = None) -> PathDecision:
        """Ask the server whether *endpoint* may touch *path* (never touches the filesystem)."""
        if self._client is None:
            raise RuntimeError("ServerCapabilities is not bound to a ServerClient")
        return await self._client.check(endpoint, path=path, op=op)

    check_path_sync = make_sync(check_path)

    # -- misc --------------------------------------------------------------- #

    def as_dict(self) -> dict[str, Any]:
        """The raw discovery document."""
        return dict(self._document)

    def __repr__(self) -> str:
        return (
            f"ServerCapabilities(identity={self.identity_id!r}, preset={self.preset!r}, "
            f"available={len(self.available())}/{len(self.endpoints)})"
        )


__all__ = ["ServerCapabilities"]
