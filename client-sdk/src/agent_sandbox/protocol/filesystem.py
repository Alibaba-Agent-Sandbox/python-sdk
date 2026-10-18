"""Compatibility exports; backend implementation lives in its provider."""

import sys as _sys
from importlib import import_module as _import_module

from agent_sandbox.providers.shared.e2b.filesystem import (
    _LIST_DIR as _LIST_DIR,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _MAKE_DIR as _MAKE_DIR,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _MOVE as _MOVE,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _REMOVE as _REMOVE,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _STAT as _STAT,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _WATCH_DIR as _WATCH_DIR,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    FilesystemProtocol as FilesystemProtocol,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _codec as _codec,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _is_directory as _is_directory,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _name_from_path as _name_from_path,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _parse_file_info as _parse_file_info,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _parse_watch_event as _parse_watch_event,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _raise_file_error as _raise_file_error,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _raise_transfer_timeout as _raise_transfer_timeout,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    _unwrap_entry as _unwrap_entry,
)
from agent_sandbox.providers.shared.e2b.filesystem import (
    logger as logger,
)

_sys.modules[__name__] = _import_module("agent_sandbox.providers.shared.e2b.filesystem")
