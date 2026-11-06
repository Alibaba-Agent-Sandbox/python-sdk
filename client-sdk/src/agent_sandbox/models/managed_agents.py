"""Dependency-free public errors shared by managed providers and applications."""

from __future__ import annotations

from typing import Any

__all__ = ["ManagedError"]


class ManagedError(Exception):
    """A bounded, explicitly public error, never an arbitrary exception string."""

    def __init__(self, status: int, code: str, message: str, param: str | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.param = status, code, message, param

    def body(self) -> dict[str, Any]:
        """Return the documented error envelope."""
        return {
            "error": {
                "type": "invalid_request_error",
                "code": self.code,
                "message": self.message,
                "param": self.param,
            }
        }
