"""Compatibility exports; backend implementation lives in its provider."""

import sys as _sys
from importlib import import_module as _import_module

from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _CREATE_CONTEXT as _CREATE_CONTEXT,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _EXECUTE as _EXECUTE,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _HTTP_TIMEOUT_BUFFER as _HTTP_TIMEOUT_BUFFER,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _LIST_CONTEXTS as _LIST_CONTEXTS,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _REMOVE_CONTEXT as _REMOVE_CONTEXT,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _RESTART_CONTEXT as _RESTART_CONTEXT,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    CodeInterpreterProtocol as CodeInterpreterProtocol,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    _codec as _codec,
)
from agent_sandbox.providers.shared.e2b.code_interpreter import (
    logger as logger,
)

_sys.modules[__name__] = _import_module("agent_sandbox.providers.shared.e2b.code_interpreter")
