"""Shared helpers for the independent security PoCs.

Every PoC is a function that ASSERTS the secure behaviour the design promises (or should promise).
A function that raises ``AssertionError`` demonstrates a finding (status VULNERABLE); one that
returns normally means the attack was stopped (status HELD).  Findings are expected to be
VULNERABLE until the design/implementation is fixed; ``run_all.py`` compares against EXPECTED.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SPIKES = HERE.parent
if str(SPIKES) not in sys.path:
    sys.path.insert(0, str(SPIKES))

import ebxp.api as api  # noqa: E402,F401  (registers the 152-op catalog stubs into the default registry)
from ebxp import *  # noqa: E402,F401,F403  (the spike facade: Policy, PathScope, CommandScope, ops, ...)
from ebxp.guards import (  # noqa: E402,F401
    CommandScope,
    Denied,
    PathScope,
    _glob_to_re,
    check_command,
    filter_env,
    open_beneath,
    resolve_path,
)
from ebxp.policy import Principal, Policy, selector_matches  # noqa: E402,F401
from ebxp.server import REG, Server  # noqa: E402,F401


def mktree() -> pathlib.Path:
    """A fresh canonical temp directory."""
    return pathlib.Path(tempfile.mkdtemp(prefix="ebx-isec-")).resolve()


def secure(cond: bool, why: str) -> None:
    """Assert the SECURE outcome; the message states the exploit that succeeded."""
    if not cond:
        raise AssertionError(why)
