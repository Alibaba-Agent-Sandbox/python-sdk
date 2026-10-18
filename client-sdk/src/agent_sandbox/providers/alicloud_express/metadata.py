"""Pure Express configuration metadata. No SDK, engine or cloud calls."""

from typing import Any

from agent_sandbox.providers.alicloud_express.config_metadata import DEFAULT_CONFIG
from agent_sandbox.providers.shared.e2b.url import envd_url


def _legacy_ports(context: Any) -> Any:
    from agent_sandbox.providers.shared.e2b.ports import WirePortAccess

    return WirePortAccess(context, server_auth=False)


def _legacy_pty_url(base_url: str, server_port: int, pty_port: int) -> str:
    from agent_sandbox.providers.shared.e2b.ports import legacy_pty_url

    return legacy_pty_url(base_url, server_port, pty_port)


CONFIG_METADATA = {
    **DEFAULT_CONFIG,
    "legacy_url_builder": envd_url,
    "legacy_port_factory": _legacy_ports,
    "legacy_pty_url_builder": _legacy_pty_url,
}
