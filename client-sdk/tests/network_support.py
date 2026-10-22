"""Explicit E2B wire adapter fixtures for NetworkModule tests."""

from typing import Any

from agent_sandbox.api.network import NetworkModule
from agent_sandbox.protocol.port_contract import PortContext
from agent_sandbox.providers.shared.e2b.ports import WirePortAccess


def provider_network(**kwargs: Any) -> NetworkModule:
    context = PortContext(
        kwargs["sandbox_id"],
        kwargs["domain"],
        kwargs.get("secure", True),
        kwargs.get("access_token"),
    )
    return NetworkModule(**kwargs, port_access=WirePortAccess(context, server_auth=False))
