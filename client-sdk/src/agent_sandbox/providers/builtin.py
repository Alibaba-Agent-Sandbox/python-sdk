"""Compatibility exports; backend implementation lives in its provider."""

import sys as _sys
from importlib import import_module as _import_module

from agent_sandbox.providers.alicloud_express.provider import (
    AlicloudExpressProvider as AlicloudExpressProvider,
)
from agent_sandbox.providers.alicloud_express.provider import (
    _fields as _fields,
)

_sys.modules[__name__] = _import_module("agent_sandbox.providers.alicloud_express.provider")
