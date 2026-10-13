"""Signed envd file URLs.

envd accepts a file request that carries ``signature`` instead of the
``X-Access-Token`` header. The signature is SHA-256 of

``path:operation:username:accessToken[:expiration]``

encoded as unpadded base64 and prefixed with ``v1_``. ``operation`` is
``read`` or ``write``. ``expiration``, when set, is a Unix timestamp in
seconds. The access token itself is not placed in the URL.
"""

from __future__ import annotations

import base64
import hashlib
import time
from typing import Literal
from urllib.parse import urlencode

from easy_sandbox.models.errors import TokenExpiredError

FileOperation = Literal["read", "write"]


def file_signature(
    *,
    path: str,
    operation: FileOperation,
    username: str,
    access_token: str,
    expiration: int | None = None,
) -> str:
    """Return the ``v1_`` signature envd checks for one file operation."""
    parts = [path, operation, username, access_token]
    if expiration is not None:
        parts.append(str(expiration))
    digest = hashlib.sha256(":".join(parts).encode()).digest()
    return "v1_" + base64.b64encode(digest).decode("ascii").rstrip("=")


def signed_file_url(
    envd_url: str,
    *,
    path: str,
    operation: FileOperation,
    access_token: str | None,
    username: str = "user",
    expires_in: int | None = None,
) -> str:
    """Build ``{envd}/files?...&signature=`` for a browser or another client.

    ``expires_in`` is a lifetime in seconds from now. Omit it for a signature
    that does not expire. A missing access token cannot be signed.
    """
    if not access_token:
        raise TokenExpiredError(
            "envdAccessToken is not available, so a signed file URL cannot be built.",
            suggestion="Create or connect to a sandbox that returns envdAccessToken.",
        )
    if expires_in is not None and expires_in < 0:
        raise ValueError("use_signature_expiration must be a non-negative number of seconds")
    if not envd_url:
        raise ValueError("Sandbox has no envd URL, so a signed file URL cannot be built.")

    expiration = None if expires_in is None else int(time.time()) + expires_in
    signature = file_signature(
        path=path,
        operation=operation,
        username=username,
        access_token=access_token,
        expiration=expiration,
    )
    query = {"path": path, "username": username, "signature": signature}
    if expiration is not None:
        query["signature_expiration"] = str(expiration)
    return f"{envd_url.rstrip('/')}/files?{urlencode(query)}"
