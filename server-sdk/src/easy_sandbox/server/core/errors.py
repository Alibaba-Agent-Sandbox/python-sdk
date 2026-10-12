"""Errors of the operation model."""

from __future__ import annotations

from typing import Any

__all__ = ["OpError", "RegistryFrozen"]


class RegistryFrozen(RuntimeError):  # noqa: N818  (public name fixed by the design doc)
    """An operation was registered after the registry was frozen."""

    def __init__(self) -> None:
        super().__init__("registry is frozen: register ops before constructing the server")


class OpError(Exception):
    """An expected failure of an operation handler.

    Attributes:
        code: Stable machine string, for example ``args.missing``.
        message: Human-readable text.
        status: HTTP status of the response (400 by default).
        details: Extra JSON fields merged into the error body.
    """

    def __init__(self, code: str, message: str, status: int = 400, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def to_body(self) -> dict[str, Any]:
        """Return the JSON body (superset of the v1 ``{error, type}`` shape)."""
        body: dict[str, Any] = {"error": self.message, "type": "OpError", "code": self.code}
        body.update(self.details)
        return body
