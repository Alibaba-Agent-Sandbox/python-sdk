"""Async HTTP client for Platform API and sandbox envd API.

Uses httpx.AsyncClient with HTTP/2 support. A long-lived client is kept for
the Platform API; envd clients are created on demand per sandbox URL.

envd URL 格式: https://49983-{sandbox_id}.{domain}（已实测验证）
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

from agent_sandbox.models.errors import (
    ConnectionError_,
    EnvdRpcError,
    FileOperationError,
    FileSizeLimitError,
    InvalidAPIKeyError,
    InvalidCredentialsError,
)
from agent_sandbox.transport.auth import AkSkAuth
from agent_sandbox.transport.codec import (
    CONNECT_CONTENT_TYPE,
    ConnectCodec,
    EnvelopeStreamParser,
    json_decode,
)
from agent_sandbox.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_sandbox.transport.auth import AuthProvider, EnvdTokenManager
    from agent_sandbox.transport.config import TransportConfig

logger = get_logger("transport.http")

# Upper bound on bytes read from an envd error response body (defensive —
# an error body is diagnostic text, not data; avoid buffering anything huge).
_MAX_ERROR_BODY_BYTES = 8192

# How much of the error body is kept in the exception / logs.
_ERROR_BODY_TEXT_LIMIT = 500


def _envd_error_detail(envd_error: dict[str, Any] | None) -> str:
    """Extract a human-readable detail string from an envd JSON error body.

    Covers the shapes observed from envd / Connect implementations:
    ``{"error": {"code": ..., "message": ...}}``, ``{"error": "text"}``,
    and flat ``{"code": ..., "message": ...}`` / ``{"message": ...}``.
    Returns ``""`` when nothing readable is found.
    """
    if not isinstance(envd_error, dict):
        return ""
    err = envd_error.get("error")
    if isinstance(err, dict):
        for key in ("message", "msg", "detail", "code"):
            val = err.get(key)
            if isinstance(val, str) and val:
                return val
    elif isinstance(err, str):
        return err
    for key in ("message", "msg", "detail", "code"):
        val = envd_error.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def _build_envd_rpc_error(raw: bytes, status_code: int, rpc_path: str) -> EnvdRpcError:
    """Build an :class:`EnvdRpcError` from an envd error response body (no sandbox URL in it)."""
    raw = raw[:_MAX_ERROR_BODY_BYTES]
    body_text = raw.decode("utf-8", errors="replace")[:_ERROR_BODY_TEXT_LIMIT]

    envd_error: dict[str, Any] | None = None
    if raw:
        try:
            parsed = ConnectCodec.decode_response(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            envd_error = parsed

    detail = _envd_error_detail(envd_error) or body_text.strip()
    message = f"envd RPC {rpc_path} failed (HTTP {status_code})"
    if detail:
        message = f"{message}: {detail}"
    return EnvdRpcError(
        message,
        status_code=status_code,
        rpc_path=rpc_path,
        envd_error=envd_error,
        body_text=body_text,
    )


def stream_envelope_for_envd(version: str | None) -> bool:
    """Whether streaming Connect calls to this envd must use the 5-byte envelope.

    Express generation 2 reports envd 0.6 and newer. That envd reads a streaming
    body as an enveloped message and rejects raw JSON (``promised N bytes in
    enveloped message``). Generation 1 envd 0.5.x accepted the raw body. An
    unknown or unparsable version uses the envelope.
    """
    if version is None or not version.strip():
        return True
    numbers: list[int] = []
    for part in version.strip().lstrip("vV").split("."):
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        numbers.append(int(digits))
    if len(numbers) < 2:
        return True
    return not (numbers[0] == 0 and numbers[1] < 6)


def _trailer_error(trailer: dict[str, Any], rpc_path: str) -> EnvdRpcError:
    """``EnvdRpcError`` for a Connect end-stream trailer (or a raw JSON error body)."""
    err = trailer.get("error")
    code = ""
    detail = ""
    if isinstance(err, dict):
        raw_code = err.get("code")
        raw_message = err.get("message")
        if isinstance(raw_code, str):
            code = raw_code
        if isinstance(raw_message, str):
            detail = raw_message
        if not detail:
            detail = _envd_error_detail(trailer)
    elif isinstance(err, str):
        detail = err
    else:
        detail = _envd_error_detail(trailer)
    if code and detail and not detail.startswith(code):
        detail = f"{code}: {detail}"
    elif code and not detail:
        detail = code
    message = f"envd RPC {rpc_path} failed"
    if detail:
        message = f"{message}: {detail}"
    return EnvdRpcError(
        message,
        rpc_path=rpc_path,
        envd_error=trailer,
        body_text=detail,
    )


def _error_from_buffered_body(raw: bytes, rpc_path: str) -> EnvdRpcError | None:
    """Parse a leftover body that was not a sequence of data frames.

    A gen2 envd can answer a bad streaming call with one enveloped error, or
    with a raw JSON object. Either shape carries ``error.code`` / ``error.message``.
    """
    body = raw.strip()
    if len(body) >= 5 and body[0] in (0, 2):
        length = struct.unpack(">I", body[1:5])[0]
        if length == len(body) - 5:
            body = body[5:]
    if not body:
        return None
    try:
        parsed = json_decode(body)
    except Exception:
        return None
    if isinstance(parsed, dict) and parsed.get("error"):
        return _trailer_error(parsed, rpc_path)
    return None


def envd_status_error(exc: httpx.HTTPStatusError, rpc_path: str) -> EnvdRpcError:
    """Convert the ``HTTPStatusError`` of a unary envd call into an :class:`EnvdRpcError`.

    Same shape as the error raised for streaming calls: the message carries the RPC path, the
    HTTP status and the envd detail (e.g. ``process not found``), never the sandbox URL.
    """
    return _build_envd_rpc_error(exc.response.content, exc.response.status_code, rpc_path)


class _DialTransport(httpx.AsyncBaseTransport):
    """Open the TCP connection to *host*:*port* and keep the original Host."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        original = request.url.netloc
        request.url = request.url.copy_with(host=self._host, port=self._port)
        request.headers["host"] = original.decode("latin-1")
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


class HttpClient:
    """Async HTTP client for Platform API and envd API.

    A single long-lived httpx.AsyncClient is used for the Platform API.
    Envd clients are created on demand (different sandboxes may have
    different base URLs) and tracked for proper cleanup.
    """

    def __init__(
        self,
        config: TransportConfig,
        auth: AuthProvider,
        *,
        envelope_connect: bool = False,
        stream_envelope: bool = True,
        envd_dial: tuple[str, int] | None = None,
        envd_headers: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._auth = auth
        self._codec = ConnectCodec()
        self._envelope = envelope_connect
        # Streaming RPCs (process start/connect) use the 5-byte Connect envelope.
        # Unary RPCs stay raw JSON. Generation-1 envd opts out via ``stream_envelope``.
        self._stream_envelope = stream_envelope
        self._dial = envd_dial
        self._envd_headers = dict(envd_headers or {})
        self._platform_client: httpx.AsyncClient | None = None
        self._envd_clients: dict[str, httpx.AsyncClient] = {}

    def _connect_body(self, payload: dict[str, Any] | None) -> tuple[bytes, dict[str, str]]:
        raw = self._codec.encode_request(payload or {})
        if not self._envelope:
            return raw, {}
        framed = struct.pack(">BI", 0, len(raw)) + raw
        return framed, {
            "Connect-Protocol-Version": "1",
            "Connect-Content-Encoding": "identity",
        }

    def _stream_body(self, payload: dict[str, Any] | None) -> tuple[bytes, dict[str, str]]:
        """Connect streaming body: 5-byte envelope around the JSON message.

        Generation-2 envd (v0.6+) rejects an unenveloped body. The first bytes of
        raw JSON are read as a length, which is the ``promised N bytes`` error.
        """
        raw = self._codec.encode_request(payload or {})
        if not self._stream_envelope:
            return raw, {}
        return struct.pack(">BI", 0, len(raw)) + raw, {
            "Connect-Protocol-Version": "1",
            "Connect-Content-Encoding": "identity",
        }

    def _envd_client_kwargs(self) -> dict[str, Any]:
        if self._dial is None:
            return {}
        return {"transport": _DialTransport(*self._dial)}

    async def _get_platform_client(self) -> httpx.AsyncClient:
        """Get or create the Platform API client."""
        if self._platform_client is None or self._platform_client.is_closed:
            self._platform_client = httpx.AsyncClient(
                base_url=self._config.sandbox_base_url,
                http2=self._config.http2,
                timeout=httpx.Timeout(self._config.http_timeout),
                limits=httpx.Limits(
                    max_connections=self._config.max_connections,
                    max_keepalive_connections=self._config.max_keepalive_connections,
                    keepalive_expiry=self._config.keepalive_expiry,
                ),
            )
        return self._platform_client

    def _create_envd_client(self, envd_url: str) -> httpx.AsyncClient:
        """Create (or reuse a cached) envd API client for a sandbox URL."""
        existing = self._envd_clients.get(envd_url)
        if existing is not None and not existing.is_closed:
            return existing
        client = httpx.AsyncClient(
            base_url=envd_url,
            http2=self._config.http2,
            timeout=httpx.Timeout(self._config.http_timeout),
            **self._envd_client_kwargs(),
        )
        self._envd_clients[envd_url] = client
        return client

    async def platform_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> httpx.Response:
        """Send a request to the Platform API (REST).

        Automatically injects authentication headers.

        Args:
            request_timeout: Per-request timeout override in seconds.
                When provided, overrides the client-level default
                ``http_timeout`` from :class:`TransportConfig` for this
                single request.  When *None*, the client-level default
                (i.e. ``SANDBOX_HTTP_TIMEOUT`` / ``Config.http_timeout``)
                is used unchanged.
        """
        client = await self._get_platform_client()
        auth_headers = await self._auth.get_headers()

        all_headers = {**auth_headers}
        if headers:
            all_headers.update(headers)

        # Build optional per-request timeout override (mirrors envd_request).
        extra_kwargs: dict[str, Any] = {}
        if request_timeout is not None:
            extra_kwargs["timeout"] = httpx.Timeout(request_timeout)

        logger.debug("Platform %s %s", method, path)
        try:
            response = await client.request(
                method=method,
                url=path,
                json=json,
                params=params,
                headers=all_headers,
                **extra_kwargs,
            )
            response.raise_for_status()
            return response
        except httpx.ConnectError as exc:
            raise ConnectionError_(
                f"Failed to connect to Platform API: {exc}",
                suggestion="Check network connectivity and API base URL.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise self._authentication_error(path) from exc
            # Let higher layers handle the other HTTP errors
            raise

    def _authentication_error(self, path: str) -> InvalidAPIKeyError | InvalidCredentialsError:
        """The SDK error for a Platform API 401 (the exception text never includes the URL)."""
        if isinstance(self._auth, AkSkAuth):
            return InvalidCredentialsError(
                f"The Platform API rejected the AK/SK credentials (HTTP 401) for {path}."
            )
        return InvalidAPIKeyError(
            f"The Platform API rejected the API key (HTTP 401) for {path}: "
            "it is invalid, revoked or for another region."
        )

    async def envd_request(
        self,
        envd_url: str,
        rpc_path: str,
        *,
        payload: dict[str, Any] | None = None,
        envd_token: EnvdTokenManager,
        headers: dict[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a Connect RPC request to the envd API.

        Args:
            envd_url: Base URL of the sandbox envd.
            rpc_path: RPC path (e.g., "/process.Process/Start").
            payload: Request body dict.
            envd_token: Token manager for this sandbox.
            headers: Additional headers.
            request_timeout: Per-request timeout override in seconds.
                When provided, overrides the default ``http_timeout``
                from :class:`TransportConfig` for this single request.
                When *None*, the client-level default is used.

        Returns:
            Decoded response dict.
        """
        client = self._create_envd_client(envd_url)
        auth_headers = envd_token.get_headers()

        # Unary RPCs are raw JSON (no 5-byte frame). Generation-2 envd answers
        # ``application/connect+json`` with HTTP 415 and wants ``application/json``.
        # Generation-1 envd (``stream_envelope`` off) keeps ``application/connect+json``.
        if self._stream_envelope or self._envelope:
            body = self._codec.encode_request(payload or {})
            content_type = "application/json"
            framed: dict[str, str] = {}
        else:
            body, framed = self._connect_body(payload)
            content_type = CONNECT_CONTENT_TYPE
        all_headers = {
            "Content-Type": content_type,
            **framed,
            **auth_headers,
            **self._envd_headers,
        }
        if headers:
            all_headers.update(headers)

        # Build optional per-request timeout override
        extra_kwargs: dict[str, Any] = {}
        if request_timeout is not None:
            extra_kwargs["timeout"] = httpx.Timeout(request_timeout)

        logger.debug("envd POST %s%s", envd_url, rpc_path)
        try:
            response = await client.post(
                url=rpc_path,
                content=body,
                headers=all_headers,
                **extra_kwargs,
            )
            response.raise_for_status()
            return self._codec.decode_response(response.content)
        except httpx.ConnectError as exc:
            raise ConnectionError_(
                f"Failed to connect to sandbox envd: {exc}",
                suggestion="Check if the sandbox is still running.",
            ) from exc

    async def _raise_envd_rpc_error(
        self,
        response: httpx.Response,
        rpc_path: str,
    ) -> NoReturn:
        """Build and raise an :class:`EnvdRpcError` from an envd error response.

        Reads a *bounded* slice of the error body, parses it as JSON when
        possible (structured propagation for upper layers), and logs the
        details at DEBUG level only — never a default WARNING, and never
        with the full sandbox URL (which embeds the sandbox ID).  The RPC
        path (e.g. ``/process.Process/Start``) is not sensitive and is kept
        for diagnostics.  Task 166.
        """
        raw = b""
        async for chunk in response.aiter_bytes():
            raw += chunk
            if len(raw) >= _MAX_ERROR_BODY_BYTES:
                raw = raw[:_MAX_ERROR_BODY_BYTES]
                break
        error = _build_envd_rpc_error(raw, response.status_code, rpc_path)
        logger.debug(
            "envd STREAM %s failed (HTTP %s): %s",
            rpc_path,
            response.status_code,
            error.body_text,
        )
        raise error

    async def envd_stream(
        self,
        envd_url: str,
        rpc_path: str,
        *,
        payload: dict[str, Any] | None = None,
        envd_token: EnvdTokenManager,
        headers: dict[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a Connect RPC streaming request to the envd API.

        Returns an async iterator of decoded response frames.
        Connect streaming uses binary envelope framing (已实测验证):
          flags (1 byte) + length (4 bytes big-endian) + JSON payload

        The response is consumed incrementally via ``client.stream()`` +
        ``aiter_bytes()`` so frames are yielded as soon as they arrive
        (server-side per-line output is visible line by line).  The full
        response body is never buffered — only a single in-flight frame is
        held in memory.

        NOTE: A fresh httpx client is used for each streaming call to
        avoid HTTP/2 connection-state issues observed with connection
        reuse on some envd versions (cached connections that served
        earlier unary RPCs can return spurious 500 errors on subsequent
        streaming calls).

        Resource cleanup: both the streaming response and the client are
        managed by ``async with``.  They are closed on normal completion,
        on errors, on cancellation (``CancelledError``), and when the
        consumer stops iterating early (``GeneratorExit`` propagated by
        ``aclose()`` / garbage collection of the generator).

        Error responses (HTTP >= 400) raise :class:`EnvdRpcError` — a
        structured :class:`~agent_sandbox.models.errors.SandboxError`
        carrying the parsed envd JSON error body, the status code and the
        RPC path.  No default WARNING is logged for the error body and the
        exception text never contains the full sandbox URL (task 166; the
        CLI/connect-layer friendly mapping is handled separately).

        Args:
            request_timeout: Per-request timeout override in seconds.
                When provided, overrides the default ``http_timeout``
                from :class:`TransportConfig` for this streaming call.
                When *None*, ``self._config.http_timeout`` is used.
        """
        auth_headers = envd_token.get_headers()

        body, framed = self._stream_body(payload)
        all_headers = {
            "Content-Type": CONNECT_CONTENT_TYPE,
            **framed,
            **auth_headers,
            **self._envd_headers,
        }
        if headers:
            all_headers.update(headers)
        effective_timeout = (
            request_timeout if request_timeout is not None else self._config.http_timeout
        )

        logger.debug("envd STREAM %s%s (timeout=%.1fs)", envd_url, rpc_path, effective_timeout)
        try:
            # Use a fresh client per streaming call (see NOTE above) and a
            # true streaming request so frames are decoded incrementally
            # as network chunks arrive.
            async with httpx.AsyncClient(
                http2=self._config.http2,
                timeout=httpx.Timeout(effective_timeout),
                **self._envd_client_kwargs(),
            ) as client:
                url = envd_url.rstrip("/") + rpc_path
                async with client.stream(
                    "POST",
                    url=url,
                    content=body,
                    headers=all_headers,
                ) as response:
                    if response.status_code >= 400:
                        # Structured error propagation instead of httpx's
                        # raise_for_status (whose message embeds the full
                        # sandbox URL and an MDN status link).
                        await self._raise_envd_rpc_error(response, rpc_path)

                    parser = EnvelopeStreamParser()
                    async for chunk in response.aiter_bytes():
                        for frame in parser.feed(chunk):
                            yield frame
                        if parser.stream_error is not None:
                            raise _trailer_error(parser.stream_error, rpc_path)

                    if parser.stream_error is not None:
                        raise _trailer_error(parser.stream_error, rpc_path)
                    if parser.pending_bytes():
                        buffered_error = _error_from_buffered_body(parser.buffered(), rpc_path)
                        if buffered_error is not None:
                            raise buffered_error
                        logger.warning(
                            "envd STREAM %s ended with %d truncated byte(s); "
                            "incomplete final frame dropped",
                            rpc_path,
                            parser.pending_bytes(),
                        )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ConnectionError_(
                f"Failed to connect to sandbox envd for streaming: {exc}",
                suggestion="Check if the sandbox is still running.",
            ) from exc

    async def envd_http_request(
        self,
        envd_url: str,
        method: str,
        path: str,
        *,
        envd_token: EnvdTokenManager,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        files: dict[str, Any] | None = None,
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        """Send a plain HTTP request (not Connect RPC) to the envd API.

        Used for file upload/download which use standard HTTP
        rather than Connect protocol (已实测验证).
        """
        if max_response_bytes is not None and (
            type(max_response_bytes) is not int or max_response_bytes < 0
        ):
            raise ValueError("max_response_bytes must be a nonnegative integer")
        client = self._create_envd_client(envd_url)
        auth_headers = envd_token.get_headers()

        all_headers = {**auth_headers, **self._envd_headers}
        if headers:
            all_headers.update(headers)

        logger.debug("envd HTTP %s %s%s", method, envd_url, path)
        try:
            if max_response_bytes is not None:
                # Count actual file bytes without allowing a compressed raw
                # chunk to inflate before the limit check. Old reads are unchanged.
                all_headers = {
                    key: value
                    for key, value in all_headers.items()
                    if key.lower() != "accept-encoding"
                }
                all_headers["Accept-Encoding"] = "identity"
                async with client.stream(
                    method=method,
                    url=path,
                    params=params,
                    headers=all_headers,
                    content=content,
                    files=files,
                ) as streamed:
                    # Error details are intentionally not read: a hostile error
                    # body can also be infinite. Preserve the status for mapping.
                    if streamed.is_error:
                        failed = httpx.Response(streamed.status_code, request=streamed.request)
                        failed.raise_for_status()
                    if (
                        streamed.headers.get("content-encoding", "identity").strip().lower()
                        != "identity"
                    ):
                        raise FileOperationError(
                            "Bounded file downloads require identity content encoding."
                        )
                    data = bytearray()
                    async for chunk in streamed.aiter_raw(chunk_size=65536):
                        if len(data) + len(chunk) > max_response_bytes:
                            raise FileSizeLimitError(max_response_bytes)
                        data.extend(chunk)
                    return httpx.Response(
                        streamed.status_code,
                        headers={
                            key: value
                            for key, value in streamed.headers.items()
                            if key.lower()
                            not in {"content-encoding", "content-length", "transfer-encoding"}
                        },
                        content=bytes(data),
                        request=streamed.request,
                    )
            response = await client.request(
                method=method,
                url=path,
                params=params,
                headers=all_headers,
                content=content,
                files=files,
            )
            response.raise_for_status()
            return response
        except httpx.ConnectError as exc:
            raise ConnectionError_(
                f"Failed to connect to sandbox envd: {exc}",
                suggestion="Check if the sandbox is still running.",
            ) from exc

    async def close(self) -> None:
        """Close all HTTP clients and release connections."""
        if self._platform_client and not self._platform_client.is_closed:
            await self._platform_client.aclose()
            self._platform_client = None

        for _url, client in list(self._envd_clients.items()):
            if not client.is_closed:
                await client.aclose()
        self._envd_clients.clear()
        logger.debug("All HTTP clients closed")

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
