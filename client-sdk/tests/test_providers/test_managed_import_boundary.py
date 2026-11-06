"""Native provider imports stay below the optional managed application layer."""

from __future__ import annotations

import subprocess
import sys


def test_managed_express_backend_keeps_error_identity_without_loading_application() -> None:
    """Exercise the real import order in a fresh interpreter, then the public re-export."""
    source = """
import sys
from agent_sandbox.providers import ManagedExpressBackend

assert ManagedExpressBackend.__module__ == 'agent_sandbox.providers.alicloud_express.managed'
assert not any(name.startswith('agent_sandbox.managed_agents') for name in sys.modules)

from agent_sandbox.models.managed_agents import ManagedError as LowerError
from agent_sandbox.managed_agents.models import ManagedError as PublicError

assert PublicError is LowerError
error = LowerError(409, 'example_conflict', 'A safe message', 'input')
try:
    raise error
except PublicError as caught:
    assert caught is error
    assert caught.status == 409
    assert caught.body() == {'error': {
        'type': 'invalid_request_error', 'code': 'example_conflict',
        'message': 'A safe message', 'param': 'input'}}
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", source],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
