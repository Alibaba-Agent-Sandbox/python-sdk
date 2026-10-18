"""Compatibility exports; backend implementation lives in its provider."""

import sys as _sys
from importlib import import_module as _import_module

from agent_sandbox.providers.shared.e2b.terminal import (
    TerminalSession as TerminalSession,
)
from agent_sandbox.providers.shared.e2b.terminal import (
    logger as logger,
)

_sys.modules[__name__] = _import_module("agent_sandbox.providers.shared.e2b.terminal")
