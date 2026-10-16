"""Structured error hierarchy for Agent Sandbox SDK.

注意：错误码（如 E1001、E2001 等）为 SDK 内部定义，不是阿里云官方 API 返回的错误码。

Every exception carries: code (str), message (str), suggestion (str), docs_url (str).
Error codes follow the pattern E{category}{sequence}:
  E1xxx = Authentication errors
  E2xxx = Sandbox creation errors
  E3xxx = Execution errors
  E4xxx = Filesystem errors
  E5xxx = Network errors
  E6xxx = Session errors
  E8xxx = Provider (backend plugin) errors
  E9xxx = In-sandbox server API errors (SandboxServer on port 9000)
"""

from __future__ import annotations

from typing import Any


class SandboxError(Exception):
    """Base exception for all Agent Sandbox errors."""

    code: str = "E0000"
    suggestion: str = ""
    docs_url: str = ""  # TODO: 待补充正式文档 URL

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        suggestion: str | None = None,
        docs_url: str | None = None,
    ) -> None:
        self.message = message
        if code is not None:
            self.code = code
        if suggestion is not None:
            self.suggestion = suggestion
        if docs_url is not None:
            self.docs_url = docs_url
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(parts)

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
            "docs_url": self.docs_url,
        }


# --- Authentication Errors (E1xxx) ---


class AuthenticationError(SandboxError):
    """Base for all authentication failures."""

    code = "E1000"


class InvalidAPIKeyError(AuthenticationError):
    """API Key is invalid or missing."""

    code = "E1001"
    suggestion = "Check your E2B_API_KEY environment variable or pass sandbox_api_key."


class TokenExpiredError(AuthenticationError):
    """Authentication token has expired."""

    code = "E1002"
    suggestion = (
        "The SDK should auto-refresh tokens. If this persists, check system clock synchronization."
    )


class InvalidCredentialsError(AuthenticationError):
    """AK/SK credentials are invalid."""

    code = "E1003"
    suggestion = (
        "Check ALICLOUD_ACCESS_KEY_ID and ALICLOUD_ACCESS_KEY_SECRET environment variables."
    )


class TokenExchangeError(AuthenticationError):
    """AK/SK to API Key token exchange failed."""

    code = "E1004"
    suggestion = (
        "Token exchange from AK/SK to Platform API key failed. "
        "Use E2B_API_KEY directly, or check AK/SK credentials and network connectivity."
    )


# --- Creation Errors (E2xxx) ---


class SandboxCreationError(SandboxError):
    """Base for sandbox creation failures."""

    code = "E2000"


class TemplateNotFoundError(SandboxCreationError):
    """Specified template does not exist."""

    code = "E2001"
    suggestion = "Run 'abx template list' to see available templates."


class QuotaExceededError(SandboxCreationError):
    """Sandbox quota has been exceeded."""

    code = "E2002"
    suggestion = "Destroy idle sandboxes or request a quota increase."


class RegionUnavailableError(SandboxCreationError):
    """Requested region is not available."""

    code = "E2003"
    suggestion = "Try a different region or check service availability."


class TemplateParseError(SandboxCreationError):
    """A matching template was found but its definition is malformed.

    Raised fail-closed by the capability resolver: when a template that
    *matches* the requested id fails model validation, we refuse to fall
    back to :data:`DEFAULT_CAPABILITIES` (which would silently widen the
    granted permissions).
    """

    code = "E2004"
    suggestion = (
        "Fix the template.yaml (see the validation error above); "
        "capabilities are NOT granted until the template parses cleanly."
    )


class SandboxNotFoundError(SandboxError):
    """No sandbox with the given ID exists (never created, expired or already killed)."""

    code = "E2009"
    suggestion = (
        "Run 'abx list' to see the running sandboxes; "
        "a killed or expired sandbox cannot be reconnected."
    )


# --- Execution Errors (E3xxx) ---


class ExecutionError(SandboxError):
    """Base for command/code execution failures."""

    code = "E3000"


class CommandTimeoutError(ExecutionError):
    """Command execution timed out."""

    code = "E3001"
    suggestion = "Increase the timeout parameter or check if the command is hanging."


class ProcessError(ExecutionError):
    """Process exited with non-zero code."""

    code = "E3002"

    def __init__(
        self,
        message: str,
        *,
        exit_code: int = -1,
        stdout: str = "",
        stderr: str = "",
        **kwargs: Any,
    ) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(message, **kwargs)


class CodeExecutionError(ExecutionError):
    """Code execution failed."""

    code = "E3003"
    suggestion = "Check code syntax and runtime dependencies in the sandbox template."


class CapabilityNotSupportedError(ExecutionError):
    """Requested capability is not enabled for this sandbox/template."""

    code = "E3004"

    def __init__(
        self,
        capability: str,
        *,
        message: str | None = None,
        suggestion: str | None = None,
        **kwargs: object,
    ) -> None:
        self.capability = capability
        _message = message or (
            f"Capability '{capability}' is not supported by this sandbox template."
        )
        _suggestion = suggestion or (
            f"Declare '{capability}' in the template's capabilities list "
            "(template.yaml) or use a template that supports it."
        )
        super().__init__(_message, suggestion=_suggestion, **kwargs)  # type: ignore[arg-type]


class CommandNotFoundError(ExecutionError):
    """Raised when :meth:`Sandbox.run` names a command the SandboxServer does not know.

    The command must be registered on the in-sandbox SandboxServer
    (``@sandbox.register`` / ``CommandRegistry``).
    """

    code = "E3005"

    def __init__(
        self,
        name: str,
        *,
        server_status: str = "",
        **kwargs: object,
    ) -> None:
        detail = kwargs.pop("detail", None)
        parts = [f"Command {name!r} not found."]
        if isinstance(detail, str) and detail.strip():
            parts.append(detail.strip().rstrip("."))
            parts[-1] += "."
        if server_status:
            parts.append(f"Server: {server_status}.")
        _suggestion = kwargs.pop("suggestion", None) or (
            "Check the command name against sandbox.list_commands() and make sure the "
            "SandboxServer is running (sandbox.start_server())."
        )
        super().__init__(
            " ".join(parts),
            suggestion=_suggestion,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )
        self.command_name = name


class EnvdRpcError(ExecutionError):
    """The sandbox envd rejected an RPC call with an HTTP error status.

    Raised by the transport layer (``HttpClient.envd_stream``) when the
    envd responds with HTTP >= 400 (e.g. a ``process.Process/Start`` 500
    for an unknown executable).  Carries the *structured* envd JSON error
    body (``envd_error``, parsed when the response body is JSON) so upper
    layers can map it to friendly messages, plus the HTTP status and RPC
    path.  The exception text deliberately avoids the full sandbox URL
    (which embeds the sandbox ID / internal host) — only the RPC path is
    included, and no separate WARNING log is emitted by default.
    """

    code = "E3006"
    suggestion = (
        "The sandbox envd rejected this RPC call. Check the command and "
        "arguments, or run with 'abx -v' for the raw error response."
    )

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        rpc_path: str = "",
        envd_error: dict[str, Any] | None = None,
        body_text: str = "",
        **kwargs: Any,
    ) -> None:
        self.status_code = status_code
        self.rpc_path = rpc_path
        self.envd_error = envd_error
        self.body_text = body_text
        super().__init__(message, **kwargs)


# --- Filesystem Errors (E4xxx) ---


class FileOperationError(SandboxError):
    """Base for filesystem operation failures."""

    code = "E4000"


class FileSizeLimitError(FileOperationError):
    """A streamed file response exceeded the caller's byte limit."""

    code = "E4003"
    suggestion = "Use a smaller file or explicitly increase max_bytes."

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__("File download exceeded the configured byte limit.")


class FileNotFoundError_(FileOperationError):  # noqa: N801, N818
    """File or directory not found in sandbox."""

    code = "E4001"
    suggestion = "Use files.list() to check available files, or files.exists() to verify path."
    # Note: named with underscore to avoid shadowing builtin FileNotFoundError


class PermissionDeniedError(FileOperationError):
    """Permission denied for file operation."""

    code = "E4002"
    suggestion = "Check file permissions in the sandbox."


# --- Session Errors (E6xxx) ---


class SessionError(SandboxError):
    """Base for session management failures."""

    code = "E6000"


class SessionNotFoundError(SessionError):
    """Session not found in the store."""

    code = "E6001"
    suggestion = (
        "Check session files in ~/.abx/sessions/ "
        "or use LocalSessionStore().list() programmatically."
    )


class SessionAlreadyExistsError(SessionError):
    """Session with the given name already exists."""

    code = "E6002"
    suggestion = "Use a different name or stop the existing session first."


# --- Network Errors (E5xxx) ---


class NetworkError(SandboxError):
    """Base for network/connection failures."""

    code = "E5000"


class ConnectionError_(NetworkError):  # noqa: N801, N818
    """Failed to connect to sandbox service."""

    code = "E5001"
    suggestion = "Check network connectivity and firewall rules."
    # Note: named with underscore to avoid shadowing builtin ConnectionError


class GitHubRateLimitError(NetworkError):
    """GitHub's anonymous API rate limit was hit while fetching templates.

    Deliberately shares the E5000 code of :class:`NetworkError`: to users
    it remains one network error, while the CLI can detect this subtype and
    offer a one-shot interactive ``github_token`` setup (task 206) before
    giving up.  The raised ``suggestion`` always carries the officially
    verified fine-grained PAT URL (see
    :mod:`agent_sandbox.utils.github_token`).
    """

    code = "E5000"


# --- Provider Errors (E8xxx) ---


class ProviderError(SandboxError):
    """Base for provider (backend plugin) failures."""

    code = "E8000"


class ProviderNotFoundError(ProviderError):
    """The provider id is unknown or not installed."""

    code = "E8001"
    suggestion = "Run 'abx provider list'; install with 'abx provider install <path-or-git-url>'."


class ProviderConfigError(ProviderError):
    """Unknown or invalid provider option, or a schema violation."""

    code = "E8002"


class ProviderConflictError(ProviderError):
    """Duplicate or reserved provider id."""

    code = "E8003"


class ProviderFeatureNotSupportedError(ProviderError, CapabilityNotSupportedError):
    """The selected provider does not implement the requested feature."""

    code = "E8004"

    def __init__(
        self,
        provider: str,
        feature: str,
        *,
        message: str | None = None,
        suggestion: str | None = None,
        **kwargs: object,
    ) -> None:
        self.provider = provider
        self.feature = feature
        CapabilityNotSupportedError.__init__(
            self,
            feature,
            message=message or f"Provider '{provider}' does not support '{feature}'.",
            suggestion=suggestion
            or f"Run 'abx provider info {provider}' to see supported features.",
            **kwargs,
        )


class ProviderResourceNotFoundError(ProviderError):
    """The provider reports that a sandbox, template or file does not exist."""

    code = "E8005"


class ProviderInstallError(ProviderError):
    """Source unreachable, or a size/path/type limit was violated."""

    code = "E8010"


class ProviderIntegrityError(ProviderError):
    """Digest/pin mismatch, or the files changed since installation."""

    code = "E8011"


class ProviderTrustError(ProviderError):
    """Consent, pinning or transport policy was not satisfied."""

    code = "E8012"


class ProviderVersionError(ProviderError):
    """The provider's ``requires`` or protocol is not supported by this host."""

    code = "E8013"


class ProviderManifestError(ProviderError):
    """``abx-provider.toml`` is invalid."""

    code = "E8014"


class ProviderProtocolError(ProviderError):
    """Malformed JSON-RPC traffic or a failed handshake with a plugin."""

    code = "E8020"


class ProviderProcessError(ProviderError):
    """The plugin process could not be spawned or crashed (stderr tail attached)."""

    code = "E8021"


class ProviderTimeoutError(ProviderError):
    """A plugin did not start or answer in time."""

    code = "E8022"


class ProviderMismatchError(ProviderError):
    """A sandbox reference belongs to a different provider than requested."""

    code = "E8030"


# --- In-sandbox server API errors (E9xxx) ---


class ServerAPIError(SandboxError):
    """The in-sandbox SandboxServer answered with an error.

    Attributes:
        status_code: HTTP status of the response (``0`` for client-side pre-checks).
        error_type: The server's ``type`` field (``ValueError``, ``PolicyDenied``, ...).
        error_code: The server's stable machine ``code`` (``path_not_allowed``, ...), if any.
        endpoint: Endpoint ID the server reported (or the client called).
        rule: The policy rule that decided (``policy:groups.file_ops``, ``default:opt-in:browser``),
            when the server names one.
    """

    code = "E9000"

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        error_type: str = "",
        error_code: str = "",
        endpoint: str = "",
        rule: str = "",
        suggestion: str | None = None,
        docs_url: str | None = None,
        code: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.rule = rule
        self.error_type = error_type
        self.error_code = error_code
        self.endpoint = endpoint
        SandboxError.__init__(self, message, code=code, suggestion=suggestion, docs_url=docs_url)


class CommandArgumentError(ServerAPIError):
    """A named command rejected its arguments (HTTP 400).

    The message is the server's validation error (missing, unexpected, or
    mistyped arguments).
    """

    code = "E9000"
    suggestion = "Compare the arguments with sandbox.list_commands()."


class CommandExecutionError(ServerAPIError):
    """A named command ran and raised (HTTP 500).

    ``error_type`` is the exception class name from the sandbox.
    """

    code = "E9000"
    suggestion = "The command function raised. error_type names the exception class."


class ServerAuthError(ServerAPIError, AuthenticationError):
    """The server rejected the credentials (HTTP 401) or the request carried ambiguous ones."""

    code = "E9001"
    suggestion = (
        "Pass the sandbox server token (ServerClient(token=...) / Sandbox.server_at(token=...))."
    )


class PolicyDeniedError(ServerAPIError):
    """The server policy denied the request (HTTP 403, or 409 ``file_exists``).

    Attributes:
        scope: The missing permission scope for ``missing_scope`` denials.
    """

    code = "E9002"
    suggestion = "Ask the template author to grant the scope/path, or call a permitted endpoint."

    def __init__(self, message: str, *, scope: str = "", **kwargs: Any) -> None:
        self.scope = scope
        super().__init__(message, **kwargs)


class FilePolicyDeniedError(PolicyDeniedError, PermissionDeniedError):
    """A path rule (allow/deny/read-only/symlink/extension/overwrite) denied a file operation.

    Also a :class:`PermissionDeniedError`, so existing ``except PermissionDeniedError`` handlers
    keep working.
    """

    code = "E9002"


class EndpointNotAvailableError(ServerAPIError, CapabilityNotSupportedError):
    """The endpoint is disabled by policy/group, or unknown to this server version.

    Also a :class:`CapabilityNotSupportedError`.  Raised both from the server's 404
    ``endpoint_disabled`` answer and from the client's discovery-based pre-check.
    """

    code = "E9003"

    def __init__(self, endpoint: str, *, message: str | None = None, **kwargs: Any) -> None:
        self.capability = endpoint
        kwargs.pop("endpoint", None)
        kwargs.setdefault("suggestion", "Use ServerCapabilities.can(endpoint) to check first.")
        super().__init__(
            message or f"Server endpoint '{endpoint}' is not available on this sandbox server.",
            endpoint=endpoint,
            **kwargs,
        )


class PayloadTooLargeError(ServerAPIError):
    """The request or response exceeded a server limit (HTTP 413).

    Attributes:
        limit: The limit in bytes the server reported (or the discovered limit), if known.
    """

    code = "E9004"
    suggestion = "Send less data or ask the template author to raise the limit."

    def __init__(self, message: str, *, limit: int | None = None, **kwargs: Any) -> None:
        self.limit = limit
        super().__init__(message, **kwargs)


class RateLimitedError(ServerAPIError):
    """The server rate-limited the request (HTTP 429).

    Attributes:
        retry_after: Seconds to wait before retrying, if the server said so.
    """

    code = "E9005"
    suggestion = "Retry after the indicated delay."

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


__all__ = [
    "SandboxError",
    "AuthenticationError",
    "InvalidAPIKeyError",
    "TokenExpiredError",
    "InvalidCredentialsError",
    "TokenExchangeError",
    "SandboxCreationError",
    "TemplateNotFoundError",
    "QuotaExceededError",
    "RegionUnavailableError",
    "TemplateParseError",
    "SandboxNotFoundError",
    "ExecutionError",
    "CommandTimeoutError",
    "ProcessError",
    "CodeExecutionError",
    "CapabilityNotSupportedError",
    "CommandNotFoundError",
    "EnvdRpcError",
    "FileOperationError",
    "FileNotFoundError_",
    "PermissionDeniedError",
    "NetworkError",
    "ConnectionError_",
    "GitHubRateLimitError",
    "SessionError",
    "SessionNotFoundError",
    "SessionAlreadyExistsError",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderConfigError",
    "ProviderConflictError",
    "ProviderFeatureNotSupportedError",
    "ProviderResourceNotFoundError",
    "ProviderInstallError",
    "ProviderIntegrityError",
    "ProviderTrustError",
    "ProviderVersionError",
    "ProviderManifestError",
    "ProviderProtocolError",
    "ProviderProcessError",
    "ProviderTimeoutError",
    "ProviderMismatchError",
    "ServerAPIError",
    "CommandArgumentError",
    "CommandExecutionError",
    "ServerAuthError",
    "PolicyDeniedError",
    "FilePolicyDeniedError",
    "EndpointNotAvailableError",
    "PayloadTooLargeError",
    "RateLimitedError",
]
