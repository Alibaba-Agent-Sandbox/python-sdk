"""Operation model of Server SDK v2, stage S1/S2: registry, ``ops`` tree, policy bridge, pipeline.

Lands **beside** the v1 dispatcher.  Nothing here replaces ``app.py``/``router.py``/``routes_*``:
every v1 route is registered as an operation whose handler is the existing route handler, and
``POST /ops/{id}`` plus ``GET /ops`` are served by :class:`Pipeline` through a thin hook that the
v1 dispatcher calls only for requests that match no v1 route.

Stdlib only (design 10, section 1.3).
"""

from __future__ import annotations

from .context import OpContext, Principal
from .dispatch import Call, Outcome, Pipeline, Rejected
from .errors import OpError, RegistryFrozen
from .legacy import build_registry
from .policy import Admission, OpNotEnabled, Policy, Verdict
from .refs import OpRef, OpTree, ops
from .registry import HttpBinding, Operation, Param, Registry

__all__ = [
    "Admission",
    "Call",
    "HttpBinding",
    "OpContext",
    "OpError",
    "OpNotEnabled",
    "OpRef",
    "OpTree",
    "Operation",
    "Outcome",
    "Param",
    "Pipeline",
    "Policy",
    "Principal",
    "Registry",
    "RegistryFrozen",
    "Rejected",
    "Verdict",
    "build_registry",
    "default_op_registry",
    "ops",
]


def default_op_registry() -> Registry:
    """Operations of the built-in v1 routes (offline introspection; no server needed)."""
    from .. import app as _app  # noqa: F401  (import side-effect: registers every v1 route)
    from ..registry import default_registry
    from ..router import default_table

    return build_registry(default_table(), default_registry())
