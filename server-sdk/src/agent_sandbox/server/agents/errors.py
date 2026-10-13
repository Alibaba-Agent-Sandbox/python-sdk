"""Exception types and error-code vocabulary of the hosted agent runtime."""

from __future__ import annotations

__all__ = [
    "AGENTS_WIRE_CODES",
    "AgentConfigError",
    "AgentNotFoundError",
    "AgentRuntimeError",
    "LocalApiError",
    "RuntimeFailure",
    "agents_wire_code",
]

# Error codes of the official Agents API (``SessionTurnError.code``).
AGENTS_WIRE_CODES = frozenset(
    {
        "context_length_exceeded",
        "session_budget_exceeded",
        "usage_limit_exceeded",
        "rate_limit_exceeded",
        "server_overloaded",
        "connection_failed",
        "server_error",
        "authentication_error",
        "invalid_request",
        "resource_not_found",
        "sandbox_error",
        "active_turn_not_steerable",
        "request_timeout",
        "internal_error",
    }
)

# Codes that only exist on the Responses wire; the Agents wire maps them.
_EXTENSION_CODES = {
    "runtime_not_installed": "sandbox_error",
    "output_limit_exceeded": "sandbox_error",
    "workspace_error": "sandbox_error",
    "cancelled": "internal_error",
}


def agents_wire_code(code: str) -> str:
    """Map an internal error *code* onto the fixed Agents-API code set."""
    if code in AGENTS_WIRE_CODES:
        return code
    return _EXTENSION_CODES.get(code, "internal_error")


class AgentRuntimeError(Exception):
    """Base class; carries an HTTP-ish status and a machine-readable code."""

    status = 400
    code = "invalid_request"

    def __init__(self, message: str, *, param: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.param = param


class AgentConfigError(AgentRuntimeError):
    """Invalid agent definition; ``problems`` lists every issue found."""

    def __init__(self, problems: list[str] | str) -> None:
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("; ".join(self.problems))


class AgentNotFoundError(AgentRuntimeError):
    """Unknown agent, session, turn or response."""

    status = 404
    code = "resource_not_found"


class LocalApiError(AgentRuntimeError):
    """A refusal raised by the local Agents API handlers (status, code and param are explicit)."""

    def __init__(
        self,
        message: str,
        *,
        param: str | None = None,
        code: str = "invalid_request",
        status: int = 400,
    ) -> None:
        super().__init__(message, param=param)
        self.code = code
        self.status = status


class RuntimeFailure(Exception):  # noqa: N818 — domain name, not an Error suffix
    """A turn-level failure with a stable ``code`` (never contains secrets)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
