"""Owner-scoped managed Agents resources, acceptance and public projections."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import posixpath
import time
from typing import Any, cast

from .models import (
    PROTOCOL,
    SUBMISSION_TERMINAL,
    ManagedConfig,
    ManagedError,
    canonical,
    digest,
    metadata,
    reject_unknown,
    text_input,
)
from .store import ManagedStore, Transaction, new_object

MAX_TOTAL_INPUT_FILE_BYTES = 10485760

OPERATIONS = (
    ("GET", "/healthz"),
    ("GET", "/v1/agent-sandbox/capabilities"),
    ("GET", "/v1/models"),
    ("GET", "/v1/models/{model_id}"),
    ("GET", "/v1/agents/runtimes"),
    ("POST", "/v1/agents"),
    ("GET", "/v1/agents"),
    ("GET", "/v1/agents/{agent_id}"),
    ("POST", "/v1/agents/{agent_id}"),
    ("DELETE", "/v1/agents/{agent_id}"),
    ("POST", "/v1/agents/sessions"),
    ("GET", "/v1/agents/sessions"),
    ("GET", "/v1/agents/sessions/{session_id}"),
    ("POST", "/v1/agents/sessions/{session_id}"),
    ("DELETE", "/v1/agents/sessions/{session_id}"),
    ("POST", "/v1/agents/sessions/{session_id}/events"),
    ("GET", "/v1/agents/sessions/{session_id}/events"),
    ("GET", "/v1/agents/sessions/{session_id}/items"),
    ("GET", "/v1/agents/sessions/{session_id}/turns"),
    ("GET", "/v1/agents/sessions/{session_id}/turns/{turn_id}"),
    ("GET", "/v1/agents/sessions/{session_id}/turns/{turn_id}/items"),
    ("GET", "/v1/agents/sessions/{session_id}/artifacts"),
    ("GET", "/v1/agents/sessions/{session_id}/artifacts/{artifact_id}"),
    ("GET", "/v1/agents/sessions/{session_id}/artifacts/{artifact_id}/content"),
    ("DELETE", "/v1/agents/sessions/{session_id}/artifacts/{artifact_id}"),
    ("POST", "/v1/files"),
    ("GET", "/v1/files"),
    ("GET", "/v1/files/{file_id}"),
    ("GET", "/v1/files/{file_id}/content"),
    ("DELETE", "/v1/files/{file_id}"),
    ("GET", "/v1/agents/environments"),
    ("GET", "/v1/agents/environments/{environment_id}"),
    ("POST", "/v1/agent-sandbox/sessions/{session_id}/close"),
    ("GET", "/v1/agent-sandbox/operations/{operation_id}"),
    ("POST", "/v1/agent-sandbox/sessions/{session_id}/submissions"),
    ("GET", "/v1/agent-sandbox/sessions/{session_id}/submissions"),
    ("GET", "/v1/agent-sandbox/sessions/{session_id}/submissions/{submission_id}"),
    ("POST", "/v1/agent-sandbox/sessions/{session_id}/submissions/{submission_id}/cancel"),
    ("POST", "/v1/agent-sandbox/sessions/{session_id}/turns/{turn_id}/cancel"),
)


def public(row: dict[str, Any]) -> dict[str, Any]:
    """Remove all private control/state fields before serializing a public object."""
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    if row.get("_kind") == "session" and isinstance(row.get("environment"), dict):
        out["environment"] = {
            **row["environment"],
            "x_agent_sandbox": {
                "lifecycle": row["x_agent_sandbox"]["lifecycle"],
                "expires_at": row.get("_deadline"),
            },
        }
    return out


class ManagedService:
    """Transactional control plane; no method starts work after HTTP response return."""

    def __init__(self, store: ManagedStore, config: ManagedConfig) -> None:
        self.store, self.config = store, config
        if (
            config.expected_state_id is not None
            and config.expected_state_id != store.state_instance_id
        ):
            raise ValueError("Managed state identity does not match the pinned deployment")

    def capabilities(self) -> dict[str, Any]:
        """Publish supported operations and honest adapter/stream/lifecycle limits."""
        return {
            "protocol": PROTOCOL,
            "revision": self.config.revision,
            "operations": [{"method": m, "path": p} for m, p in OPERATIONS],
            "adapters": sorted(set(self.config.models.values())),
            "features": {
                "steering": False,
                "explicit_queue": True,
                "functions": False,
                "mcp": False,
                "subagents": False,
                "session_settings": False,
                "streaming": "durable_public_events_with_explicit_native_gaps",
                "guest_restart": "freeze_and_reconcile",
                "input_types": ["input_text", "managed_file_reference"],
            },
            "limits": {
                **self.config.limits,
                **self.config.storage,
                **self.config.sessions,
                "max_total_input_file_bytes": MAX_TOTAL_INPUT_FILE_BYTES,
            },
        }

    def control(self, tx: Transaction) -> dict[str, Any]:
        """Read the durable application/revision admission fence."""
        return cast(
            "dict[str, Any]",
            json.loads(
                tx.execute(
                    "SELECT body FROM managed_control WHERE application=?", (tx.application,)
                ).fetchone()["body"]
            ),
        )

    def check_admission(self, tx: Transaction, revision: str) -> None:
        """Reject admission before resource allocation during global or revision drain."""
        control = self.control(tx)
        if not control["accepting"] or revision in control["draining_revisions"]:
            raise ManagedError(503, "application_draining", "This application revision is draining")

    def _idem(self, tx: Transaction, owner: str, scope: str, key: str, body: Any) -> Any:
        if not key:
            return None
        if len(key) > 128 or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ManagedError(
                400,
                "invalid_idempotency_key",
                "Use 1-128 printable ASCII characters",
                "Idempotency-Key",
            )
        row = tx.execute(
            "SELECT digest,result FROM managed_idempotency WHERE application=? AND "
            "scope=? AND key=?",
            (tx.application, owner + ":" + scope, key),
        ).fetchone()
        if row is None:
            return None
        if row["digest"] != digest(body):
            raise ManagedError(
                409,
                "idempotency.mismatch",
                "The key belongs to another request body",
                "Idempotency-Key",
            )
        result = json.loads(row["result"])
        # A deleted resource must never be resurrected by a retained key.
        if isinstance(result, dict) and result.get("id"):
            tx.get(result["id"], owner)
        return result

    def _remember(
        self, tx: Transaction, owner: str, scope: str, key: str, body: Any, result: Any
    ) -> None:
        if key:
            tx.execute(
                "INSERT INTO managed_idempotency(application,scope,key,digest,result) "
                "VALUES(?,?,?,?,?)",
                (tx.application, owner + ":" + scope, key, digest(body), canonical(result)),
            )

    def _page(
        self, rows: list[dict[str, Any]], owner: str, scope: str, query: dict[str, str]
    ) -> dict[str, Any]:
        reject_unknown(query, {"limit", "order", "after", "idempotency_key"})
        try:
            limit = int(query.get("limit", "20"))
        except ValueError as exc:
            raise ManagedError(400, "invalid_limit", "limit must be 1-100", "limit") from exc
        order = query.get("order", "desc")
        if not 1 <= limit <= 100 or order not in {"asc", "desc"}:
            raise ManagedError(400, "invalid_pagination", "Invalid pagination parameters")
        rows = list(rows if order == "asc" else reversed(rows))
        after = query.get("after")
        if after:
            try:
                if "." in after:
                    encoded, signature = after.split(".")
                    expected = hmac.new(
                        self.store.cursor_secret.encode(), encoded.encode(), hashlib.sha256
                    ).hexdigest()
                    if not hmac.compare_digest(signature, expected):
                        raise ValueError
                    cursor = json.loads(
                        base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                    )
                    if cursor[:3] != [owner, scope, order]:
                        raise ValueError
                    last_id = cursor[3]
                else:
                    # SDK paginators pass the public last_id. It must be present
                    # in this already owner/scope-filtered collection.
                    last_id = after
                index = next(i for i, r in enumerate(rows) if r["id"] == last_id)
                rows = rows[index + 1 :]
            except (ValueError, StopIteration, IndexError, TypeError) as exc:
                raise ManagedError(
                    400, "invalid_cursor", "Cursor does not belong to this collection", "after"
                ) from exc
        selected = rows[:limit]

        def cursor_for(row: dict[str, Any]) -> str:
            data = (
                base64.urlsafe_b64encode(canonical([owner, scope, order, row["id"]]).encode())
                .decode()
                .rstrip("=")
            )
            return (
                data
                + "."
                + hmac.new(
                    self.store.cursor_secret.encode(), data.encode(), hashlib.sha256
                ).hexdigest()
            )

        return {
            "object": "list",
            "data": [public(r) for r in selected],
            "first_id": selected[0]["id"] if selected else None,
            "last_id": selected[-1]["id"] if selected else None,
            "has_more": len(rows) > limit,
            "x_agent_sandbox": {
                "next_cursor": cursor_for(selected[-1]) if len(rows) > limit else None
            },
        }

    def _agent(
        self, body: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        reject_unknown(
            body, {"name", "model", "instructions", "metadata", "tools", "x_agent_sandbox"}
        )
        out = dict(existing or {})
        if "model" in body:
            if body["model"] not in self.config.models:
                raise ManagedError(
                    400, "model_not_available", "Select a model from this deployment", "model"
                )
            out["model"] = body["model"]
        if not out.get("model"):
            raise ManagedError(400, "model_required", "model is required", "model")
        for key in ("name", "instructions"):
            if key in body:
                if body[key] is not None and (
                    not isinstance(body[key], str) or len(body[key]) > 32768
                ):
                    raise ManagedError(400, "invalid_field", "Expected a bounded string", key)
                out[key] = body[key] or ""
        if "metadata" in body:
            out["metadata"] = metadata(body["metadata"])
        out.setdefault("metadata", {})
        if body.get("tools") not in (None, []):
            raise ManagedError(
                400, "unsupported_feature", "External tools are not enabled", "tools"
            )
        extension = body.get("x_agent_sandbox", {})
        if not isinstance(extension, dict):
            raise ManagedError(400, "invalid_extension", "Expected an object", "x_agent_sandbox")
        reject_unknown(extension, {"adapter"}, "x_agent_sandbox.")
        adapter = self.config.models[out["model"]]
        if extension.get("adapter", adapter) != adapter:
            raise ManagedError(
                400,
                "adapter_mismatch",
                "The model is bound to another adapter",
                "x_agent_sandbox.adapter",
            )
        out["tools"] = []
        out["x_agent_sandbox"] = {"adapter": adapter, "configuration_revision": digest(out)}
        return out

    def _session(self, tx: Transaction, sid: str, owner: str) -> dict[str, Any]:
        row = tx.get(sid, owner)
        if row["_kind"] != "session":
            raise ManagedError(404, "resource_not_found", "Session was not found")
        if row.get("_retain_until", float("inf")) < time.time():
            raise ManagedError(410, "resource_expired", "Session results have expired")
        return row

    def _attachments(
        self, tx: Transaction, owner: str, body: dict[str, Any]
    ) -> list[dict[str, Any]]:
        extension = body.get("x_agent_sandbox", {})
        if not isinstance(extension, dict):
            raise ManagedError(400, "invalid_extension", "Expected an object", "x_agent_sandbox")
        reject_unknown(extension, {"input_files"}, "x_agent_sandbox.")
        files = extension.get("input_files", [])
        if not isinstance(files, list) or len(files) > 50:
            raise ManagedError(
                400,
                "invalid_files",
                "Expected at most 50 file references",
                "x_agent_sandbox.input_files",
            )
        out, paths = [], set()
        total = 0
        for ref in files:
            if not isinstance(ref, dict) or set(ref) != {"file_id", "path"}:
                raise ManagedError(400, "invalid_file_reference", "Expected file_id and path")
            path = ref["path"]
            root = self.config.workspace.rstrip("/") + "/input/"
            if (
                not isinstance(path, str)
                or not path.startswith(root)
                or posixpath.normpath(path) != path
                or "\x00" in path
                or "\\" in path
                or path in paths
            ):
                raise ManagedError(
                    400,
                    "invalid_path",
                    "Use a unique path under the workspace input directory",
                    "path",
                )
            paths.add(path)
            file = tx.get(str(ref["file_id"]), owner)
            if file["_kind"] != "file" or file.get("expires_at", 0) < time.time():
                raise ManagedError(400, "file_unavailable", "Input file is unavailable", "file_id")
            total += file["bytes"]
            if total > MAX_TOTAL_INPUT_FILE_BYTES:
                raise ManagedError(
                    413,
                    "input_files_too_large",
                    "Total attachment bytes exceed the 10 MiB budget",
                    "x_agent_sandbox.input_files",
                )
            out.append(
                {"file_id": file["id"], "path": path, "sha256": file["x_agent_sandbox"]["sha256"]}
            )
        return out

    def _enqueue(
        self,
        tx: Transaction,
        session: dict[str, Any],
        body: dict[str, Any],
        key: str,
        *,
        queue: bool,
    ) -> dict[str, Any]:
        owner, sid = session["_owner"], session["id"]
        scope = "enqueue:" + sid
        old = self._idem(tx, owner, scope, key, body)
        if old:
            return tx.get(old["id"], owner)
        self.check_admission(tx, session["_revision"])
        if session["x_agent_sandbox"]["lifecycle"] not in {
            "unallocated",
            "provisioning",
            "ready",
        } or session.get("_close_requested"):
            raise ManagedError(409, "session_closed", "This Session cannot accept more work")
        active = [
            r
            for r in tx.list("submission", parent=sid, pending=True)
            if r["status"] not in SUBMISSION_TERMINAL
        ]
        if active and not queue:
            raise ManagedError(
                409,
                "active_turn_not_steerable",
                "Use explicit enqueue while this Session is busy",
                "events",
            )
        limits = session["_settings"]["limits"]
        if len(active) >= session["_settings"]["sessions"]["maxQueuedTurnsPerSession"]:
            raise ManagedError(
                429, "queue_full", "This Session's pending input budget is exhausted"
            )
        all_pending = [
            r for r in tx.list("submission", pending=True) if r["status"] not in SUBMISSION_TERMINAL
        ]
        recent = [r for r in tx.list("submission", owner, recent_after=time.time() - 60)]
        if len(all_pending) >= limits["maxQueuedRuns"] or len(recent) >= limits["maxRunsPerMinute"]:
            raise ManagedError(
                429, "admission_limit", "The application admission budget is exhausted"
            )
        if session.get("_deadline") and session["_deadline"] - time.time() < min(
            30, limits["maxRunSeconds"]
        ):
            raise ManagedError(
                409, "session_deadline", "Not enough Session lifetime remains for another turn"
            )
        prompt = text_input(body.get("input"))
        attachments = self._attachments(tx, owner, body)
        row = new_object(
            "submission",
            owner,
            parent=sid,
            session_id=sid,
            kind="message",
            status="queued",
            accepted_at=time.time(),
            turn_id=None,
            error=None,
            _prompt=prompt,
            _files=attachments,
            _key=key,
            _revision=session["_revision"],
            _cancel=False,
        )
        tx.put(row)
        self._remember(tx, owner, scope, key, body, {"id": row["id"]})
        session["status"] = "in_progress"
        session["last_active_at"] = time.time()
        tx.event(session, "agent.session.submission.accepted", {"submission_id": row["id"]})
        return row

    def create_session(
        self, owner: str, body: dict[str, Any], key: str = ""
    ) -> tuple[dict[str, Any], str | None]:
        """Atomically create a logical Session and its optional initial submission."""
        reject_unknown(
            body,
            {"agent_id", "agent", "environment", "metadata", "input", "stream", "x_agent_sandbox"},
        )
        if "stream" in body and not isinstance(body["stream"], bool):
            raise ManagedError(400, "invalid_stream", "stream must be boolean", "stream")
        with self.store.transaction() as tx:
            old = self._idem(tx, owner, "create-session", key, body)
            if old:
                row = self._session(tx, old["id"], owner)
                return public(row), old.get("submission_id")
            self.check_admission(tx, self.config.revision)
            if len(tx.list("session", owner)) >= self.config.sessions["maxLogicalSessionsPerOwner"]:
                raise ManagedError(429, "session_limit", "The logical Session budget is exhausted")
            saved = tx.get(str(body["agent_id"]), owner) if body.get("agent_id") else None
            if saved and saved["_kind"] != "agent":
                raise ManagedError(404, "resource_not_found", "Agent was not found")
            agent = self._agent(body.get("agent", {}), public(saved) if saved else None)
            environment = body.get("environment", {})
            if not isinstance(environment, dict):
                raise ManagedError(400, "invalid_environment", "Expected an environment object")
            reject_unknown(environment, {"type", "workspace_directory"}, "environment.")
            if (
                environment.get("type", "self_hosted") != "self_hosted"
                or environment.get("workspace_directory", self.config.workspace)
                != self.config.workspace
            ):
                raise ManagedError(
                    400,
                    "unsupported_environment",
                    "Use this deployment's fixed self-hosted workspace",
                    "environment",
                )
            row = new_object(
                "session",
                owner,
                agent=agent,
                status="idle",
                metadata=metadata(body.get("metadata")),
                last_active_at=time.time(),
                usage=None,
                error=None,
                x_agent_sandbox={"lifecycle": "unallocated", "revision": self.config.revision},
                _revision=self.config.revision,
                _seq=0,
                _resource=None,
                _close_requested=False,
                _settings={
                    "template": self.config.template,
                    "workspace": self.config.workspace,
                    "port": self.config.port,
                    "modelEnvAllowlist": self.config.model_env_allowlist,
                    "sessions": self.config.sessions,
                    "limits": self.config.limits,
                    "storage": self.config.storage,
                },
            )
            env = new_object(
                "environment",
                owner,
                parent=row["id"],
                type="self_hosted",
                workspace_directory=self.config.workspace,
                x_agent_sandbox={"lifecycle": "unallocated"},
            )
            row["environment"] = public(env)
            tx.put(env)
            tx.event(row, "agent.session.created", {"session": public(row)})
            submission = None
            if "input" in body:
                submission = self._enqueue(
                    tx,
                    row,
                    {"input": body["input"], "x_agent_sandbox": body.get("x_agent_sandbox", {})},
                    "",
                    queue=True,
                )
            elif body.get("x_agent_sandbox"):
                # Attachments are meaningful only with an immutable accepted input.
                raise ManagedError(
                    400, "input_required", "File references require initial input", "input"
                )
            self._remember(
                tx,
                owner,
                "create-session",
                key,
                body,
                {"id": row["id"], "submission_id": submission["id"] if submission else None},
            )
            return public(row), submission["id"] if submission else None

    def upload_file(
        self, owner: str, filename: str, purpose: str, content: bytes, key: str = ""
    ) -> dict[str, Any]:
        """Seal bounded input bytes; upload never writes an active workspace."""
        if purpose != "user_data" or not filename or len(filename) > 255 or "\x00" in filename:
            raise ManagedError(400, "invalid_file", "Use a bounded filename and purpose=user_data")
        if len(content) > self.config.storage["maxFileBytes"]:
            raise ManagedError(413, "file_too_large", "Input file exceeds the deployment budget")
        body = {
            "filename": filename,
            "purpose": purpose,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        with self.store.transaction() as tx:
            old = self._idem(tx, owner, "upload-file", key, body)
            if old:
                return public(tx.get(old["id"], owner))
            self.check_storage(tx, owner, len(content))
            row = new_object(
                "file",
                owner,
                filename=filename,
                purpose=purpose,
                bytes=len(content),
                expires_at=time.time() + self.config.sessions["resultRetentionSeconds"],
                x_agent_sandbox={"sha256": body["sha256"]},
                _data=base64.b64encode(content).decode(),
            )
            row["object"] = "file"
            tx.put(row)
            self._remember(tx, owner, "upload-file", key, body, {"id": row["id"]})
            return public(row)

    def check_storage(self, tx: Transaction, owner: str, extra: int) -> None:
        """Count retained private bytes too, so tombstones cannot bypass quota."""
        total = sum(
            r.get("bytes", 0)
            for kind in ("file", "artifact")
            for r in tx.list(kind, owner, deleted=True, has_blob=True)
            if r.get("_has_blob")
        )
        if total + extra > self.config.storage["maxRetainedBytesPerOwner"]:
            raise ManagedError(429, "storage_limit", "Retained storage budget is exhausted")

    def collect(self, tx: Transaction, limit: int = 100) -> int:
        """Collect bounded result batches without scanning retained tombstone history."""
        now = time.time()
        pending_files = {
            ref["file_id"]
            for sub in tx.list("submission", pending=True)
            for ref in sub.get("_files", [])
        }
        rows = tx.execute(
            "SELECT body FROM managed_objects "  # nosec B608 - fixed fields; values bound
            "WHERE application=? AND kind IN ('file','artifact')"
            " AND CAST(COALESCE(" + tx.field("_has_blob") + ", 'false') AS TEXT) IN ('true','1')"
            " AND (CAST(" + tx.field("expires_at") + " AS DOUBLE PRECISION)<? OR "
            "CAST(COALESCE(" + tx.field("_deleted") + ", 'false') AS TEXT) IN ('true','1'))"
            " ORDER BY id LIMIT ?",
            (tx.application, now, limit),
        ).fetchall()
        collected = 0
        for raw in rows:
            row = json.loads(raw["body"])
            if row["id"] in pending_files:
                continue
            tx.purge_blob(row)
            row["_expired"] = row.get("expires_at", float("inf")) < now
            tx.put(row)
            collected += 1
        sessions = tx.execute(
            "SELECT body FROM managed_objects "  # nosec B608 - fixed fields; values bound
            "WHERE application=? AND kind='session' AND "
            "CAST(" + tx.field("_retain_until") + " AS DOUBLE PRECISION)<? AND "
            "CAST(COALESCE("
            + tx.field("_cleanup_confirmed")
            + ", 'false') AS TEXT) IN ('true','1')"
            " AND CAST(COALESCE("
            + tx.field("_collected")
            + ", 'false') AS TEXT) NOT IN ('true','1')"
            " ORDER BY id LIMIT 10",
            (tx.application, now),
        ).fetchall()
        for raw in sessions:
            session = json.loads(raw["body"])
            if session.get("_resource") or session.get("_creation_started"):
                continue
            children = tx.execute(
                "SELECT id,body FROM managed_objects WHERE application=? AND parent=? AND id>?"
                " ORDER BY id LIMIT ?",
                (tx.application, session["id"], session.get("_collect_cursor", ""), limit),
            ).fetchall()
            for child in children:
                row = json.loads(child["body"])
                tx.purge_blob(row)
                for field in ("content", "_prompt", "_files", "agent"):
                    row.pop(field, None)
                row["_expired"], row["_deleted"] = True, True
                tx.put(row)
                session["_collect_cursor"] = row["id"]
                collected += 1
            first = tx.execute(
                "SELECT MIN(seq) AS first FROM managed_events WHERE application=? AND session_id=?",
                (tx.application, session["id"]),
            ).fetchone()["first"]
            if first is not None:
                tx.execute(
                    "DELETE FROM managed_events WHERE application=? AND session_id=? AND seq<?",
                    (tx.application, session["id"], first + limit),
                )
            session["_expired"] = True
            if len(children) < limit and first is None:
                session["_collected"] = True
            tx.put(session)
        return collected

    def _cancel(
        self, tx: Transaction, session: dict[str, Any], submission: dict[str, Any]
    ) -> dict[str, Any]:
        previous = submission.get("_cancel_operation")
        if previous:
            return tx.get(previous, session["_owner"])
        op = new_object(
            "operation",
            session["_owner"],
            parent=session["id"],
            kind="cancel",
            status="queued",
            result=None,
            error=None,
            _submission=submission["id"],
            _revision=session["_revision"],
        )
        submission["_cancel_operation"] = op["id"]
        if submission["status"] in SUBMISSION_TERMINAL:
            op.update(
                status="requires_reconcile" if submission["status"] == "uncertain" else "succeeded",
                result={"stop_confirmed": submission["status"] != "uncertain"},
            )
        elif submission["status"] == "queued":
            submission["status"] = "cancelled"
            op.update(status="succeeded", result={"stop_confirmed": True})
            tx.event(
                session, "agent.session.submission.cancelled", {"submission_id": submission["id"]}
            )
        else:
            submission["_cancel"] = True
            submission["status"] = "cancelling"
        tx.put(submission)
        tx.put(op)
        return op

    def _close(self, tx: Transaction, session: dict[str, Any]) -> dict[str, Any]:
        if session.get("_close_operation"):
            return tx.get(session["_close_operation"], session["_owner"])
        op = new_object(
            "operation",
            session["_owner"],
            parent=session["id"],
            kind="close",
            status="queued",
            result=None,
            error=None,
            _revision=session["_revision"],
        )
        session["_close_operation"], session["_close_requested"] = op["id"], True
        session["x_agent_sandbox"]["lifecycle"] = "closing"
        for sub in tx.list("submission", parent=session["id"]):
            if sub["status"] not in SUBMISSION_TERMINAL:
                self._cancel(tx, session, sub)
        tx.put(op)
        tx.event(session, "agent.session.closing", {})
        return op

    def handle(
        self,
        owner: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        key: str = "",
    ) -> tuple[int, Any, dict[str, str]]:
        """Apply the stream/deletion gate before taking the application transaction."""
        parts = path.strip("/").split("/")
        if method == "DELETE" and len(parts) == 4 and parts[:3] == ["v1", "agents", "sessions"]:
            with self.store.session_gate(parts[3]):
                return self._handle(owner, method, path, body, query, key)
        return self._handle(owner, method, path, body, query, key)

    def _handle(
        self,
        owner: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        key: str = "",
    ) -> tuple[int, Any, dict[str, str]]:
        """Handle one finite business operation; streaming is separately subscribed."""
        body, query = body or {}, query or {}
        parts = path.strip("/").split("/")
        if method == "GET" and path == "/v1/agent-sandbox/capabilities":
            return 200, self.capabilities(), {}
        if method == "GET" and path in {"/v1/models", "/v1/agents/runtimes"}:
            data = (
                [
                    {"id": model, "object": "model", "owned_by": "agent-sandbox-managed"}
                    for model in self.config.models
                ]
                if path == "/v1/models"
                else [
                    {"id": name, "object": "agent.runtime", "implemented": True, "installed": True}
                    for name in sorted(set(self.config.models.values()))
                ]
            )
            return 200, {"object": "list", "data": data}, {}
        if method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "models"]:
            if parts[2] not in self.config.models:
                raise ManagedError(404, "model_not_found", "Model was not found")
            return 200, {"id": parts[2], "object": "model", "owned_by": "agent-sandbox-managed"}, {}
        if path == "/v1/agents/sessions" and method == "POST":
            row, subid = self.create_session(owner, body, key)
            headers = {"Location": "/v1/agents/sessions/" + row["id"]}
            if subid:
                headers["X-Agent-Sandbox-Submission-Id"] = subid
            return 201, row, headers
        with self.store.transaction() as tx:
            if path == "/v1/agents":
                if method == "GET":
                    return 200, self._page(tx.list("agent", owner), owner, "agents", query), {}
                if method == "POST":
                    old = self._idem(tx, owner, "create-agent", key, body)
                    if old:
                        return 201, public(tx.get(old["id"], owner)), {}
                    agent = new_object("agent", owner, **self._agent(body))
                    tx.put(agent)
                    self._remember(tx, owner, "create-agent", key, body, {"id": agent["id"]})
                    return 201, public(agent), {}
            if (
                len(parts) == 3
                and parts[:2] == ["v1", "agents"]
                and parts[2] not in {"sessions", "environments", "runtimes"}
            ):
                row = tx.get(parts[2], owner)
                if row["_kind"] != "agent":
                    raise ManagedError(404, "resource_not_found", "Agent was not found")
                if method == "GET":
                    return 200, public(row), {}
                if method == "POST":
                    row.update(self._agent(body, row))
                    tx.put(row)
                    return 200, public(row), {}
                if method == "DELETE":
                    row["_deleted"] = True
                    tx.put(row)
                    return 200, {"id": row["id"], "object": "agent.deleted", "deleted": True}, {}
            if (
                path in {"/v1/agents/sessions", "/v1/agents/environments", "/v1/files"}
                and method == "GET"
            ):
                kind = {"sessions": "session", "environments": "environment", "files": "file"}[
                    parts[-1]
                ]
                rows = tx.list(kind, owner)
                if kind == "environment":
                    rows = [
                        r
                        for r in rows
                        if not tx.get(r["_parent"], owner, deleted=True).get("_deleted")
                    ]
                    for row in rows:
                        parent = self._session(tx, row["_parent"], owner)
                        row["x_agent_sandbox"] = {
                            "lifecycle": parent["x_agent_sandbox"]["lifecycle"],
                            "expires_at": parent.get("_deadline"),
                        }
                return 200, self._page(rows, owner, kind, query), {}
            if len(parts) >= 3 and parts[:2] == ["v1", "files"]:
                row = tx.get(parts[2], owner)
                if row["_kind"] != "file":
                    raise ManagedError(404, "resource_not_found", "File was not found")
                if row.get("expires_at", 0) <= time.time():
                    raise ManagedError(410, "resource_expired", "File content has expired")
                if method == "GET" and len(parts) == 3:
                    return 200, public(row), {}
                if method == "GET" and parts[3:] == ["content"]:
                    blob = tx.get(row["id"], owner, with_data=True)
                    return (
                        200,
                        base64.b64decode(blob["_data"]),
                        {"Content-Type": "application/octet-stream"},
                    )
                if method == "DELETE" and len(parts) == 3:
                    row["_deleted"] = True
                    tx.put(row)
                    return 200, {"id": row["id"], "object": "file.deleted", "deleted": True}, {}
            if (
                len(parts) == 4
                and parts[:3] == ["v1", "agents", "environments"]
                and method == "GET"
            ):
                row = tx.get(parts[3], owner)
                if row["_kind"] != "environment":
                    raise ManagedError(404, "resource_not_found", "Environment was not found")
                parent = self._session(tx, row["_parent"], owner)
                row["x_agent_sandbox"] = {
                    "lifecycle": parent["x_agent_sandbox"]["lifecycle"],
                    "expires_at": parent.get("_deadline"),
                }
                return 200, public(row), {}
            if (
                len(parts) == 4
                and parts[:3] == ["v1", "agent-sandbox", "operations"]
                and method == "GET"
            ):
                row = tx.get(parts[3], owner)
                if row["_kind"] != "operation":
                    raise ManagedError(404, "resource_not_found", "Operation was not found")
                return 200, public(row), {}
            managed = parts[:3] == ["v1", "agent-sandbox", "sessions"]
            standard = parts[:3] == ["v1", "agents", "sessions"]
            if (managed or standard) and len(parts) >= 4:
                session = self._session(tx, parts[3], owner)
                tail = parts[4:]
                if standard and not tail:
                    if method == "GET":
                        return 200, public(session), {}
                    if method == "POST":
                        reject_unknown(body, {"metadata"})
                        if "metadata" in body:
                            session["metadata"] = metadata(body["metadata"])
                            tx.put(session)
                        return 200, public(session), {}
                    if method == "DELETE":
                        pending = [
                            r
                            for r in tx.list("submission", parent=session["id"])
                            if r["status"] not in SUBMISSION_TERMINAL
                        ]
                        if pending or session["x_agent_sandbox"]["lifecycle"] == "closing":
                            raise ManagedError(
                                409, "active_session", "Cancel or close active work before deletion"
                            )
                        op = self._close(tx, session)
                        op["kind"] = "delete"
                        tx.put(op)
                        session["_deleted"] = True
                        # Purge public payloads while preserving private ownership/cleanup.
                        for kind in ("turn", "item", "artifact", "submission", "environment"):
                            for row in tx.list(kind, owner, parent=session["id"]):
                                row["_deleted"] = True
                                if kind in {"artifact", "item"}:
                                    tx.purge_blob(row)
                                    row.pop("content", None)
                                tx.put(row)
                        tx.put(session)
                        return (
                            200,
                            {
                                "id": session["id"],
                                "object": "agent.session.deleted",
                                "deleted": True,
                            },
                            {
                                "X-Agent-Sandbox-Operation-Id": op["id"],
                                "Location": "/v1/agent-sandbox/operations/" + op["id"],
                            },
                        )
                if standard and tail == ["events"] and method == "POST":
                    reject_unknown(body, {"events", "input", "x_agent_sandbox"})
                    if "events" in body:
                        events = body["events"]
                        if (
                            not isinstance(events, list)
                            or len(events) != 1
                            or not isinstance(events[0], dict)
                        ):
                            raise ManagedError(
                                400, "invalid_events", "Submit exactly one event", "events"
                            )
                        event = events[0]
                        reject_unknown(event, {"type", "input"}, "events[0].")
                        if event.get("type") == "agent.session.input.cancel":
                            scope = "cancel:" + session["id"]
                            old = self._idem(tx, owner, scope, key, body)
                            if old is not None:
                                return (
                                    202,
                                    None,
                                    (
                                        {"X-Agent-Sandbox-Operation-Id": old["operation_id"]}
                                        if old.get("operation_id")
                                        else {}
                                    ),
                                )
                            pending = [
                                r
                                for r in tx.list("submission", parent=session["id"])
                                if r["status"] not in SUBMISSION_TERMINAL and r.get("turn_id")
                            ]
                            cancel_op = self._cancel(tx, session, pending[0]) if pending else None
                            self._remember(
                                tx,
                                owner,
                                scope,
                                key,
                                body,
                                {"operation_id": cancel_op["id"] if cancel_op else None},
                            )
                            return (
                                202,
                                None,
                                {"X-Agent-Sandbox-Operation-Id": cancel_op["id"]}
                                if cancel_op
                                else {},
                            )
                        if event.get("type") != "agent.session.input.message":
                            raise ManagedError(
                                400,
                                "unsupported_feature",
                                "This event type is not supported",
                                "events[0].type",
                            )
                        prompt = event.get("input")
                    else:
                        prompt = body.get("input")
                    sub = self._enqueue(
                        tx,
                        session,
                        {"input": prompt, "x_agent_sandbox": body.get("x_agent_sandbox", {})},
                        key,
                        queue=False,
                    )
                    return (
                        202,
                        None,
                        {
                            "X-Agent-Sandbox-Submission-Id": sub["id"],
                            "Location": (
                                f"/v1/agent-sandbox/sessions/{session['id']}"
                                f"/submissions/{sub['id']}"
                            ),
                        },
                    )
                if managed and tail == ["close"] and method == "POST":
                    reject_unknown(body, set())
                    op = self._close(tx, session)
                    return 202, public(op), {"Location": "/v1/agent-sandbox/operations/" + op["id"]}
                if managed and tail == ["submissions"]:
                    if method == "POST":
                        reject_unknown(body, {"input", "x_agent_sandbox"})
                        if not key:
                            raise ManagedError(
                                400,
                                "idempotency_key_required",
                                "Explicit enqueue requires Idempotency-Key",
                            )
                        return 202, public(self._enqueue(tx, session, body, key, queue=True)), {}
                    if method == "GET":
                        rows = tx.list("submission", owner, session["id"])
                        if "idempotency_key" in query:
                            rows = [r for r in rows if r.get("_key") == query["idempotency_key"]]
                        return (
                            200,
                            self._page(rows, owner, "submissions:" + session["id"], query),
                            {},
                        )
                if managed and len(tail) >= 2 and tail[0] in {"submissions", "turns"}:
                    row = tx.get(tail[1], owner)
                    expected = "submission" if tail[0] == "submissions" else "turn"
                    if row.get("_parent") != session["id"] or row["_kind"] != expected:
                        raise ManagedError(404, "resource_not_found", "Resource was not found")
                    if tail[0] == "submissions" and len(tail) == 2 and method == "GET":
                        return 200, public(row), {}
                    if tail[2:] == ["cancel"] and method == "POST":
                        reject_unknown(body, set())
                        if tail[0] == "turns":
                            row = tx.get(row["_submission"], owner)
                        return 202, public(self._cancel(tx, session, row)), {}
                if standard and tail and tail[0] in {"items", "turns", "artifacts"}:
                    kind = {"items": "item", "turns": "turn", "artifacts": "artifact"}[tail[0]]
                    if len(tail) == 1 and method == "GET":
                        return (
                            200,
                            self._page(
                                tx.list(kind, owner, session["id"]),
                                owner,
                                kind + ":" + session["id"],
                                query,
                            ),
                            {},
                        )
                    if len(tail) >= 2:
                        row = tx.get(tail[1], owner)
                        if row.get("_parent") != session["id"] or row["_kind"] != kind:
                            raise ManagedError(404, "resource_not_found", "Resource was not found")
                        if row.get("expires_at", float("inf")) <= time.time():
                            raise ManagedError(410, "resource_expired", "Stored result has expired")
                        if len(tail) == 2 and method == "GET":
                            return 200, public(row), {}
                        if kind == "turn" and tail[2:] == ["items"] and method == "GET":
                            rows = [
                                r
                                for r in tx.list("item", owner, session["id"])
                                if r.get("turn_id") == row["id"]
                            ]
                            return (
                                200,
                                self._page(rows, owner, "turn-items:" + row["id"], query),
                                {},
                            )
                        if kind == "artifact" and tail[2:] == ["content"] and method == "GET":
                            blob = tx.get(row["id"], owner, with_data=True)
                            return (
                                200,
                                base64.b64decode(blob["_data"]),
                                {
                                    "Content-Type": "application/octet-stream",
                                    "Content-Disposition": "attachment",
                                },
                            )
                        if kind == "artifact" and len(tail) == 2 and method == "DELETE":
                            row["_deleted"] = True
                            tx.purge_blob(row)
                            tx.put(row)
                            return (
                                200,
                                {
                                    "id": row["id"],
                                    "object": "agent.session.artifact.deleted",
                                    "deleted": True,
                                },
                                {},
                            )
        raise ManagedError(404, "endpoint_not_available", "This endpoint is not available")

    def events(self, owner: str, sid: str, cursor: str | None = None) -> list[dict[str, Any]]:
        """Read durable public events with a Session-bound cursor."""
        with self.store.transaction() as tx:
            session = self._session(tx, sid, owner)
            prefix = "evt_" + sid + "_"
            if cursor is None or cursor == "0":
                seq = 0
            elif cursor.startswith(prefix) and cursor[len(prefix) :].isdigit():
                seq = int(cursor[len(prefix) :])
            else:
                raise ManagedError(
                    400, "invalid_cursor", "Event cursor belongs to another Session", "after"
                )
            if seq > session.get("_seq", 0):
                raise ManagedError(
                    400, "invalid_cursor", "Event cursor is ahead of this Session", "after"
                )
            return tx.events(sid, seq)
