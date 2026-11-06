"""Optional, durable application Gateway for Agents running in owned sandboxes.

Importing this module does not start a server, discover providers or create resources.
"""

from .models import ManagedConfig, ManagedError
from .service import ManagedService
from .store import ManagedStore

__all__ = ["ManagedConfig", "ManagedError", "ManagedService", "ManagedStore"]
