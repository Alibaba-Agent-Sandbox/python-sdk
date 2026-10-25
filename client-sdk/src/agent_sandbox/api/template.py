"""Launch an entire prepared template and retain all of its service clients."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.process import ProcessResult
from agent_sandbox.transport.streaming import StreamReader
from agent_sandbox.workflows.identity import bytes_digest
from agent_sandbox.workflows.launch import plan_template_launch, validate_template_manifest

if TYPE_CHECKING:
    from types import TracebackType

    from agent_sandbox.api.server_client import ServerClient
    from agent_sandbox.providers.base import Provider


class TemplateLaunchError(RuntimeError):
    """A phase-specific failure; durable journals retain uncertain or residual resources."""

    def __init__(self, reason: str, phase: str) -> None:
        self.reason, self.phase = reason, phase
        super().__init__(f"Template {phase}: {reason}")


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


class TemplateSession:
    """One complete template and the sandbox exclusively owned by this session."""

    def __init__(
        self,
        plan: dict[str, Any],
        sandbox: Sandbox | None,
        services: dict[str, ServerClient],
        journal: _Journal,
    ) -> None:
        self.plan, self.sandbox, self.services = plan, sandbox, services
        self.servers = {
            name: client
            for name, client in services.items()
            if plan["services"][name]["protocol"] == "agent-sandbox-server"
            and plan["services"][name]["version"] == 2
        }
        self.server = next(iter(self.servers.values())) if len(self.servers) == 1 else None
        self.journal_path = journal.path
        self._journal = journal
        self._closed = False
        self.creation_uncertain = False

    async def run_command(self, name: str, /, **arguments: Any) -> Any:
        """Call the sole SandboxServer; use ``servers[id]`` when there are several."""
        if self._closed or self.server is None:
            raise TemplateLaunchError("select-a-server-from-session.servers", "before-invoke")
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
            for client in self.services.values():
                try:
                    await asyncio.wait_for(client.aclose(), 10)
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
                raise TemplateLaunchError(
                    "journal-write-failed; owned cleanup attempted", "cleanup"
                )
            if failures:
                raise TemplateLaunchError(
                    "cleanup-failed; inspect owned resource journal", "cleanup"
                )
            if self.creation_uncertain:
                record("reconciliation-required")
                return
            record("cleanup-complete")
            if journal_failures:
                raise TemplateLaunchError(
                    "journal-write-failed; owned cleanup attempted", "cleanup"
                )
            self._closed = True

        task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def __aenter__(self) -> TemplateSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


async def _dispatch_start(sandbox: Sandbox, command: str, timeout: float) -> None:
    """Start the template once without binding startup to a particular service."""
    stream = await sandbox.commands._start_for_startup(command, timeout=86400)
    if not isinstance(stream, StreamReader):
        raise TemplateLaunchError("process-stream-missing", "before-start")
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
            raise TemplateLaunchError("startup-not-acknowledged", "before-start")
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


async def launch_template(
    manifest: dict[str, Any] | str | Path,
    *,
    provider: str | Provider,
    reference: str | None = None,
    application_token: str | None = None,
    provider_options: dict[str, Any] | None = None,
    envs: dict[str, str] | None = None,
    timeout: int = 300,
    readiness_timeout: float = 30,
    journal_path: str | Path | None = None,
) -> TemplateSession:
    """Start the complete template using a previously prepared provider reference.

    Python never builds source projects. Prepare sources with the CLI and pass
    the resulting reference, or declare an image/native template in the manifest.
    All services are returned. SandboxServer services are checked with health and
    discovery; other protocols use the template's ready_cmd for readiness.
    """
    from agent_sandbox.providers.registry import builtin_provider, get_provider

    if isinstance(manifest, (str, Path)):
        import yaml

        manifest_bytes = Path(manifest).read_bytes()
        snapshot = yaml.safe_load(manifest_bytes)
    else:
        snapshot = copy.deepcopy(manifest)
        manifest_bytes = json.dumps(snapshot, sort_keys=True).encode()
    snapshot = validate_template_manifest(snapshot)
    if snapshot.get("application"):
        raise TemplateLaunchError("deployment-orchestrator-required", "before-create")
    resolved = reference or snapshot.get("image") or snapshot.get("template_id")
    if not isinstance(resolved, str) or not resolved.strip():
        raise TemplateLaunchError("prepare-source-with-cli-and-pass-reference", "before-prepare")
    if snapshot.get("image") and not re.fullmatch(
        r"(?:[A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[a-f0-9]{64}", resolved
    ):
        raise TemplateLaunchError("immutable-image-reference-required", "before-create")
    if readiness_timeout <= 0:
        raise ValueError("readiness_timeout must be positive")
    effective_env = {
        key: value or os.environ.get(key, "") for key, value in snapshot.get("env", {}).items()
    }
    effective_env.update(envs or {})
    if application_token is not None:
        effective_env["ABX_SERVER_TOKEN"] = application_token
    token = effective_env.get("ABX_SERVER_TOKEN") or None
    if "ABX_SERVER_TOKEN" in effective_env and not token:
        raise TemplateLaunchError("application-token-required", "before-create")
    prov = get_provider(provider) if isinstance(provider, str) else provider
    plan = plan_template_launch(snapshot, prov.describe(), "python-provider", prepared=True)
    if not plan["supported"]:
        raise TemplateLaunchError(
            plan.get("reason") or ("missing-operations: " + ", ".join(plan["missing_operations"])),
            "before-create",
        )
    run_id = uuid4().hex
    journal = _Journal(
        Path(journal_path) if journal_path else Path.home() / ".abx" / "runs" / f"{run_id}.jsonl"
    )
    provider_digest = prov.content_digest()
    journal.append(
        "planned",
        run_id=run_id,
        provider_id=prov.id,
        manifest_digest=bytes_digest(manifest_bytes),
        provider_digest=provider_digest,
        contract_version=1,
        contract_digest=bytes_digest(
            Path(__file__).parents[1].joinpath("workflows/launch-v1.json").read_bytes()
        ),
    )
    creation_uncertain = False
    sandbox: Sandbox | None = None
    clients: dict[str, ServerClient] = {}
    session: TemplateSession | None = None
    try:
        if prov.content_digest() != provider_digest:
            raise TemplateLaunchError("provider-content-changed", "before-create")
        journal.append("create-intent", run_id=run_id, provider_id=prov.id)
        try:
            sandbox = await Sandbox.create(
                template=resolved,
                provider=prov.id if prov is builtin_provider() else provider,
                provider_options=provider_options,
                envs=effective_env,
                cpu=snapshot.get("cpu_count", snapshot.get("resources", {}).get("cpu")),
                memory=snapshot.get("memory_mb", snapshot.get("resources", {}).get("memory")),
                timeout=timeout,
                metadata={"abx_template_run": run_id},
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
            raise TemplateLaunchError("provider-content-changed", "before-start")
        if snapshot.get("start_cmd"):
            await _dispatch_start(sandbox, snapshot["start_cmd"], readiness_timeout)
            journal.append("started", sandbox_id=sandbox.id)
        if snapshot.get("ready_cmd"):
            loop = asyncio.get_running_loop()
            deadline = loop.time() + readiness_timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TemplateLaunchError("readiness-command-failed", "before-invoke")
                try:
                    result = await asyncio.wait_for(
                        sandbox.commands.run(
                            snapshot["ready_cmd"], timeout=max(1, math.ceil(remaining))
                        ),
                        timeout=remaining,
                    )
                except asyncio.TimeoutError:
                    raise TemplateLaunchError("readiness-command-failed", "before-invoke") from None
                if not isinstance(result, ProcessResult):
                    raise TemplateLaunchError("readiness-command-failed", "before-invoke")
                if result.exit_code == 0:
                    break
                await asyncio.sleep(min(0.25, max(0, deadline - loop.time())))
        for name, service in plan["services"].items():
            client = await sandbox.application_client(service["port"], token=token)
            clients[name] = client
            if service["protocol"] != "agent-sandbox-server" or service["version"] != 2:
                continue
            deadline = asyncio.get_running_loop().time() + readiness_timeout
            while not await client.health():
                if asyncio.get_running_loop().time() >= deadline:
                    raise TemplateLaunchError("application-not-ready: " + name, "before-invoke")
                await asyncio.sleep(0.2)
            discovery = await client.discover()
            if discovery.api_version != service["version"]:
                raise TemplateLaunchError("protocol-mismatch: " + name, "before-invoke")
            journal.append("protocol-checked", service=name, api_version=discovery.api_version)
        session = TemplateSession(plan, sandbox, clients, journal)
        return session
    except BaseException:
        if session is None:
            session = TemplateSession(plan, sandbox, clients, journal)
        session.creation_uncertain = creation_uncertain
        await session.close()
        raise
