"""Unimplemented project interpreter routes fail explicitly before any transport I/O."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError
from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider
from agent_sandbox.providers.shared.e2b.code_interpreter import UnsupportedCodeProtocol


@pytest.mark.parametrize(
    "method, options, operation",
    [
        ("run_code", {"code": "raise Exception()"}, "code.execute"),
        (
            "run_code",
            {"code": "raise Exception()", "mode": "default-context"},
            "code.default-context.execute",
        ),
        ("run_code", {"code": "raise Exception()", "context_id": "owned"}, "code.context.execute"),
        ("create_context", {}, "code.context.create"),
        ("list_contexts", {}, "code.context.list"),
        ("restart_context", {"context_id": "owned"}, "code.context.restart"),
        ("remove_context", {"context_id": "owned"}, "code.context.delete"),
    ],
)
async def test_unsupported_interpreter_has_no_wire_fallback(method, options, operation):
    transport = MagicMock(envd_request=AsyncMock())
    protocol = UnsupportedCodeProtocol("alicloud-express")
    with pytest.raises(ProviderFeatureNotSupportedError) as exc:
        await getattr(protocol, method)("sandbox", "https://envd.invalid", transport, **options)
    assert exc.value.feature == operation
    transport.envd_request.assert_not_awaited()


def test_express_does_not_advertise_unverified_interpreter_operations():
    provider = AlicloudExpressProvider()
    assert not any(operation.startswith("code.") for operation in provider.operations)
    assert "code" not in provider.capabilities()
