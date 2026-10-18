"""Express composes pure distribution data with its legacy URL adapter."""

from agent_sandbox.providers.shared.e2b.url import envd_url
from agent_sandbox.utils.bundled_config import DEFAULT_CONFIG

CONFIG_METADATA = {**DEFAULT_CONFIG, "legacy_url_builder": envd_url}
