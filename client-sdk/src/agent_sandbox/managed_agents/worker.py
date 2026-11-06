"""Bounded, claim-fenced Session execution, observation and owned cleanup."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import secrets
import time
from typing import Any

from .backend import bridge_request
from .models import SUBMISSION_TERMINAL, ManagedError, canonical
from .service import ManagedService, public
from .store import new_object


class ManagedWorker:
    """Run finite invocations; replacing an observer never authorizes input replay."""

    def __init__(
        self,
        service: ManagedService,
        backend: Any,
        *,
        poll_seconds: float = 0.25,
        lease_seconds: float = 45,
    ) -> None:
        self.service, self.store, self.config = service, service.store, service.config
        self.backend, self.poll_seconds = backend, poll_seconds
        if lease_seconds < 0.1:
            raise ValueError("The observation lease must be at least 0.1 seconds")
        self.lease_seconds = lease_seconds

    def _owned(self, sid: str, claim: str) -> dict[str, Any]:
        with self.store.transaction() as tx:
            row = tx.get(sid, deleted=True)
            if row.get("_claim") != claim or row.get("_claim_until", 0) <= time.time():
                raise ManagedError(409, "claim_changed", "Observation ownership changed")
            if row["x_agent_sandbox"]["lifecycle"] == "requires_reconcile" and not row.get(
                "_close_requested"
            ):
                raise ManagedError(409, "claim_changed", "The Session is frozen for reconciliation")
            return row

    async def _heartbeat(self, sid: str, claim: str) -> None:
        while True:
            await asyncio.sleep(self.lease_seconds / 3)
            with self.store.transaction() as tx:
                row = tx.get(sid, deleted=True)
                if row.get("_claim") != claim or row.get("_claim_until", 0) <= time.time():
                    return
                row["_claim_until"] = time.time() + self.lease_seconds
                tx.put(row)

    def _uncertain(self, sid: str, subid: str | None, claim: str, code: str) -> None:
        with self.store.transaction() as tx:
            row = tx.get(sid, deleted=True)
            if row.get("_claim") != claim:
                return
            row["x_agent_sandbox"]["lifecycle"] = "requires_reconcile"
            row["status"], row["error"] = (
                "failed",
                {"code": code, "message": "Execution ownership requires reconciliation"},
            )
            if subid:
                sub = tx.get(subid, deleted=True)
                sub.update(status="uncertain", error={"code": code})
                tx.put(sub)
                if sub.get("turn_id"):
                    turn = tx.get(sub["turn_id"], deleted=True)
                    if turn["status"] == "in_progress":
                        turn.update(
                            status="failed",
                            completed_at=time.time(),
                            error={
                                "code": "execution_result_uncertain",
                                "message": "Gateway could not confirm execution outcome",
                            },
                            x_agent_sandbox={"execution_status": "uncertain"},
                        )
                        tx.put(turn)
                        tx.event(
                            row,
                            "agent.session.turn.failed",
                            {"turn_id": turn["id"], "turn": public(turn)},
                        )
            tx.event(row, "agent.session.failed", {"error": row["error"]})

    async def run(self, sid: str, submission_id: str | None = None) -> bool:
        """Claim one Session, execute/observe one input, or advance its close operation."""
        claim = secrets.token_hex(16)
        sub: dict[str, Any] | None = None
        with self.store.transaction() as tx:
            session = tx.get(sid, deleted=True)
            if session["_revision"] != self.config.revision:
                raise ManagedError(
                    409,
                    "worker_revision_mismatch",
                    "This Session belongs to another Worker revision",
                )
            if session["x_agent_sandbox"]["lifecycle"] in {
                "requires_reconcile",
                "closed",
                "expired",
            } and not session.get("_close_requested"):
                return False
            if session.get("_claim_until", 0) > time.time():
                return False
            concurrent = [
                r
                for r in tx.list("session", deleted=True, work=True)
                if r.get("_claim_until", 0) > time.time()
            ]
            if len(concurrent) >= self.config.limits["maxConcurrentRuns"]:
                return False
            if (
                session.get("_claim")
                and session.get("_phase") in {"creating", "submitting"}
                and not session.get("_close_requested")
            ):
                session["x_agent_sandbox"]["lifecycle"] = "requires_reconcile"
                tx.put(session)
                return False
            session["_claim"], session["_claim_until"] = claim, time.time() + self.lease_seconds
            if session.get("_close_requested"):
                session["_phase"] = "closing"
            else:
                pending = [
                    r
                    for r in tx.list("submission", parent=sid, pending=True)
                    if r["status"] not in SUBMISSION_TERMINAL
                ]
                if submission_id:
                    pending = [r for r in pending if r["id"] == submission_id]
                if not pending:
                    return False
                sub = pending[0]
                if sub["status"] == "queued":
                    sub["status"] = "dispatching"
                session["_active_submission"] = sub["id"]
                tx.put(sub)
            tx.put(session)
        heartbeat = asyncio.create_task(self._heartbeat(sid, claim))
        try:
            if session.get("_close_requested"):
                await self._close(sid, claim)
                return True
            assert sub is not None
            await self._work(sid, sub["id"], claim)
            return True
        except asyncio.CancelledError:
            with self.store.transaction() as tx:
                interrupted = tx.get(sid, deleted=True)
            if interrupted.get("_phase") in {"creating", "submitting"}:
                self._uncertain(sid, sub["id"] if sub else None, claim, "observer_cancelled")
            raise
        except Exception as exc:
            if isinstance(exc, ManagedError) and exc.code == "claim_changed":
                return False
            self._uncertain(sid, sub["id"] if sub else None, claim, "execution_result_uncertain")
            expired = False
            if sub:
                with self.store.transaction() as tx:
                    current_sub, current = (
                        tx.get(sub["id"], deleted=True),
                        tx.get(sid, deleted=True),
                    )
                    expired = current_sub.get("_deadline", float("inf")) <= time.time()
                    if expired:
                        self.service._close(tx, current)
            if expired:
                try:
                    await asyncio.wait_for(self._close(sid, claim), 10)
                except Exception:
                    self._uncertain(sid, sub["id"] if sub else None, claim, "stop_unconfirmed")
            return False
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            with self.store.transaction() as tx:
                row = tx.get(sid, deleted=True)
                if row.get("_claim") == claim:
                    row["_claim_until"] = 0
                    row["_claim"] = None
                    tx.put(row)

    @staticmethod
    def _rpc_timeout(sub: dict[str, Any], cap: float = 30) -> float:
        remaining: float = sub["_deadline"] - time.time()
        if remaining <= 0:
            raise ManagedError(504, "turn_deadline", "The host execution deadline expired")
        return min(cap, remaining)

    async def _prepare(self, sid: str, claim: str) -> dict[str, Any]:
        session = self._owned(sid, claim)
        if session.get("_resource"):
            return session
        with self.store.transaction() as tx:
            session = tx.get(sid, deleted=True)
            allocated = [r for r in tx.list("session", deleted=True, occupied=True)]
            if session.get("_claim") != claim or session.get("_claim_until", 0) <= time.time():
                raise ManagedError(409, "claim_changed", "Observation ownership changed")
            if len(allocated) >= self.config.sessions["maxActiveSessions"]:
                raise ManagedError(
                    429, "sandbox_capacity", "Allocated or uncertain resources occupy capacity"
                )
            token = secrets.token_urlsafe(32)
            session.update(
                _creation_started=True,
                _phase="creating",
                _app_token=token,
                _deadline=time.time() + session["_settings"]["sessions"]["maxLifetimeSeconds"],
            )
            session["x_agent_sandbox"]["lifecycle"] = "provisioning"
            tx.event(session, "agent.session.environment.pending", {})

        def created(resource: dict[str, Any]) -> None:
            with self.store.transaction() as tx:
                current = tx.get(sid, deleted=True)
                # Preserve a late create result even if close/claim changes.
                current["_resource"] = resource
                current["_cleanup_confirmed"] = False
                tx.put(current)
                if current.get("_claim") != claim or current.get("_claim_until", 0) <= time.time():
                    raise ManagedError(409, "claim_changed", "Observation ownership changed")

        self._owned(sid, claim)
        resource = await self.backend.create(session, token, created)
        self._owned(sid, claim)
        deadline = time.monotonic() + 60
        while True:
            try:
                self._owned(sid, claim)
                caps = await bridge_request(resource, "GET", "/capabilities")
                self._owned(sid, claim)
                if session["agent"]["x_agent_sandbox"]["adapter"] not in caps.get("adapters", []):
                    raise ManagedError(
                        503, "guest_adapter_unavailable", "The selected adapter is unavailable"
                    )
                break
            except Exception as exc:
                if isinstance(exc, ManagedError) and exc.code == "claim_changed":
                    raise
                if time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.5)
        self._owned(sid, claim)
        local = await bridge_request(
            resource,
            "POST",
            "/managed/session",
            {
                "nonce": sid,
                "agent": {
                    "adapter": session["agent"]["x_agent_sandbox"]["adapter"],
                    "model": session["agent"]["model"],
                    "instructions": session["agent"].get("instructions"),
                },
            },
        )
        self._owned(sid, claim)
        if local.get("epoch") != caps["epoch"]:
            raise ManagedError(409, "runtime_epoch_changed", "The runtime restarted during setup")
        with self.store.transaction() as tx:
            current = tx.get(sid, deleted=True)
            current.update(
                _resource=resource,
                _guest_session=local["session_id"],
                _guest_epoch=local["epoch"],
                _phase="ready",
            )
            if not current.get("_close_requested"):
                current["x_agent_sandbox"]["lifecycle"] = "ready"
            tx.event(current, "agent.session.environment.connected", {})
            return current

    async def _work(self, sid: str, subid: str, claim: str) -> None:
        session = await self._prepare(sid, claim)
        with self.store.transaction() as tx:
            sub = tx.get(subid)
            current = tx.get(sid, deleted=True)
            if current.get("_claim") != claim or current.get("_claim_until", 0) <= time.time():
                raise ManagedError(409, "claim_changed", "Observation ownership changed")
            if not sub.get("_sent") and (sub.get("_cancel") or current.get("_close_requested")):
                sub["status"] = "cancelled"
                tx.put(sub)
                if sub.get("_cancel_operation"):
                    op = tx.get(sub["_cancel_operation"])
                    op.update(status="succeeded", result={"stop_confirmed": True})
                    tx.put(op)
                if current.get("_close_requested"):
                    # Leave normal owned-resource cleanup to the same claim.
                    current["_phase"] = "closing"
                else:
                    current["status"], current["_phase"] = "idle", "ready"
                tx.put(current)
                cancelled_before_send = True
            else:
                cancelled_before_send = False
                files = []
                for ref in sub["_files"]:
                    source = tx.get(ref["file_id"], sub["_owner"], deleted=True, with_data=True)
                    files.append(
                        {
                            "path": ref["path"],
                            "sha256": ref["sha256"],
                            "data_base64": source["_data"],
                        }
                    )
                if not sub.get("_deadline"):
                    sub["_deadline"] = min(
                        time.time() + session["_settings"]["limits"]["maxRunSeconds"],
                        session["_deadline"] - 5,
                    )
                already_sent = bool(sub.get("_sent"))
                if not already_sent:
                    sub.update(_sent=True, status="submitted")
                    current["_phase"] = "submitting"
                    tx.put(sub)
                    tx.put(current)
        if cancelled_before_send:
            if current.get("_close_requested"):
                await self._close(sid, claim)
            return
        if not already_sent:
            try:
                self._owned(sid, claim)
                receipt = await bridge_request(
                    session["_resource"],
                    "POST",
                    "/managed/submissions",
                    {
                        "submission_id": subid,
                        "session_id": session["_guest_session"],
                        "input": sub["_prompt"],
                        "files": files,
                        "deadline": sub["_deadline"],
                        "max_tool_seconds": session["_settings"]["limits"]["maxToolSeconds"],
                        "max_output_bytes": session["_settings"]["limits"]["maxOutputBytes"],
                        "max_events": session["_settings"]["limits"]["maxEventsPerRun"],
                    },
                    timeout_seconds=self._rpc_timeout(sub),
                )
            except Exception:
                # Inspect the original receipt. A 404/timeout is uncertain, never
                # permission to submit the same input into a fresh runtime.
                receipt = await bridge_request(
                    session["_resource"],
                    "GET",
                    "/managed/submissions/" + subid,
                    timeout_seconds=self._rpc_timeout(sub),
                )
        else:
            receipt = await bridge_request(
                session["_resource"],
                "GET",
                "/managed/submissions/" + subid,
                timeout_seconds=self._rpc_timeout(sub),
            )
        while True:
            current = self._owned(sid, claim)
            if (
                receipt.get("epoch") != current["_guest_epoch"]
                or receipt.get("current_epoch") != current["_guest_epoch"]
                or receipt.get("status") == "uncertain"
            ):
                raise ManagedError(
                    409, "runtime_epoch_changed", "Receipt identity is no longer authoritative"
                )
            with self.store.transaction() as tx:
                current, sub = tx.get(sid, deleted=True), tx.get(subid, deleted=True)
                current["_claim_until"] = time.time() + self.lease_seconds
                current["_phase"] = "observing"
                cancel = (
                    sub.get("_cancel")
                    or current.get("_close_requested")
                    or time.time() > sub["_deadline"]
                )
                if cancel:
                    sub["_cancel"] = True
                cancel = cancel or sub.get("_output_exceeded", False)
                tx.put(current)
                tx.put(sub)
            if cancel and receipt.get("status") not in SUBMISSION_TERMINAL:
                receipt = await bridge_request(
                    current["_resource"],
                    "POST",
                    "/managed/submissions/" + subid + "/cancel",
                    {"epoch": current["_guest_epoch"], "session_id": current["_guest_session"]},
                    timeout_seconds=min(5, max(0.001, sub["_deadline"] - time.time())),
                )
            self._ingest(sid, subid, claim, receipt)
            if receipt.get("status") in {"completed", "failed", "cancelled"} and receipt.get(
                "returned_cursor", 0
            ) >= receipt.get("latest_cursor", 0):
                if receipt.get("stop_confirmed") is not True:
                    with self.store.transaction() as tx:
                        row = tx.get(sid, deleted=True)
                        previous_cancel = tx.get(subid, deleted=True).get("_cancel", False)
                        self.service._close(tx, row)
                    await self._close(sid, claim)
                    if not self._owned(sid, claim).get("_cleanup_confirmed"):
                        raise ManagedError(409, "stop_unconfirmed", "Sandbox stop is unconfirmed")
                    with self.store.transaction() as tx:
                        stopped_sub = tx.get(subid, deleted=True)
                        stopped_sub["_cancel"] = previous_cancel
                        tx.put(stopped_sub)
                self._finish(sid, subid, claim, receipt)
                if self._owned(sid, claim).get("_close_requested"):
                    await self._close(sid, claim)
                return
            if time.time() > sub["_deadline"] + 20:
                raise ManagedError(409, "stop_unconfirmed", "The turn did not confirm stopping")
            await asyncio.sleep(self.poll_seconds)
            with self.store.transaction() as tx:
                sub = tx.get(subid, deleted=True)
            receipt = await bridge_request(
                current["_resource"],
                "GET",
                "/managed/submissions/" + subid + "?after=" + str(sub.get("_native_seq", 0)),
                timeout_seconds=self._rpc_timeout(sub),
            )

    def _ingest(self, sid: str, subid: str, claim: str, receipt: dict[str, Any]) -> None:
        with self.store.transaction() as tx:
            session, sub = tx.get(sid, deleted=True), tx.get(subid, deleted=True)
            if session.get("_claim") != claim:
                raise ManagedError(409, "claim_changed", "Observation ownership changed")
            if session.get("_deleted"):
                return
            wires = receipt.get("events", [])
            started = receipt.get("turn") or any(
                e.get("wire", {}).get("type") == "agent.session.turn.in_progress" for e in wires
            )
            if not sub.get("turn_id") and started:
                turn = new_object(
                    "turn",
                    sub["_owner"],
                    parent=sid,
                    session_id=sid,
                    status="in_progress",
                    completed_at=None,
                    usage=None,
                    error=None,
                    _submission=subid,
                )
                sub["turn_id"] = turn["id"]
                sub["status"] = "running"
                tx.put(turn)
                tx.event(
                    session,
                    "agent.session.turn.created",
                    {"turn_id": turn["id"], "turn": public(turn), "submission_id": subid},
                )
            seen: set[str] = set()
            frontier = sub.get("_native_seq", 0)
            for event in wires:
                if event.get("seq", 0) <= frontier:
                    continue
                wire = event.get("wire", {})
                native_id = wire.get("event_id")
                if native_id in seen:
                    continue
                seen.add(native_id)
                kind = wire.get("type", "")
                if (
                    kind.endswith((".completed", ".failed", ".cancelled", ".idle"))
                    or kind in {"agent.session.created", "agent.session.turn.created"}
                    or "reasoning" in kind
                ):
                    continue
                sub["_native_count"] = sub.get("_native_count", 0) + 1
                if sub["_native_count"] > session["_settings"]["limits"]["maxEventsPerRun"]:
                    sub["_output_exceeded"] = True
                    continue
                value = dict(wire)
                value.pop("event_id", None)
                value.pop("session", None)
                value.pop("turn", None)
                value["session_id"], value["turn_id"] = sid, sub.get("turn_id")
                if isinstance(value.get("item"), dict):
                    value["item"] = self._item(sid, sub.get("turn_id"), value["item"])
                if "item_id" in value:
                    value["item_id"] = self._item_id(sid, str(value["item_id"]))
                value.pop("type", None)
                size = len(canonical(value).encode())
                sub["_stream_bytes"] = sub.get("_stream_bytes", 0) + size
                if sub["_stream_bytes"] > session["_settings"]["limits"]["maxOutputBytes"]:
                    sub["_output_exceeded"] = True
                    continue
                tx.event(session, kind, value)
            if receipt.get("gap") and not sub.get("_gap"):
                tx.event(session, "agent.session.events.gap", {"submission_id": subid})
                sub["_gap"] = True
            sub["_native_seq"] = receipt.get("returned_cursor", sub.get("_native_seq", 0))
            tx.put(sub)

    @staticmethod
    def _item_id(sid: str, native_id: str) -> str:
        return "item_" + hashlib.sha256((sid + ":" + native_id).encode()).hexdigest()[:32]

    def _item(self, sid: str, tid: str | None, value: dict[str, Any]) -> dict[str, Any]:
        return {**value, "id": self._item_id(sid, str(value["id"])), "turn_id": tid}

    def _finish(self, sid: str, subid: str, claim: str, receipt: dict[str, Any]) -> None:
        with self.store.transaction() as tx:
            session, sub = tx.get(sid, deleted=True), tx.get(subid, deleted=True)
            if session.get("_claim") != claim:
                raise ManagedError(409, "claim_changed", "Observation ownership changed")
            if not sub.get("turn_id"):
                raise ManagedError(
                    409, "missing_turn_receipt", "The native turn identity was not observed"
                )
            turn = tx.get(sub["turn_id"], deleted=True)
            if session.get("_deleted"):
                return
            session["_phase"] = "collecting"
            native = receipt["turn"]
            errors = list(receipt.get("artifact_errors", []))
            total = 0
            items = [i for i in receipt.get("items", []) if i.get("type") != "reasoning"]
            if len(canonical(items).encode()) > session["_settings"]["limits"]["maxOutputBytes"]:
                sub["_output_exceeded"] = True
            for item in [] if sub.get("_output_exceeded") else items:
                if item.get("type") == "reasoning":
                    continue
                projected = self._item(sid, turn["id"], item)
                projected.update(
                    _owner=sub["_owner"], _kind="item", _parent=sid, created_at=time.time()
                )
                tx.put(projected)
            for artifact in receipt.get("artifacts", []):
                raw = base64.b64decode(artifact["data_base64"], validate=True)
                total += len(raw)
                limits = session["_settings"]["storage"]
                if (
                    len(raw) > limits["maxArtifactBytes"]
                    or total > limits["maxTurnArtifactBytes"]
                    or hashlib.sha256(raw).hexdigest() != artifact["sha256"]
                ):
                    raise ManagedError(
                        413, "artifact_limit", "The output artifact exceeds its declared budget"
                    )
                self.service.check_storage(tx, sub["_owner"], len(raw))
                row = new_object(
                    "artifact",
                    sub["_owner"],
                    parent=sid,
                    session_id=sid,
                    turn_id=turn["id"],
                    path=artifact["path"],
                    bytes=len(raw),
                    expires_at=time.time()
                    + session["_settings"]["sessions"]["resultRetentionSeconds"],
                    x_agent_sandbox={"sha256": artifact["sha256"]},
                    _data=artifact["data_base64"],
                )
                tx.put(row)
                tx.event(
                    session,
                    "agent.session.artifact.created",
                    {"artifact": public(row), "turn_id": turn["id"]},
                )
            status = (
                "failed"
                if sub.get("_output_exceeded")
                else "cancelled"
                if sub.get("_cancel")
                else receipt["status"]
            )
            turn.update(
                status=status,
                completed_at=time.time(),
                usage=native.get("usage"),
                error=(
                    {"code": "output_budget_exceeded"}
                    if sub.get("_output_exceeded")
                    else receipt.get("error") or native.get("error")
                ),
                x_agent_sandbox={
                    "publication": "partial" if errors else "complete",
                    "artifact_errors": errors,
                },
            )
            sub.update(status=status, completed_at=time.time())
            tx.put(turn)
            tx.put(sub)
            if sub.get("_cancel_operation"):
                op = tx.get(sub["_cancel_operation"], deleted=True)
                op.update(status="succeeded", result={"stop_confirmed": True})
                tx.put(op)
            session["last_active_at"] = time.time()
            session["_phase"] = "closed" if session.get("_cleanup_confirmed") else "ready"
            pending = [
                r
                for r in tx.list("submission", parent=sid, pending=True)
                if r["status"] not in SUBMISSION_TERMINAL
            ]
            session["status"] = "in_progress" if pending else "idle"
            tx.event(
                session,
                "agent.session.turn." + status,
                {"turn_id": turn["id"], "turn": public(turn)},
            )
            if not pending:
                tx.event(session, "agent.session.idle", {"session": public(session)})

    async def _close(self, sid: str, claim: str) -> None:
        session = self._owned(sid, claim)
        confirmed = False
        if session.get("_resource"):
            confirmed = await self.backend.kill(session["_resource"])
        elif not session.get("_creation_started"):
            confirmed = True
        with self.store.transaction() as tx:
            current = tx.get(sid, deleted=True)
            if current.get("_claim") != claim:
                return
            current["x_agent_sandbox"]["lifecycle"] = (
                "closed" if confirmed else "requires_reconcile"
            )
            current["status"] = "idle" if confirmed else "failed"
            if confirmed:
                current.update(
                    _resource=None,
                    _creation_started=False,
                    _cleanup_confirmed=True,
                    _retain_until=time.time()
                    + current["_settings"]["sessions"]["resultRetentionSeconds"],
                )
                for sub in tx.list("submission", parent=sid, deleted=True, pending=True):
                    if sub["status"] not in SUBMISSION_TERMINAL:
                        sub["status"] = "cancelled"
                        tx.put(sub)
                for cancellation in tx.list("operation", parent=sid, deleted=True):
                    if (
                        cancellation.get("kind") == "cancel"
                        and cancellation.get("status") != "succeeded"
                    ):
                        cancellation.update(status="succeeded", result={"stop_confirmed": True})
                        tx.put(cancellation)
            op = tx.get(current["_close_operation"], deleted=True)
            op.update(
                status="succeeded" if confirmed else "requires_reconcile",
                result={
                    "stop_confirmed": confirmed,
                    "compute_released": confirmed,
                    "public_removed": bool(current.get("_deleted")),
                },
            )
            tx.put(op)
            if not current.get("_deleted"):
                tx.event(
                    current,
                    "agent.session.closed" if confirmed else "agent.session.cleanup.uncertain",
                    {},
                )
            else:
                tx.put(current)

    def due(self, limit: int = 20, revisions: set[str] | None = None) -> list[dict[str, str]]:
        """Claim bounded outbox deliveries and apply Session lifetime fences."""
        if not 1 <= limit <= 100:
            raise ManagedError(400, "invalid_limit", "Dispatch limit must be 1-100")
        out = []
        with self.store.transaction() as tx:
            self.service.collect(tx)
            for session in tx.list("session", deleted=True, work=True):
                if revisions is not None and session["_revision"] not in revisions:
                    continue
                pending = [
                    r
                    for r in tx.list("submission", parent=session["id"], pending=True)
                    if r["status"] not in SUBMISSION_TERMINAL
                ]
                lifetime = session.get("_deadline", float("inf")) <= time.time()
                idle = (
                    not pending
                    and session.get("_resource")
                    and time.time() - session["last_active_at"]
                    >= session["_settings"]["sessions"]["idleTimeoutSeconds"]
                )
                if (lifetime or idle) and not session.get("_close_requested"):
                    self.service._close(tx, session)
                if session.get("_close_requested") and not session.get("_cleanup_confirmed"):
                    identifier = session["_close_operation"]
                elif pending:
                    identifier = pending[0]["id"]
                else:
                    continue
                if (
                    session.get("_claim_until", 0) > time.time()
                    or session.get("_dispatch_after", 0) > time.time()
                ):
                    continue
                session["_dispatch_after"] = time.time() + 15
                session["_dispatch_attempt"] = session.get("_dispatch_attempt", 0) + 1
                tx.put(session)
                out.append(
                    {
                        "sessionId": session["id"],
                        "submissionId": identifier,
                        "revision": session["_revision"],
                        "deliveryId": identifier + "-" + str(session["_dispatch_attempt"]),
                    }
                )
                if len(out) >= limit:
                    break
        return out
