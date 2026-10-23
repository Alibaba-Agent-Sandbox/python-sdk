"""Explicit Python workflow launch with durable ownership and application preflight."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.process import ProcessResult
from agent_sandbox.transport.streaming import StreamReader
from agent_sandbox.workflows import plan_workflow
from agent_sandbox.workflows.identity import binding_digest, bytes_digest

if TYPE_CHECKING:
    from types import TracebackType

    from agent_sandbox.providers.base import Provider


class WorkflowError(RuntimeError):
    """A phase-specific failure; durable journals retain uncertain or residual resources."""

    def __init__(self, reason: str, phase: str) -> None:
        self.reason, self.phase = reason, phase
        super().__init__(f"Workflow {phase}: {reason}")


class _Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, **values: Any) -> None:
        payload = (json.dumps({"event": event, **values}, sort_keys=True) + "\n").encode()
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            with os.fdopen(descriptor, "ab") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            raise


class WorkflowSession:
    """One checked workflow and its exclusively owned sandbox, if any."""

    def __init__(
        self,
        plan: dict[str, Any],
        sandbox: Sandbox | None,
        server: ServerClient | None,
        journal: _Journal,
    ) -> None:
        self.plan, self.sandbox, self.server = plan, sandbox, server
        self.journal_path = journal.path
        self._journal = journal
        self._closed = False
        self.creation_uncertain = False

    async def run_command(self, name: str, /, **arguments: Any) -> Any:
        """Invoke the selected named-command workflow after protocol checks passed."""
        if self._closed or self.server is None or self.plan["kind"] != "application":
            raise WorkflowError("application-client-unavailable", "before-invoke")
        if self.plan["service"]["protocol"] != "agent-sandbox-server":
            raise WorkflowError("protocol-mismatch", "before-invoke")
        if self.plan["operation"] != "commands.run":
            raise WorkflowError("operation-mismatch", "before-invoke")
        result = await self.server.commands.run(name, **arguments)
        self._journal.append("invoked", operation="commands.run")
        return result

    async def close(self) -> None:
        """Attempt every owned cleanup even if client close fails or cancellation arrives."""
        if self._closed:
            return

        async def cleanup() -> None:
            failures = []
            journal_failures = []

            def record(event: str, **values: Any) -> None:
                try:
                    self._journal.append(event, **values)
                except BaseException as exc:
                    journal_failures.append(type(exc).__name__)

            if self.sandbox is not None:
                record(
                    "cleanup-intent", provider_id=self.sandbox.provider, sandbox_id=self.sandbox.id
                )
            if self.server is not None:
                try:
                    await asyncio.wait_for(self.server.aclose(), 10)
                except BaseException as exc:
                    failures.append(type(exc).__name__)
                    record("application-client-close-failed")
            if self.sandbox is not None:
                try:
                    await self.sandbox.kill()
                except BaseException as exc:
                    failures.append(type(exc).__name__)
                    record(
                        "cleanup-failed",
                        provider_id=self.sandbox.provider,
                        sandbox_id=self.sandbox.id,
                    )
                else:
                    record("deleted", provider_id=self.sandbox.provider, sandbox_id=self.sandbox.id)
            if journal_failures:
                raise WorkflowError("journal-write-failed; owned cleanup attempted", "cleanup")
            if failures:
                raise WorkflowError("cleanup-failed; inspect owned resource journal", "cleanup")
            if self.creation_uncertain:
                record("reconciliation-required")
                return
            record("cleanup-complete")
            if journal_failures:
                raise WorkflowError("journal-write-failed; owned cleanup attempted", "cleanup")
            self._closed = True

        task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def __aenter__(self) -> WorkflowSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


async def _dispatch_start(sandbox: Sandbox, command: str, timeout: float) -> None:
    """Acknowledge an exec workflow without requiring any application HTTP port."""
    stream = await sandbox.commands._start_for_startup(command, timeout=86400)
    if not isinstance(stream, StreamReader):
        raise WorkflowError("process-stream-missing", "before-start")
    started: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    async def drain() -> None:
        try:
            async for chunk in stream:
                if chunk.pid and not started.done():
                    started.set_result(True)
        finally:
            if not started.done():
                started.set_result(False)
            await stream.cancel()

    task = asyncio.create_task(drain())
    sandbox._server_stream_tasks.add(task)
    task.add_done_callback(sandbox._server_stream_tasks.discard)
    try:
        if not await asyncio.wait_for(started, timeout):
            raise WorkflowError("startup-not-acknowledged", "before-start")
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


async def launch_workflow(
    manifest: dict[str, Any] | str | Path,
    *,
    provider: str | Provider,
    workflow_id: str | None = None,
    reference: str | None = None,
    application_url: str | None = None,
    application_token: str | None = None,
    provider_options: dict[str, Any] | None = None,
    envs: dict[str, str] | None = None,
    timeout: int = 300,
    readiness_timeout: float = 30,
    journal_path: str | Path | None = None,
) -> WorkflowSession:
    """Launch a prepared image/reference or connect an explicit external service.

    Source preparation is a separate CLI operation; Python never starts Node to
    build sources for a native provider. A workflow with missing operations is
    rejected before creating resources. This standalone launcher does not execute
    application deployment hooks or silently reinterpret deployment topology.
    """
    from agent_sandbox.providers.registry import get_provider

    if isinstance(manifest, (str, Path)):
        import yaml

        manifest_bytes = Path(manifest).read_bytes()
        snapshot = yaml.safe_load(manifest_bytes)
    else:
        snapshot = copy.deepcopy(manifest)
        manifest_bytes = json.dumps(snapshot, sort_keys=True).encode()

    selected = workflow_id or snapshot.get("default_workflow")
    prov = get_provider(provider) if isinstance(provider, str) else provider
    plan = plan_workflow(snapshot, prov.describe(), selected, "python-provider")
    plan = {
        **plan,
        "startup": snapshot["workflows"][selected]["startup"],
        "operation": snapshot["workflows"][selected]["operation"],
    }
    if plan["state"] != "T":
        raise WorkflowError("requirements-unmet", "before-create")
    if snapshot.get("application"):
        raise WorkflowError("deployment-orchestrator-required", "before-create")
    if plan["input"] == "source":
        raise WorkflowError("source-preparation-unimplemented", "before-prepare")
    if plan["input"] == "service":
        if not application_url or plan["binding"]["endpoint"] != "explicit-url":
            raise WorkflowError("explicit-application-url-required", "before-invoke")
    elif not isinstance(reference, str) or not reference.strip():
        raise WorkflowError("prepared-reference-required", "before-create")
    artifact_digest = "unknown"
    if plan["input"] == "image":
        if not re.fullmatch(
            r"(?:[A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[a-f0-9]{64}", reference or ""
        ):
            raise WorkflowError("immutable-image-reference-required", "before-create")
        artifact_digest = "sha256:" + (reference or "").rsplit("sha256:", 1)[1]
    elif plan["input"] == "managed":
        raise WorkflowError("immutable-managed-reference-unresolved", "before-create")
    if plan["binding"]["authentication"] == "service-token" and not application_token:
        raise WorkflowError("application-token-required", "before-create")
    if plan["input"] == "service" and plan["kind"] != "application":
        raise WorkflowError("external-service-requires-application-client", "before-invoke")
    if readiness_timeout <= 0:
        raise ValueError("readiness_timeout must be positive")
    run_id = uuid4().hex
    journal = _Journal(
        Path(journal_path) if journal_path else Path.home() / ".abx" / "runs" / f"{run_id}.jsonl"
    )
    provider_digest = prov.content_digest()
    journal.append(
        "planned",
        run_id=run_id,
        provider_id=prov.id,
        workflow_id=selected,
        manifest_digest=bytes_digest(manifest_bytes),
        provider_digest=provider_digest,
        contract_version=1,
        contract_digest=bytes_digest(
            Path(__file__).parents[1].joinpath("workflows/workflow-v1.json").read_bytes()
        ),
        binding_digest=binding_digest(plan["binding"]),
        artifact_digest=artifact_digest,
        build_digest="unknown",
        template_source_digest="unknown",
        reference=reference if plan["input"] == "image" else None,
    )
    creation_uncertain = False
    sandbox: Sandbox | None = None
    client: ServerClient | None = None
    session: WorkflowSession | None = None
    try:
        if prov.content_digest() != provider_digest:
            raise WorkflowError("provider-content-changed", "before-create")
        if plan["input"] != "service":
            journal.append("create-intent", run_id=run_id, provider_id=prov.id)
            try:
                sandbox = await Sandbox.create(
                    template=cast("str", reference),
                    provider=prov,
                    provider_options=provider_options,
                    envs={
                        **(envs or {}),
                        **({"ABX_SERVER_TOKEN": application_token} if application_token else {}),
                    },
                    timeout=timeout,
                    metadata={"abx_workflow_run": run_id},
                    on_created=lambda sandbox_id: journal.append(
                        "created", sandbox_id=sandbox_id, provider_id=prov.id
                    ),
                )
            except BaseException as exc:
                resource = getattr(exc, "owned_resource", None)
                cleaned = getattr(exc, "resource_cleanup_complete", False)
                if resource and cleaned:
                    journal.append("deleted", **resource)
                creation_uncertain = not cleaned
                journal.append(
                    "create-uncertain" if creation_uncertain else "create-failed-cleaned",
                    run_id=run_id,
                    provider_id=prov.id,
                )
                raise
            journal.append("created", sandbox_id=sandbox.id, provider_id=prov.id)
            if prov.content_digest() != provider_digest:
                raise WorkflowError("provider-content-changed", "before-start")
            if plan["startup"] == "exec":
                if plan["kind"] == "application":
                    client = await sandbox.start_server(
                        command=snapshot["start_cmd"],
                        token=application_token,
                        port=plan["service"]["port"],
                        wait=False,
                        timeout=readiness_timeout,
                    )
                else:
                    await _dispatch_start(sandbox, snapshot["start_cmd"], readiness_timeout)
                journal.append("started", sandbox_id=sandbox.id)
            if snapshot.get("ready_cmd"):
                result = await sandbox.commands.run(
                    snapshot["ready_cmd"], timeout=int(readiness_timeout)
                )
                if not isinstance(result, ProcessResult) or result.exit_code != 0:
                    raise WorkflowError("readiness-command-failed", "before-invoke")
            if plan["kind"] == "application" and client is None:
                client = await sandbox.application_client(
                    plan["service"]["port"], token=application_token
                )
        else:
            client = ServerClient(cast("str", application_url), token=application_token)
        session = WorkflowSession(plan, sandbox, client, journal)
        if plan["kind"] == "application":
            if client is None:
                raise WorkflowError("application-client-unavailable", "before-invoke")
            deadline = asyncio.get_running_loop().time() + readiness_timeout
            while not await client.health():
                if asyncio.get_running_loop().time() >= deadline:
                    raise WorkflowError("application-not-ready", "before-invoke")
                await asyncio.sleep(0.2)
            discovery = await client.discover()
            if discovery.api_version != plan["service"]["version"]:
                raise WorkflowError("protocol-mismatch", "before-invoke")
            if snapshot["workflows"][selected]["operation"] == "commands.run":
                discovery.require("run_command")
            journal.append("protocol-checked", api_version=discovery.api_version)
        return session
    except BaseException:
        if session is None:
            session = WorkflowSession(plan, sandbox, client, journal)
        session.creation_uncertain = creation_uncertain
        await session.close()
        raise
