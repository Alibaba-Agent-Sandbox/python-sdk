"""Finite workers and durable dispatch, independent of any web framework."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from .models import Application, ApplicationError, ExecutionResult, Principal

if TYPE_CHECKING:
    from collections.abc import Callable

    from .store import Store


class Executor(Protocol):
    """Exclusive executor; callbacks must cooperate with asyncio cancellation.

    Cleanup verifies remote work stopped. Applications must isolate blocking
    callbacks; Python cannot forcibly stop arbitrary in-process code.
    """

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Run Agent code and return output before releasing the sandbox."""
        ...

    async def close(self) -> bool:
        """Stop/release owned resources; return False for uncertain cleanup."""
        ...


@dataclass(frozen=True)
class ExecutionContext:
    """Run-scoped access. Check immediately before each model/tool/resource call."""

    store: Store
    run_id: str
    attempt: str
    prompt: str
    snapshot: dict[str, Any]
    stopping: asyncio.Event = field(default_factory=asyncio.Event, compare=False)

    def check(self) -> None:
        """Fail before new work once cancel, deadline or lease fencing applies."""
        if self.stopping.is_set():
            raise ApplicationError(409, "execution_stopped", "Run is stopping")
        row = self.store.get(self.run_id)
        self.store._check_attempt(row, self.attempt)
        if row["cancel"] or time.time() >= row["deadline"]:
            raise ApplicationError(409, "execution_stopped", "Run is stopping")

    def emit(self, kind: str, data: dict[str, Any]) -> None:
        """Persist a public, non-secret event."""
        self.check()
        self.store.emit(self.run_id, self.attempt, kind, data)

    def resource(self, receipt: dict[str, Any]) -> None:
        """Record resource identity without tokens or signed URLs."""
        self.store.bind_resource(self.run_id, self.attempt, receipt)


@dataclass
class ApplicationRuntime:
    """Deployment-supplied trusted wiring shared by gateway/worker/dispatcher.

    ``send_task`` returns only after the task platform durably accepts an event,
    or raises. Its delivery may be duplicated. Workers claim runs conditionally.
    ``authenticate`` must validate expiry/revocation on every incoming request.
    """

    store: Store
    applications: dict[str, Application]
    executor_factory: Callable[[Application], Executor]
    send_task: Callable[[dict[str, str]], None]
    authenticate: Callable[[str], Principal | None]
    heartbeat_seconds: float = 2.0
    cleanup_seconds: float = 30.0

    def create(self, principal: Principal, key: str, body: dict[str, Any]) -> dict[str, Any]:
        """Authorize and validate a create request before durable acceptance."""
        principal.require("runs:write")
        if (
            not key
            or len(key) > 128
            or not key.isascii()
            or not key.isprintable()
            or set(body) != {"applicationRevision", "input"}
        ):
            raise ApplicationError(
                400, "invalid_request", "Invalid create request or idempotency key"
            )
        revision, value = body["applicationRevision"], body["input"]
        if (
            not isinstance(revision, str)
            or not isinstance(value, dict)
            or set(value) != {"text"}
            or not isinstance(value["text"], str)
            or not value["text"]
            or len(value["text"]) > 65536
        ):
            raise ApplicationError(400, "invalid_request", "Input must contain bounded text")
        if revision not in principal.revisions or revision not in self.applications:
            raise ApplicationError(404, "not_found", "Application revision was not found")
        return self.store.create(principal.owner, self.applications[revision], key, body)

    def dispatch(self, *, limit: int = 20, max_seconds: float = 20) -> int:
        """Bounded durable outbox drain; invoke periodically via an external trigger."""
        self.store.reconcile()
        sent = 0
        deadline = time.monotonic() + max_seconds
        for _ in range(max(0, min(limit, 100))):
            if time.monotonic() >= deadline:
                break
            leased = self.store.next_dispatch()
            if leased is None:
                break
            run_id, token = leased
            try:
                self.send_task({"runId": run_id})
            except Exception:
                # Do not log cloud SDK exceptions: they can include signed requests.
                self.store.dispatched(run_id, token, success=False)
            else:
                self.store.dispatched(run_id, token, success=True)
                sent += 1
        return sent

    async def work(self, run_id: str) -> bool:
        """Execute one claimed run and confirm cleanup before terminal publication.

        No takeover is attempted after an uncertain lease. An invocation can
        disappear at any instruction; the next dispatcher fences expired leases.
        """
        row = self.store.get(run_id)
        app = self.applications.get(row["revision"])
        if app is None:
            return False
        lease_seconds = max(30, int(self.cleanup_seconds * 2 + self.heartbeat_seconds + 10))
        attempt = self.store.claim(run_id, app, lease_seconds=lease_seconds)
        if attempt is None:
            return False
        executor: Executor | None = None
        context: ExecutionContext | None = None
        task: asyncio.Task[ExecutionResult] | None = None
        result, status = ExecutionResult(""), "failed"
        failure: str | None = "execution_failed"
        try:
            executor = self.executor_factory(app)
            context = ExecutionContext(
                self.store,
                run_id,
                attempt,
                json.loads(row["request"])["input"]["text"],
                json.loads(row["snapshot"]),
            )
            context.check()
            self.store.started(run_id, attempt)
            task = asyncio.create_task(executor.execute(context))
            while True:
                done, _ = await asyncio.wait({task}, timeout=self.heartbeat_seconds)
                latest = self.store.heartbeat(run_id, attempt, lease_seconds=lease_seconds)
                if latest["cancel"] or time.time() >= latest["deadline"]:
                    status = "cancelled" if latest["cancel"] else "timed_out"
                    failure = None
                    task.cancel()
                    break
                if done:
                    result = task.result()
                    status, failure = "succeeded", None
                    break
        except asyncio.CancelledError:
            # Platform SIGTERM/outer cancellation must not claim a remote stop.
            status, failure = "failed", "worker_interrupted"
            raise
        except ApplicationError as exc:
            failure = (
                exc.code
                if exc.code
                in {
                    "event_budget",
                    "output_budget",
                    "artifact_budget",
                    "execution_stopped",
                }
                else "execution_failed"
            )
        except Exception:
            # Never persist model/cloud exception text or repr (may contain credentials).
            failure = "execution_failed"
        finally:
            if context is not None:
                context.stopping.set()
            if task is not None and not task.done():
                task.cancel()
                # Cooperative callbacks must respond to cancellation; otherwise isolate runtime.
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait({task}, timeout=self.cleanup_seconds)
            confirmed = executor is None
            if executor is not None:
                try:
                    confirmed = await asyncio.wait_for(executor.close(), self.cleanup_seconds)
                except (Exception, asyncio.CancelledError):
                    confirmed = False
            if task is not None and not task.done():
                confirmed = False
            if confirmed:
                try:
                    self.store.finish(run_id, attempt, status, result, failure)
                except ApplicationError as exc:
                    if exc.code in {"output_budget", "artifact_budget"}:
                        self.store.finish(run_id, attempt, "failed", ExecutionResult(""), exc.code)
                    else:
                        self.store.uncertain(run_id, attempt)
            else:
                self.store.uncertain(run_id, attempt)
        return True
