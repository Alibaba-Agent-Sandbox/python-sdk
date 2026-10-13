"""Process hardening: refuse an argv whose executable resolves under a system tree.

``/proc``, ``/sys`` and ``/dev`` are refused on the path as given and on its real path,
so a symlink that lands in one of them is refused too.  Live exec routes call this before
starting a process.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence

from ..policy import PolicyDenied

__all__ = ["check_process"]

_DENIED_ROOTS = ("/proc", "/sys", "/dev")


def _under_denied_root(path: str) -> bool:
    norm = os.path.normpath(path if os.path.isabs(path) else os.path.abspath(path))
    return any(norm == root or norm.startswith(root + os.sep) for root in _DENIED_ROOTS)


def _resolved_executable(exe: str) -> tuple[str, str]:
    """Return ``(lookup path, realpath)`` for *exe* (``PATH`` search for a bare name)."""
    looked_up = exe if os.sep in exe or os.path.isabs(exe) else shutil.which(exe) or exe
    return looked_up, os.path.realpath(looked_up)


def check_process(argv: Sequence[str]) -> list[str]:
    """Return *argv* when its executable does not resolve under ``/proc``, ``/sys`` or ``/dev``.

    Raises:
        PolicyDenied: ``process_invalid`` (400) or ``process_denied``.
    """
    if (
        isinstance(argv, (str, bytes))
        or not isinstance(argv, Sequence)
        or not argv
        or not all(isinstance(arg, str) for arg in argv)
    ):
        raise PolicyDenied(
            "process_invalid",
            "argv must be a non-empty list of strings",
            status=400,
            error_type="ValueError",
        )
    exe = argv[0]
    if not exe or "\x00" in exe:
        raise PolicyDenied(
            "process_invalid", "Empty executable", status=400, error_type="ValueError"
        )
    looked_up, resolved = _resolved_executable(exe)
    if _under_denied_root(looked_up) or _under_denied_root(resolved):
        raise PolicyDenied(
            "process_denied", f"Executable {exe!r} resolves under a protected directory"
        )
    return list(argv)
