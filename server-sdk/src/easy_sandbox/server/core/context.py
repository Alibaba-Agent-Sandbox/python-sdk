"""Principal and the per-call context handed to native handlers (design 02, section 3)."""

from __future__ import annotations

import dataclasses
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .dispatch import Pipeline
    from .registry import Operation

__all__ = ["OpContext", "Principal"]


@dataclasses.dataclass(frozen=True)
class Principal:
    """An authenticated (or anonymous) caller.

    ``scopes`` carries the in-flight ``PolicyEngine`` identity scopes so one decision source can
    answer both the v1 dispatcher and the operation pipeline.
    """

    id: str
    roles: tuple[str, ...] = ()
    claims: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    authenticated: bool = True
    scopes: frozenset[str] = frozenset()

    @classmethod
    def anonymous(cls, scopes: frozenset[str] = frozenset({"*"})) -> Principal:
        """The caller of an unauthenticated (open) server."""
        return cls(id="anonymous", authenticated=False, scopes=scopes)


@dataclasses.dataclass
class OpContext:
    """What a native handler may rely on (the subset of design 02 implemented in S1/S2)."""

    op: Operation
    principal: Principal
    pipeline: Pipeline
    headers: Mapping[str, str] = dataclasses.field(default_factory=dict)
    request_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex[:16])

    @property
    def registry(self) -> Any:
        """The operation registry of the serving pipeline."""
        return self.pipeline.registry

    @property
    def policy(self) -> Any:
        """The policy bridge that answers this call."""
        return self.pipeline.policy
