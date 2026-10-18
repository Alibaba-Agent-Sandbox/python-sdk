"""Pure Express configuration metadata. No SDK, engine or cloud calls."""

from agent_sandbox.utils.config_keys import (
    ALICLOUD_EXPRESS_KEYS,
    BUILTIN_PROVIDER_ID,
    GENERIC_ENDPOINT_KEYS,
)

CONFIG_METADATA = {
    "id": BUILTIN_PROVIDER_ID,
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
