"""Compatibility exports; backend implementation lives in its provider."""

import sys as _sys
from importlib import import_module as _import_module

from agent_sandbox.providers.alicloud_express.auth import (
    _ENVD_BASIC_AUTH as _ENVD_BASIC_AUTH,
)
from agent_sandbox.providers.alicloud_express.auth import (
    _TOKEN_EXCHANGE_ACTION as _TOKEN_EXCHANGE_ACTION,
)
from agent_sandbox.providers.alicloud_express.auth import (
    _TOKEN_EXCHANGE_API_VERSION as _TOKEN_EXCHANGE_API_VERSION,
)
from agent_sandbox.providers.alicloud_express.auth import (
    ENVD_AUTH_HEADER as ENVD_AUTH_HEADER,
)
from agent_sandbox.providers.alicloud_express.auth import (
    ENVD_SANDBOX_ID_HEADER as ENVD_SANDBOX_ID_HEADER,
)
from agent_sandbox.providers.alicloud_express.auth import (
    ENVD_SANDBOX_PORT_HEADER as ENVD_SANDBOX_PORT_HEADER,
)
from agent_sandbox.providers.alicloud_express.auth import (
    PLATFORM_AUTH_HEADER as PLATFORM_AUTH_HEADER,
)
from agent_sandbox.providers.alicloud_express.auth import (
    AkSkAuth as AkSkAuth,
)
from agent_sandbox.providers.alicloud_express.auth import (
    ApiKeyAuth as ApiKeyAuth,
)
from agent_sandbox.providers.alicloud_express.auth import (
    AuthProvider as AuthProvider,
)
from agent_sandbox.providers.alicloud_express.auth import (
    EnvdTokenManager as EnvdTokenManager,
)
from agent_sandbox.providers.alicloud_express.auth import (
    _exchange_aksk_for_api_key as _exchange_aksk_for_api_key,
)
from agent_sandbox.providers.alicloud_express.auth import (
    _percent_encode as _percent_encode,
)
from agent_sandbox.providers.alicloud_express.auth import (
    _sign_rpc as _sign_rpc,
)
from agent_sandbox.providers.alicloud_express.auth import (
    build_envd_headers as build_envd_headers,
)
from agent_sandbox.providers.alicloud_express.auth import (
    create_auth_provider as create_auth_provider,
)
from agent_sandbox.providers.alicloud_express.auth import (
    logger as logger,
)

_sys.modules[__name__] = _import_module("agent_sandbox.providers.alicloud_express.auth")
