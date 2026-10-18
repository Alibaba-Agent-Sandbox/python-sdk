"""Pure Express configuration metadata. No SDK, engine or cloud calls."""

from typing import Any

from agent_sandbox.providers.shared.e2b.url import envd_url
from agent_sandbox.utils.config_keys import (
    ALICLOUD_EXPRESS_KEYS,
    BUILTIN_PROVIDER_ID,
    GENERIC_ENDPOINT_KEYS,
)


def _legacy_ports(context: Any) -> Any:
    from agent_sandbox.providers.shared.e2b.ports import WirePortAccess

    return WirePortAccess(context, server_auth=False)


def _legacy_pty_url(base_url: str, server_port: int, pty_port: int) -> str:
    from agent_sandbox.providers.shared.e2b.ports import legacy_pty_url

    return legacy_pty_url(base_url, server_port, pty_port)


CONFIG_METADATA: dict[str, Any] = {
    "id": BUILTIN_PROVIDER_ID,
    "legacy_url_builder": envd_url,
    "legacy_port_factory": _legacy_ports,
    "legacy_pty_url_builder": _legacy_pty_url,
    "keys": ALICLOUD_EXPRESS_KEYS,
    "inherit": frozenset(GENERIC_ENDPOINT_KEYS),
    "derive": {
        "sandbox_base_url": "https://api.{region}.e2b.fc.aliyuncs.com",
        "sandbox_domain": "{region}.e2b.fc.aliyuncs.com",
    },
    "endpoint_defaults": {
        "sandbox_base_url": "https://api.cn-hangzhou.e2b.fc.aliyuncs.com",
        "sandbox_domain": "cn-hangzhou.e2b.fc.aliyuncs.com",
    },
    "legacy_fields": frozenset({"region", "access_key_id", "access_key_secret"}),
    "omit_default_options": True,
}
