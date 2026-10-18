"""Declared absence must refuse PTY before touching session or wire state."""

import pytest

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError
from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider


async def test_native_terminal_checks_feature_before_session_access() -> None:
    provider = AlicloudExpressProvider()
    provider.features = provider.features - {"pty"}
    with pytest.raises(ProviderFeatureNotSupportedError):
        await provider.open_terminal(None)
