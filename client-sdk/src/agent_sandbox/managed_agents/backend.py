"""Explicit native Express lifecycle; no CLI engine, HOME store or registry discovery."""

from __future__ import annotations

import json
import os
import ssl
from typing import Any

import httpx

from agent_sandbox.providers import ManagedExpressBackend as ExpressBackend

from .models import BRIDGE_PROTOCOL, ManagedError

__all__ = ["ExpressBackend", "bridge_request"]


async def bridge_request(
    resource: dict[str, Any], method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call a recorded private endpoint, preserving provider headers and app auth."""
    headers = dict(resource.get("headers", {}))
    occupied = {k.lower() for k in headers}
    if "x-access-token" not in occupied:
        headers["X-Access-Token"] = resource["token"]
    elif "authorization" not in occupied:
        headers["Authorization"] = "Bearer " + resource["token"]
    else:
        raise ManagedError(
            503,
            "authentication_collision",
            "Provider headers leave no application authentication channel",
        )
    async with httpx.AsyncClient(
        headers=headers,
        timeout=30,
        follow_redirects=False,
        trust_env=False,
        verify=ssl.create_default_context(cafile=os.getenv("ABX_MANAGED_TLS_CA_FILE")),
    ) as client:
        base = httpx.URL(resource["url"])
        url = base.copy_with(
            path=base.path.rstrip("/") + path.split("?")[0],
            query=b"&".join(x for x in (base.query, path.partition("?")[2].encode()) if x) or None,
        )
        async with client.stream(method, url, json=body) as response:
            if response.status_code >= 400:
                raise ManagedError(
                    503,
                    "guest_request_failed",
                    "The private runtime request could not be completed",
                )
            size = 0
            chunks = []
            async for chunk in response.aiter_bytes(chunk_size=65536):
                size += len(chunk)
                if size > 32000000:
                    raise ManagedError(
                        413, "guest_output_limit", "Private runtime output exceeded its budget"
                    )
                chunks.append(chunk)
            value = json.loads(b"".join(chunks))
        if not isinstance(value, dict):
            raise ManagedError(
                503, "invalid_guest_response", "The private runtime response is invalid"
            )
        if path == "/capabilities" and value.get("protocol") != BRIDGE_PROTOCOL:
            raise ManagedError(
                503, "guest_protocol_mismatch", "The Sandbox lacks the required managed bridge"
            )
        return value
