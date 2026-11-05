"""Private signed invocation and finite outbox delivery, including safe drain."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from typing import TYPE_CHECKING, Any, cast

from .models import ManagedError, canonical

if TYPE_CHECKING:
    from .worker import ManagedWorker


def sign_invocation(payload: dict[str, Any], token: str, role: str) -> dict[str, Any]:
    """Sign a role-scoped body; no secret appears in the envelope."""
    if role not in {"worker", "dispatcher"} or len(token) < 32:
        raise ValueError("A private role and at least 32-character token are required")
    value = {"version": 1, "role": role, "payload": payload}
    return {
        **value,
        "signature": hmac.new(
            token.encode(), canonical(value).encode(), hashlib.sha256
        ).hexdigest(),
    }


def verify_invocation(value: dict[str, Any], token: str, role: str) -> dict[str, Any]:
    """Authenticate direct/timer invocation before accessing control-plane state."""
    if role == "dispatcher" and set(value) == {"triggerTime", "triggerName", "payload"}:
        try:
            value = json.loads(value["payload"])
        except (ValueError, TypeError) as exc:
            raise ManagedError(401, "unauthenticated", "Private invocation required") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "role", "payload", "signature"}
        or value.get("version") != 1
        or value.get("role") != role
        or not isinstance(value.get("payload"), dict)
        or not isinstance(value.get("signature"), str)
    ):
        raise ManagedError(401, "unauthenticated", "Private invocation required")
    expected = sign_invocation(value["payload"], token, role)["signature"]
    if not hmac.compare_digest(value["signature"], expected):
        raise ManagedError(401, "unauthenticated", "Private invocation required")
    return cast("dict[str, Any]", value["payload"])


class FCTaskSender:
    """Use the official Python FC SDK and role credentials, with SDK retries disabled."""

    def __init__(
        self, endpoint: str, workers: dict[str, str], token: str, *, client: Any = None
    ) -> None:
        if not endpoint or "://" in endpoint or len(token) < 32:
            raise ValueError("Explicit FC endpoint and private invocation token are required")
        if client is None:
            from alibabacloud_credentials.client import Client as Credentials
            from alibabacloud_fc20230330.client import Client
            from alibabacloud_tea_openapi.models import Config

            client = Client(Config(credential=Credentials(), endpoint=endpoint))
        self.client, self.workers, self.token = client, dict(workers), token

    def __call__(self, payload: dict[str, str]) -> None:
        """Deliver to the Session's pinned revision, never silently the newest Worker."""
        from alibabacloud_fc20230330.models import InvokeFunctionHeaders, InvokeFunctionRequest
        from alibabacloud_tea_util.models import RuntimeOptions

        function = self.workers.get(payload["revision"])
        if not function:
            raise ManagedError(
                503, "worker_revision_unavailable", "The pinned Worker revision is unavailable"
            )
        body = {k: payload[k] for k in ("sessionId", "submissionId")}
        response = self.client.invoke_function_with_options(
            function,
            InvokeFunctionRequest(
                body=io.BytesIO(canonical(sign_invocation(body, self.token, "worker")).encode())
            ),
            InvokeFunctionHeaders(
                x_fc_invocation_type="Async", x_fc_async_task_id=payload["deliveryId"]
            ),
            RuntimeOptions(autoretry=False, connect_timeout=10000, read_timeout=15000),
        )
        if response.status_code != 202:
            raise ManagedError(503, "task_not_accepted", "FC did not durably accept the task")


class ManagedDispatcher:
    """Finite dispatch/status/drain operations sharing the normal Session state machine."""

    def __init__(self, worker: ManagedWorker, sender: Any = None) -> None:
        self.worker, self.service, self.store, self.sender = (
            worker,
            worker.service,
            worker.store,
            sender,
        )

    async def dispatch(self, limit: int = 20) -> dict[str, int]:
        """Dispatch bounded due work, retaining failures for later outbox attempts."""
        sent, failed = 0, 0
        revisions = (
            set(self.service.config.workers)
            if self.sender is not None
            else {self.service.config.revision}
        )
        for payload in self.worker.due(limit, revisions):
            try:
                if self.sender is None:
                    await self.worker.run(payload["sessionId"])
                else:
                    self.sender(payload)
                sent += 1
            except Exception:
                failed += 1
        return {"dispatched": sent, "pendingRetry": failed}

    def status(self, revision: str | None = None) -> dict[str, Any]:
        """Count all usable logical Sessions and uncertain resources before retirement."""
        with self.store.transaction() as tx:
            sessions = [
                r
                for r in tx.list("session", deleted=True, work=True)
                if revision is None or r["_revision"] == revision
            ]
            active = [
                r
                for r in sessions
                if (
                    not r.get("_deleted")
                    and r["x_agent_sandbox"]["lifecycle"] not in {"closed", "expired"}
                )
                or r.get("_resource")
                or r.get("_creation_started")
            ]
            pending = [
                r for r in sessions if r.get("_close_requested") and not r.get("_cleanup_confirmed")
            ]
            uncertain = [
                r for r in sessions if r["x_agent_sandbox"]["lifecycle"] == "requires_reconcile"
            ]
            control = self.service.control(tx)
            return {
                "stateInstanceId": self.store.state_instance_id,
                "activeSessions": len(active),
                "pendingCleanup": len(pending),
                "uncertainResources": len(uncertain),
                "draining": not control["accepting"] or revision in control["draining_revisions"],
            }

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle signed dispatch/status/drain without introducing a business admin API."""
        if set(payload) - {"operation", "applicationId", "revision", "limit"}:
            raise ManagedError(400, "invalid_invocation", "Unknown dispatcher input")
        operation, revision = payload.get("operation", "dispatch"), payload.get("revision")
        limit = payload.get("limit", 20)
        if (
            (not isinstance(limit, int) or isinstance(limit, bool))
            or not 1 <= limit <= 100
            or (revision is not None and not isinstance(revision, str))
        ):
            raise ManagedError(400, "invalid_invocation", "Invalid dispatch bounds")
        if operation not in {"dispatch", "status", "drain"}:
            raise ManagedError(400, "invalid_operation", "Unknown private control operation")
        if (
            operation != "dispatch"
            and payload.get("applicationId") != self.service.config.application_id
        ):
            raise ManagedError(403, "application_mismatch", "Private control target does not match")
        if operation == "status":
            return self.status(revision)
        if operation == "drain":
            with self.store.transaction() as tx:
                control = self.service.control(tx)
                if revision:
                    control["draining_revisions"] = sorted(
                        set(control["draining_revisions"]) | {revision}
                    )
                else:
                    control["accepting"] = False
                tx.execute(
                    "UPDATE managed_control SET body=? WHERE application=?",
                    (canonical(control), tx.application),
                )
                for session in tx.list("session", deleted=True, work=True):
                    if (revision is None or session["_revision"] == revision) and not session.get(
                        "_cleanup_confirmed"
                    ):
                        self.service._close(tx, session)
            await self.dispatch(limit)
            return self.status(revision)
        return await self.dispatch(limit)
