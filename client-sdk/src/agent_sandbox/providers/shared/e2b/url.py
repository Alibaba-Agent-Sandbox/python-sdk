"""Address convention of the explicitly selected E2B/envd wire adapter."""

ENVD_PORT = 49983


def envd_url(sandbox_id: str, domain: str) -> str:
    """Build an envd address; only adapters opting into this protocol use it."""
    return f"https://{ENVD_PORT}-{sandbox_id}.{domain}"
