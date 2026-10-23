"""Runtime enforcement of a manifest's ``[features] supported`` list for ``rest`` providers.

``rest`` providers reuse the built-in protocol classes. This gives them the behaviour ``exec``
providers get from their EPP adapters: a method whose feature is not declared fails with ``E8004``
before any request is sent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from agent_sandbox.providers.base import ProviderInfra

#: Rules map a method name to the features of which at least one must be supported.
SANDBOX_RULES: dict[str, tuple[str, ...]] = {
    "create": ("sandbox.lifecycle",),
    "list": ("sandbox.lifecycle",),
    "list_v2": ("sandbox.lifecycle",),
    "get_info": ("sandbox.lifecycle",),
    "connect": ("sandbox.lifecycle",),
    "is_running": ("sandbox.lifecycle",),
    "kill": ("sandbox.lifecycle",),
    "set_timeout": ("sandbox.timeout",),
    "pause": ("sandbox.pause",),
    "resume": ("sandbox.pause",),
}

PROCESS_RULES: dict[str, tuple[str, ...]] = {
    "start": ("exec.run", "exec.stream"),
    "list_processes": ("process.manage",),
    "connect_to_process": ("process.manage",),
    "update": ("process.manage",),
    "send_input": ("process.manage",),
    "send_signal": ("process.manage",),
    "send_stdin": ("process.manage",),
    "kill": ("process.manage",),
    "open_terminal": ("pty",),
}

_FILE_METHODS = (
    "stat",
    "list_dir",
    "make_dir",
    "remove",
    "move",
    "upload_file",
    "download_file",
    "exists",
    "get_info",
    "read",
    "read_text",
    "write",
    "rename",
)

FILESYSTEM_RULES: dict[str, tuple[str, ...]] = {
    **{m: ("files.rw",) for m in _FILE_METHODS},
    "watch_dir": ("files.watch",),
}


class _Gated:
    """Proxy over a protocol object; methods of undeclared features raise ``E8004``."""

    def __init__(
        self,
        target: Any,
        provider_id: str,
        rules: Mapping[str, tuple[str, ...]],
        supported: frozenset[str],
    ) -> None:
        self._target = target
        self._provider_id = provider_id
        self._rules = rules
        self._supported = supported

    def __getattr__(self, name: str) -> Any:
        needed = self._rules.get(name)
        if needed is not None and not any(f in self._supported for f in needed):
            provider_id, feature = self._provider_id, needed[0]

            async def _raise(*_a: Any, **_k: Any) -> Any:
                raise ProviderFeatureNotSupportedError(provider_id, feature)

            return _raise
        return getattr(self._target, name)


def gate_protocol(
    target: Any,
    provider_id: str,
    rules: Mapping[str, tuple[str, ...]],
    supported: frozenset[str],
) -> Any:
    """Wrap *target*; a method needing an undeclared feature raises E8004."""
    return _Gated(target, provider_id, rules, supported)


__all__ = [
    "FILESYSTEM_RULES",
    "OPERATION_SANDBOX_RULES",
    "OPERATION_PROCESS_RULES",
    "OPERATION_FILESYSTEM_RULES",
    "gate_operation_protocols",
    "PROCESS_RULES",
    "SANDBOX_RULES",
    "gate_protocol",
]


OPERATION_SANDBOX_RULES = {
    "create": ("sandbox.create",),
    "list": ("sandbox.list",),
    "list_v2": ("sandbox.list",),
    "get_info": ("sandbox.get",),
    "connect": ("sandbox.get",),
    "is_running": ("sandbox.get",),
    "kill": ("sandbox.delete",),
    "set_timeout": ("sandbox.timeout",),
    "pause": ("sandbox.pause",),
    "resume": ("sandbox.resume",),
    "port_url": ("ports.resolve",),
    "application_endpoint": ("ports.resolve",),
}
OPERATION_PROCESS_RULES = {"start": ("exec.run", "exec.stream")}
OPERATION_FILESYSTEM_RULES = {
    "read": ("files.read",),
    "read_text": ("files.read",),
    "download_file": ("files.read",),
    "write": ("files.write",),
    "upload_file": ("files.write",),
    "make_dir": ("files.write",),
    "list_dir": ("files.list",),
    "stat": ("files.stat",),
    "get_info": ("files.stat",),
    "exists": ("files.stat",),
    "remove": ("files.remove",),
    "move": ("files.move",),
    "rename": ("files.move",),
}


def gate_operation_protocols(
    infra: ProviderInfra, provider_id: str, operations: frozenset[str]
) -> ProviderInfra:
    """Enforce the exact public operation boundary before transport dispatch."""
    for field, rules in (
        ("sandbox_protocol", OPERATION_SANDBOX_RULES),
        ("process_protocol", OPERATION_PROCESS_RULES),
        ("filesystem_protocol", OPERATION_FILESYSTEM_RULES),
    ):
        protocol = getattr(infra, field)
        if protocol is not None:
            setattr(infra, field, gate_protocol(protocol, provider_id, rules, operations))
    return infra
