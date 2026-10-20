"""Explicit typed async client for the application run API (not local Agents API)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .models import ApplicationError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class AgentRun(BaseModel):
    """Public durable run state."""

    model_config = ConfigDict(populate_by_name=True)
    id: str
    application_revision: str = Field(alias="applicationRevision")
    execution_snapshot_digest: str = Field(alias="executionSnapshotDigest")
    placement: Literal["external", "in-sandbox"]
    status: Literal[
        "accepted",
        "queued",
        "provisioning",
        "running",
        "cancelling",
        "requires_reconcile",
        "succeeded",
        "failed",
        "cancelled",
        "timed_out",
    ]
    event_integrity: Literal["complete", "incomplete"] = Field(alias="eventIntegrity")
    created_at: str = Field(alias="createdAt")
    attempt_id: str | None = Field(alias="attemptId")
    links: dict[str, str]
    failure: dict[str, str] | None = None


class AgentEvent(BaseModel):
    """Committed run event; sequence is scoped to its run."""

    model_config = ConfigDict(populate_by_name=True)
    run_id: str = Field(alias="runId")
    attempt_id: str | None = Field(alias="attemptId")
    seq: int
    type: str
    occurred_at: str = Field(alias="occurredAt")
    data: dict[str, Any]


class RunArtifact(BaseModel):
    """Durably retained artifact ID; never an arbitrary server path."""

    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str
    content_link: str = Field(alias="contentLink")


class AgentResult(BaseModel):
    """Immutable terminal result; reading it cannot restart an execution."""

    model_config = ConfigDict(populate_by_name=True)
    run_id: str = Field(alias="runId")
    status: Literal["succeeded", "failed", "cancelled", "timed_out"]
    output_text: str = Field(alias="outputText")
    artifacts: list[RunArtifact]
    failure_code: str | None = Field(default=None, alias="failureCode")


class ApplicationClient:
    """Async application client; mutating requests are never automatically retried."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 35,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": "Bearer " + token}
        self._owned = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False
        )

    async def __aenter__(self) -> ApplicationClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the owned HTTP client; injected clients remain caller-owned."""
        if self._owned:
            await self._http.aclose()

    @staticmethod
    def _path(run_id: str) -> str:
        return "/v1/agent-runs/" + quote(run_id, safe="")

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.is_error:
            # Never propagate untrusted remote response bodies/SDK exception URLs.
            raise ApplicationError(
                response.status_code, "request_failed", "Application API request did not succeed"
            )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        response = await self._http.request(method, self._base + path, headers=headers, **kwargs)
        self._check(response)
        return response.json()

    async def create(self, revision: str, text: str, *, idempotency_key: str) -> AgentRun:
        """Durably accept input using an explicit caller-generated idempotency key."""
        return AgentRun.model_validate(
            await self._request(
                "POST",
                "/v1/agent-runs",
                headers={"Idempotency-Key": idempotency_key},
                json={"applicationRevision": revision, "input": {"text": text}},
            )
        )

    async def get(self, run_id: str) -> AgentRun:
        """Read current authoritative state."""
        return AgentRun.model_validate(await self._request("GET", self._path(run_id)))

    async def cancel(self, run_id: str) -> AgentRun:
        """Record cancellation intent; inspect state to confirm remote work stopped."""
        return AgentRun.model_validate(await self._request("POST", self._path(run_id) + "/cancel"))

    async def result(self, run_id: str) -> AgentResult:
        """Read terminal output, or receive 409 while unfinished."""
        return AgentResult.model_validate(
            await self._request("GET", self._path(run_id) + "/result")
        )

    async def artifact(self, run_id: str, artifact_id: str) -> bytes:
        """Download only an artifact ID associated with an owned run."""
        response = await self._http.get(
            self._base
            + self._path(run_id)
            + "/artifacts/"
            + quote(artifact_id, safe="")
            + "/content",
            headers=self._headers,
        )
        self._check(response)
        return response.content

    async def events(self, run_id: str, *, after: int = 0) -> AsyncIterator[AgentEvent]:
        """Read one bounded SSE connection; reconnect explicitly with the last sequence."""
        if after < 0:
            raise ValueError("Event cursor must be nonnegative")
        async with self._http.stream(
            "GET",
            self._base + self._path(run_id) + "/events",
            headers={**self._headers, "Last-Event-ID": str(after)},
        ) as response:
            self._check(response)
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    if len(line) > 131072:
                        raise ValueError("Application event exceeds size limit")
                    yield AgentEvent.model_validate(json.loads(line[6:]))
