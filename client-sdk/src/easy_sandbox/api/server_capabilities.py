"""Capability discovery for the in-sandbox SandboxServer.

:class:`ServerCapabilities` is a read-only snapshot of ``GET /capabilities``.  It answers
"may I call this endpoint, with which limits, on which paths" *before* the request is made.
The server stays authoritative: every denial is also enforced (and reported with the same typed
exceptions) on the server side, so a stale snapshot can only cause a late error, never a bypass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from easy_sandbox.models.errors import EndpointNotAvailableError, PolicyDeniedError
from easy_sandbox.models.server import EndpointInfo, EndpointPaths, PathDecision
from easy_sandbox.utils.async_bridge import make_sync

if TYPE_CHECKING:
    from easy_sandbox.api.server_client import ServerClient

#: Group each endpoint belongs to (used only to gate legacy servers that disclose groups only).
ENDPOINT_GROUPS: dict[str, str] = {
    "health": "core",
    "capabilities": "core",
    "capabilities_check": "core",
    "list_commands": "commands",
    "run_command": "commands",
    "upload": "file_ops",
    "download": "file_ops",
    "shell": "process",
    "files_list": "file_ops",
    "files_stat": "file_ops",
    "files_mkdir": "file_ops",
    "files_delete": "file_ops",
    "files_move": "file_ops",
    "files_search": "file_ops",
    "files_upload_stream": "file_ops",
    "files_download_stream": "file_ops",
    "files_archive": "file_ops",
    "files_watch": "file_ops",
    "shell_stream": "process",
    "process_start": "process",
    "process_list": "process",
    "process_detail": "process",
    "process_signal": "process",
    "process_stdin": "process",
    "process_output": "process",
    "pty_create_session": "terminal",
    "pty_list_sessions": "terminal",
    "pty_detail": "terminal",
    "pty_resize": "terminal",
    "pty_delete_session": "terminal",
    "pty_connect": "terminal",
    "system_info": "system",
    "system_metrics": "system",
    "env_get": "system",
    "env_set": "system",
    "ports": "system",
    "packages": "system",
    "code_run": "dev_tools",
    "git_status": "dev_tools",
    "git_diff": "dev_tools",
    "browser_navigate": "browser",
    "browser_screenshot": "browser",
    "browser_content": "browser",
    "browser_click": "browser",
    "browser_type": "browser",
    "browser_evaluate": "browser",
    "browser_pdf": "browser",
    "browser_console": "browser",
}

_LEGACY_DEFAULT_GROUPS: dict[str, bool] = {
    "core": True,
    "commands": True,
    "file_ops": True,
    "process": True,
    "terminal": True,
    "system": True,
    "dev_tools": False,
    "browser": False,
}


class ServerCapabilities:
    """Snapshot of what the current identity may do on the sandbox server.

    Attributes:
        legacy: ``True`` when the server predates per-endpoint discovery (no ``endpoints``
            key).  Only group-level gating is possible then and path/limit queries return
            "unknown".
        revision: Hash of the effective policy; compare to detect a changed configuration.
    """

    def __init__(self, document: dict[str, Any], client: ServerClient | None = None) -> None:
        self._document = document
        self._client = client
        raw_endpoints = document.get("endpoints")
        self.legacy: bool = not isinstance(raw_endpoints, dict)
        self.api_version: int = int(document.get("api_version", 1) or 1)
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
            {str(k): bool(v) for k, v in groups.items()}
            if isinstance(groups, dict)
            else dict(_LEGACY_DEFAULT_GROUPS)
        )
        self.endpoints: dict[str, EndpointInfo] = {}
        if isinstance(raw_endpoints, dict):
            for name, info in raw_endpoints.items():
                if isinstance(info, dict):
                    self.endpoints[str(name)] = EndpointInfo.model_validate({**info, "name": name})

    # -- queries -------------------------------------------------------------- #

    def info(self, endpoint: str) -> EndpointInfo | None:
        """The disclosed rule of *endpoint* (``None`` when unknown or on a legacy server)."""
        return self.endpoints.get(endpoint)

    def can(self, endpoint: str) -> bool:
        """Whether *endpoint* is enabled and the current identity holds its scopes.

        Legacy servers: group-level answer.  Endpoints this client does not know about are
        assumed available on legacy servers and unavailable on discovering ones.
        """
        if self.legacy:
            group = ENDPOINT_GROUPS.get(endpoint)
            return True if group is None else self.groups.get(group, True)
        info = self.endpoints.get(endpoint)
        return info is not None and info.enabled and info.allowed

    def denial(self, endpoint: str) -> str | None:
        """Why *endpoint* is unavailable (``endpoint_disabled``, ``missing_scope``, ...) or None."""
        if self.can(endpoint):
            return None
        if self.legacy:
            return "group_disabled"
        info = self.endpoints.get(endpoint)
        if info is None:
            return "unknown_endpoint"
        if not info.enabled:
            return info.reason or "endpoint_disabled"
        return info.reason or "missing_scope"

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
        raise EndpointNotAvailableError(
            endpoint,
            status_code=404,
            error_code=reason,
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
        """Sorted endpoint IDs the current identity may call (empty on legacy servers)."""
        return sorted(n for n, i in self.endpoints.items() if i.enabled and i.allowed)

    # -- server-authoritative path check ------------------------------------- #

    async def check_path(self, endpoint: str, path: str, op: str | None = None) -> PathDecision:
        """Ask the server whether *endpoint* may touch *path* (never touches the filesystem)."""
        if self.legacy:
            raise EndpointNotAvailableError(
                "capabilities_check",
                message="This sandbox server predates path checks (legacy discovery).",
                status_code=404,
            )
        if self._client is None:
            raise RuntimeError("ServerCapabilities is not bound to a ServerClient")
        return await self._client.check(endpoint, path=path, op=op)

    check_path_sync = make_sync(check_path)

    # -- misc --------------------------------------------------------------- #

    def as_dict(self) -> dict[str, Any]:
        """The raw discovery document."""
        return dict(self._document)

    def __repr__(self) -> str:
        if self.legacy:
            return f"ServerCapabilities(legacy=True, groups={self.groups!r})"
        return (
            f"ServerCapabilities(identity={self.identity_id!r}, preset={self.preset!r}, "
            f"available={len(self.available())}/{len(self.endpoints)})"
        )


__all__ = ["ENDPOINT_GROUPS", "ServerCapabilities"]
