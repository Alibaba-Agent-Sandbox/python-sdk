"""Global configuration data model."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_sandbox.providers.bundled_config import DEFAULT_CONFIG


class GlobalConfig(BaseModel):
    """SDK-wide configuration settings.

    This is the data model for configuration. The actual loading logic
    (env vars, .env files, config.toml) is in transport/config.py.
    """

    # Authentication
    api_key: str | None = None
    access_key_id: str | None = None
    access_key_secret: str | None = None

    # Connection
    api_url: str = DEFAULT_CONFIG["endpoint_defaults"]["sandbox_base_url"]
    domain: str = DEFAULT_CONFIG["endpoint_defaults"]["sandbox_domain"]
    region: str = str(next(key.default for key in DEFAULT_CONFIG["keys"] if key.key == "region"))
    timeout: int = Field(default=300, ge=1)
    max_retries: int = Field(default=3, ge=0, le=10)
    secure: bool = True

    @staticmethod
    def api_url_for_region(region: str) -> str:
        """Generate the Platform API URL for a given region."""
        return str(DEFAULT_CONFIG["derive"]["sandbox_base_url"]).replace("{region}", region)

    @staticmethod
    def domain_for_region(region: str) -> str:
        """Generate the data-plane domain for a given region."""
        return str(DEFAULT_CONFIG["derive"]["sandbox_domain"]).replace("{region}", region)

    # Logging
    log_level: str = "WARNING"

    # CLI
    default_template: str = "base"
