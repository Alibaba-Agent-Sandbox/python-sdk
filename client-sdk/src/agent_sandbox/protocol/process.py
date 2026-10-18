"""Compatibility exports; backend implementation lives in its provider."""

import sys as _sys
from importlib import import_module as _import_module

from agent_sandbox.providers.shared.e2b.process import (
    _CONNECT as _CONNECT,
)
from agent_sandbox.providers.shared.e2b.process import (
    _HTTP_TIMEOUT_BUFFER as _HTTP_TIMEOUT_BUFFER,
)
from agent_sandbox.providers.shared.e2b.process import (
    _LIST as _LIST,
)
from agent_sandbox.providers.shared.e2b.process import (
    _SEND_INPUT as _SEND_INPUT,
)
from agent_sandbox.providers.shared.e2b.process import (
    _SEND_SIGNAL as _SEND_SIGNAL,
)
from agent_sandbox.providers.shared.e2b.process import (
    _SIGNAL_NAMES as _SIGNAL_NAMES,
)
from agent_sandbox.providers.shared.e2b.process import (
    _START as _START,
)
from agent_sandbox.providers.shared.e2b.process import (
    _UPDATE as _UPDATE,
)
from agent_sandbox.providers.shared.e2b.process import (
    ProcessProtocol as ProcessProtocol,
)
from agent_sandbox.providers.shared.e2b.process import (
    _codec as _codec,
)
from agent_sandbox.providers.shared.e2b.process import (
    _parse_process_chunk as _parse_process_chunk,
)
from agent_sandbox.providers.shared.e2b.process import (
    _process_selector as _process_selector,
)
from agent_sandbox.providers.shared.e2b.process import (
    logger as logger,
)

_sys.modules[__name__] = _import_module("agent_sandbox.providers.shared.e2b.process")
