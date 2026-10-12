"""The discovery document (design 02, section 7), served by ``GET /ops`` and ``core.describe``.

``GET /capabilities`` is untouched in this stage: it is a v1 route and keeps its v1 body.  The
v2 keys of its union body (design IF-26) arrive when that route moves onto the pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .._version import __version__
from .context import OpContext  # noqa: TC001  (resolved at runtime for parameter types)
from .errors import OpError
from .registry import CATALOG_VERSION

if TYPE_CHECKING:
    from .context import Principal
    from .dispatch import Pipeline
    from .registry import Registry

__all__ = ["build_document", "register_native"]

API_FAMILY = "easy-sandbox/2"


def build_document(
    pipeline: Pipeline,
    principal: Principal,
    *,
    namespace: str | None = None,
    ids: list[str] | None = None,
) -> dict[str, Any]:
    """Operations effective for *principal*; unmounted operations are not listed (no oracle)."""
    registry = pipeline.registry
    policy = pipeline.policy
    prefix = f"{namespace}." if namespace else ""

    def visible(operation: Any) -> bool:
        return operation.id.startswith(prefix) and policy.peek(operation, principal).allowed

    entries = registry.describe(*(ids or []), visible=visible)
    for entry in entries:
        operation = registry.get(entry["id"])
        if operation is not None:
            effective = policy.limits_of(operation)
            if effective:
                entry["effective"] = effective
    return {
        "api": API_FAMILY,
        "catalog_version": CATALOG_VERSION,
        "server_version": __version__,
        "revision": policy.revision,
        "principal": {"id": principal.id, "roles": list(principal.roles)},
        "policy": {"configured": policy.configured, "preset": policy.preset},
        "count": len(entries),
        "ops": entries,
    }


def _describe(
    ctx: OpContext, namespace: str | None = None, ids: list[Any] | None = None
) -> dict[str, Any]:
    """The operations the caller may use, with their effects, bindings and parameters."""
    if namespace is not None and not isinstance(namespace, str):
        raise OpError("args.type", "'namespace' must be a string")
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
        raise OpError("args.type", "'ids' must be a list of strings")
    return build_document(ctx.pipeline, ctx.principal, namespace=namespace, ids=ids)


def register_native(registry: Registry) -> None:
    """Register the operations that have no v1 route behind them."""
    registry.op(
        "core.describe",
        effects="read",
        http="GET /ops",
        group="core",
        since="2.0",
    )(_describe)
