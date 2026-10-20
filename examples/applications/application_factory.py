"""Packaged trusted FC application factory; uses the runtime's real adapters.

Set all bindings described in docs/en/guide/agent-applications.md. This factory
creates no cloud resources. The gateway, worker and dispatcher share this image
and factory; only their startup role changes. Replace the authenticator or model
adapter here when application-specific integration is needed.
"""

from agent_sandbox.applications import ApplicationRuntime
from agent_sandbox.applications.config import default_factory


def create_application() -> ApplicationRuntime:
    """Wire immutable template inputs, PostgreSQL, remote tools and FC delivery."""
    return default_factory()
