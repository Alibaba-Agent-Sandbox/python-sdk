"""Transactional run/event/outbox storage. SQLite is explicitly local-only.

PostgreSQL row locks serialize per-run mutation and application admission. There
is no lease takeover: an expired running lease becomes requires_reconcile.
This deliberately avoids replaying unknown remote side effects.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import sqlite3
import time
import uuid
from typing import TYPE_CHECKING, Any

from .models import (
    TERMINAL,
    Application,
    ApplicationError,
    ExecutionResult,
    canonical,
    digest,
    timestamp,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS app_revisions (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS app_runs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
    "revision TEXT NOT NULL, placement TEXT NOT NULL, snapshot TEXT NOT NULL, "
    "snapshot_digest TEXT NOT NULL, request TEXT NOT NULL, idem TEXT NOT NULL, "
    "status TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, deadline DOUBLE PRECISION NOT NULL, "
    "attempt TEXT, lease DOUBLE PRECISION, cancel INTEGER NOT NULL DEFAULT 0, "
    "seq INTEGER NOT NULL DEFAULT 0, integrity TEXT NOT NULL DEFAULT 'complete', "
    "failure TEXT, result TEXT, resource TEXT, UNIQUE(owner, revision, idem))",
    "CREATE TABLE IF NOT EXISTS app_events (run_id TEXT NOT NULL, seq INTEGER NOT NULL, "
    "body TEXT NOT NULL, PRIMARY KEY(run_id, seq))",
    "CREATE TABLE IF NOT EXISTS app_outbox (run_id TEXT PRIMARY KEY, attempts INTEGER NOT NULL "
    "DEFAULT 0, next_at DOUBLE PRECISION NOT NULL, "
    "lease_until DOUBLE PRECISION NOT NULL DEFAULT 0, "
    "lease_owner TEXT, delivered INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS app_artifacts (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, "
    "name TEXT NOT NULL, content TEXT NOT NULL, media_type TEXT NOT NULL, "
    "size INTEGER NOT NULL, sha256 TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS app_runs_revision_status ON app_runs(revision, status)",
)


class Store:
    """Durable state store with explicit PostgreSQL or local SQLite configuration.

    PostgreSQL requires the optional ``applications-postgres`` extra. The URL is
    never included in errors or logs. Use a private database and least privilege.
    """

    def __init__(self, url: str, *, local: bool = False) -> None:
        self._url = url
        self._sqlite = url.startswith("sqlite:///")
        if self._sqlite:
            if not local or any(os.getenv(key) for key in ("FC_FUNCTION_NAME", "FC_INSTANCE_ID")):
                raise ValueError(
                    "SQLite application storage is allowed only in explicit local mode"
                )
            if url == "sqlite:///:memory:":
                raise ValueError("Use a file-backed SQLite database for durable local execution")
        elif not url.startswith(("postgres://", "postgresql://")):
            raise ValueError("Application storage requires PostgreSQL or explicit local SQLite")
        with self._transaction() as db:
            if not self._sqlite:
                # Serialize first-start DDL across independent FC instances.
                self._execute(
                    db, "SELECT pg_advisory_xact_lock(?)", (int.from_bytes(b"ABXAPP", "big"),)
                )
            for statement in _SCHEMA:
                self._execute(db, statement)

    def __repr__(self) -> str:
        return f"Store(backend={'sqlite-local' if self._sqlite else 'postgresql'})"

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[Any]:
        if self._sqlite:
            db: Any = sqlite3.connect(self._url[len("sqlite:///") :], timeout=30)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
        else:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("Install agent-sandbox-client[applications-postgres]") from exc
            db = psycopg.connect(self._url, row_factory=dict_row, connect_timeout=10)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _execute(self, db: Any, sql: str, values: tuple[Any, ...] = ()) -> Any:
        return db.execute(sql if self._sqlite else sql.replace("?", "%s"), values)

    def _run(self, db: Any, run_id: str, *, owner: str | None = None) -> dict[str, Any]:
        suffix = "" if self._sqlite else " FOR UPDATE"
        raw = self._execute(db, "SELECT * FROM app_runs WHERE id=?" + suffix, (run_id,)).fetchone()
        if raw is None or (owner is not None and raw["owner"] != owner):
            raise ApplicationError(404, "not_found", "Run was not found")
        return dict(raw)

    def _event(self, db: Any, row: dict[str, Any], kind: str, data: dict[str, Any]) -> None:
        limit = json.loads(row["snapshot"])["limits"]["events"]
        if row["seq"] >= limit:
            raise ApplicationError(409, "event_budget", "Run event budget exhausted")
        row["seq"] += 1
        body = {
            "runId": row["id"],
            "attemptId": row["attempt"],
            "seq": row["seq"],
            "type": kind,
            "occurredAt": timestamp(time.time()),
            "data": data,
        }
        if len(canonical(body).encode()) > 131072:
            raise ApplicationError(400, "event_too_large", "Event exceeds size limit")
        self._execute(
            db,
            "INSERT INTO app_events VALUES(?,?,?)",
            (
                row["id"],
                row["seq"],
                canonical(body),
            ),
        )
        self._execute(db, "UPDATE app_runs SET seq=? WHERE id=?", (row["seq"], row["id"]))

    def create(
        self, owner: str, app: Application, key: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Atomically admit a run, its first event and a durable dispatch outbox row."""
        now = time.time()
        snapshot = canonical(app.execution_snapshot())
        request = canonical(body)
        with self._transaction() as db:
            self._execute(
                db,
                "INSERT INTO app_revisions(id,snapshot) VALUES(?,?) ON CONFLICT(id) DO NOTHING",
                (app.revision, snapshot),
            )
            suffix = "" if self._sqlite else " FOR UPDATE"
            deployed = self._execute(
                db, "SELECT snapshot FROM app_revisions WHERE id=?" + suffix, (app.revision,)
            ).fetchone()
            if deployed["snapshot"] != snapshot:
                raise ApplicationError(409, "revision_changed", "Deploy a new application revision")
            previous = self._execute(
                db,
                "SELECT * FROM app_runs WHERE owner=? AND revision=? AND idem=?",
                (owner, app.revision, key),
            ).fetchone()
            if previous is not None:
                if previous["request"] != request:
                    raise ApplicationError(
                        409, "idempotency_mismatch", "Key belongs to another request"
                    )
                return dict(previous)
            queued = self._execute(
                db,
                "SELECT COUNT(*) AS n FROM app_runs WHERE revision=? "
                "AND status IN ('accepted','queued')",
                (app.revision,),
            ).fetchone()["n"]
            recent = self._execute(
                db,
                "SELECT COUNT(*) AS n FROM app_runs WHERE revision=? AND created>?",
                (app.revision, now - 60),
            ).fetchone()["n"]
            if queued >= app.max_queued_runs or recent >= app.max_runs_per_minute:
                raise ApplicationError(429, "capacity", "Application admission budget exceeded")
            run_id = "run_" + uuid.uuid4().hex
            self._execute(
                db,
                "INSERT INTO app_runs(id,owner,revision,placement,snapshot,"
                "snapshot_digest,request,idem,status,created,deadline) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    owner,
                    app.revision,
                    app.placement,
                    snapshot,
                    digest(json.loads(snapshot)),
                    request,
                    key,
                    "accepted",
                    now,
                    now + app.max_run_seconds,
                ),
            )
            row = self._run(db, run_id)
            self._event(db, row, "run.accepted", {})
            self._execute(db, "INSERT INTO app_outbox(run_id,next_at) VALUES(?,?)", (run_id, now))
            return row

    def get(self, run_id: str, owner: str | None = None) -> dict[str, Any]:
        """Read authoritative state; foreign and unknown runs have the same error."""
        with self._transaction() as db:
            return self._run(db, run_id, owner=owner)

    def cancel(self, run_id: str, owner: str) -> dict[str, Any]:
        """Record cancellation intent, or prove an unclaimed run never started."""
        with self._transaction() as db:
            row = self._run(db, run_id, owner=owner)
            if row["status"] in TERMINAL or row["cancel"]:
                return row
            self._execute(db, "UPDATE app_runs SET cancel=1 WHERE id=?", (run_id,))
            self._event(db, row, "cancel.requested", {})
            if row["attempt"] is None:
                return self._finish(db, row, "cancelled", ExecutionResult(""))
            if row["status"] == "requires_reconcile":
                # Cancellation intent must not reopen a fenced execution lease.
                row["cancel"] = 1
                return row
            self._execute(db, "UPDATE app_runs SET status='cancelling' WHERE id=?", (run_id,))
            row["status"] = "cancelling"
            row["cancel"] = 1
            return row

    def claim(self, run_id: str, app: Application, *, lease_seconds: int = 30) -> str | None:
        """Claim once; reject duplicates, expired deadlines and changed revisions."""
        now = time.time()
        with self._transaction() as db:
            # Match create's admission lock; concurrent worker starts are bounded globally.
            suffix = "" if self._sqlite else " FOR UPDATE"
            self._execute(
                db, "SELECT id FROM app_revisions WHERE id=?" + suffix, (app.revision,)
            ).fetchone()
            row = self._run(db, run_id)
            if row["status"] not in {"accepted", "queued"} or row["attempt"]:
                return None
            if row["snapshot"] != canonical(app.execution_snapshot()):
                self._finish(db, row, "failed", ExecutionResult(""), "revision_unavailable")
                return None
            if row["cancel"] or now >= row["deadline"]:
                self._finish(
                    db, row, "cancelled" if row["cancel"] else "timed_out", ExecutionResult("")
                )
                return None
            active = self._execute(
                db,
                "SELECT COUNT(*) AS n FROM app_runs WHERE revision=? "
                "AND status IN ('provisioning','running','cancelling',"
                "'requires_reconcile')",
                (app.revision,),
            ).fetchone()["n"]
            if active >= app.max_concurrent_runs:
                # The accepted invocation may be acknowledged; durable dispatcher retries later.
                self._execute(
                    db,
                    "UPDATE app_outbox SET delivered=0,next_at=?,lease_until=0 WHERE run_id=?",
                    (now + 5, run_id),
                )
                return None
            attempt = "attempt_" + uuid.uuid4().hex
            self._execute(
                db,
                "UPDATE app_runs SET status='provisioning',attempt=?,lease=? WHERE id=?",
                (attempt, now + lease_seconds, run_id),
            )
            return attempt

    def heartbeat(self, run_id: str, attempt: str, *, lease_seconds: int = 30) -> dict[str, Any]:
        """Renew only a live lease; an expired or reconciled worker stays fenced."""
        with self._transaction() as db:
            row = self._run(db, run_id)
            if (
                row["attempt"] != attempt
                or row["status"] in TERMINAL
                or row["status"] == "requires_reconcile"
                or row["lease"] < time.time()
            ):
                raise ApplicationError(409, "lease_lost", "Execution lease is no longer valid")
            self._execute(
                db,
                "UPDATE app_runs SET lease=? WHERE id=?",
                (
                    time.time() + lease_seconds,
                    run_id,
                ),
            )
            return row

    def started(self, run_id: str, attempt: str) -> None:
        """Persist the start transition before executing Agent/model/tool code."""
        with self._transaction() as db:
            row = self._run(db, run_id)
            self._check_attempt(row, attempt)
            if row["cancel"] or time.time() >= row["deadline"]:
                raise ApplicationError(409, "execution_stopped", "Run is stopping")
            self._execute(db, "UPDATE app_runs SET status='running' WHERE id=?", (run_id,))
            self._event(db, row, "run.started", {})

    def emit(self, run_id: str, attempt: str, kind: str, data: dict[str, Any]) -> None:
        """Commit a bounded public event before publishing it over SSE."""
        if kind not in {"output.delta", "tool.started", "tool.completed", "artifact.created"}:
            raise ValueError("Unsupported executor event type")
        with self._transaction() as db:
            row = self._run(db, run_id)
            self._check_attempt(row, attempt)
            # Reserve cancellation, uncertain-stop and reconciled terminal outcome.
            if row["seq"] >= json.loads(row["snapshot"])["limits"]["events"] - 3:
                raise ApplicationError(409, "event_budget", "Run event budget exhausted")
            self._event(db, row, kind, data)

    def bind_resource(self, run_id: str, attempt: str, receipt: dict[str, Any]) -> None:
        """Save a non-secret exclusive sandbox receipt before issuing tools."""
        with self._transaction() as db:
            row = self._run(db, run_id)
            self._check_attempt(row, attempt)
            self._execute(
                db, "UPDATE app_runs SET resource=? WHERE id=?", (canonical(receipt), run_id)
            )

    @staticmethod
    def _check_attempt(row: dict[str, Any], attempt: str) -> None:
        if (
            row["attempt"] != attempt
            or row["status"] in TERMINAL
            or row["status"] == "requires_reconcile"
            or row["lease"] < time.time()
        ):
            raise ApplicationError(409, "lease_lost", "Execution lease is no longer valid")

    def finish(
        self,
        run_id: str,
        attempt: str,
        status: str,
        result: ExecutionResult,
        failure: str | None = None,
    ) -> None:
        """Finish after verified cleanup. Cancellation wins once recorded."""
        with self._transaction() as db:
            row = self._run(db, run_id)
            self._check_attempt(row, attempt)
            if row["cancel"]:
                status, result = "cancelled", ExecutionResult("")
            elif time.time() >= row["deadline"]:
                status, result = "timed_out", ExecutionResult("")
            self._finish(db, row, status, result, failure)

    def _finish(
        self,
        db: Any,
        row: dict[str, Any],
        status: str,
        result: ExecutionResult,
        failure: str | None = None,
    ) -> dict[str, Any]:
        if status not in TERMINAL:
            raise ValueError("Expected a terminal status")
        limits = json.loads(row["snapshot"])["limits"]
        if (
            len(result.text.encode()) > min(limits["outputBytes"], 65536)
            or len(result.artifacts) > 100
        ):
            raise ApplicationError(409, "output_budget", "Run output budget exceeded")
        if sum(len(art.content) for art in result.artifacts) > limits["artifactBytes"]:
            raise ApplicationError(409, "artifact_budget", "Run artifact budget exceeded")
        artifacts = []
        for artifact in result.artifacts:
            if not artifact.name or len(artifact.name) > 256:
                raise ValueError("Invalid artifact name")
            aid = "artifact_" + uuid.uuid4().hex
            sha = hashlib.sha256(artifact.content).hexdigest()
            self._execute(
                db,
                "INSERT INTO app_artifacts VALUES(?,?,?,?,?,?,?)",
                (
                    aid,
                    row["id"],
                    artifact.name,
                    base64.b64encode(artifact.content).decode(),
                    artifact.media_type,
                    len(artifact.content),
                    sha,
                ),
            )
            artifacts.append(
                {
                    "id": aid,
                    "name": artifact.name,
                    "sizeBytes": len(artifact.content),
                    "sha256": sha,
                    "contentLink": f"/v1/agent-runs/{row['id']}/artifacts/{aid}/content",
                }
            )
        body: dict[str, Any] = {
            "runId": row["id"],
            "status": status,
            "outputText": result.text,
            "artifacts": artifacts,
        }
        if failure:
            body["failureCode"] = failure
        self._execute(
            db,
            "UPDATE app_runs SET status=?,result=?,failure=?,lease=NULL WHERE id=?",
            (status, canonical(body), failure, row["id"]),
        )
        self._execute(db, "UPDATE app_outbox SET delivered=1 WHERE run_id=?", (row["id"],))
        row["status"] = status
        kind = {
            "succeeded": "run.completed",
            "failed": "run.failed",
            "cancelled": "run.cancelled",
            "timed_out": "run.timed_out",
        }[status]
        self._event(db, row, kind, {"status": status})
        return row

    def reconcile(self) -> int:
        """Fence expired workers; expire only runs proven never to have started.

        This never steals a lease or assumes stopping FC stopped a sandbox.
        Operator reconciliation must terminate/inspect the recorded sandbox.
        """
        now, count = time.time(), 0
        with self._transaction() as db:
            ids = self._execute(
                db,
                "SELECT id FROM app_runs WHERE status NOT IN "
                "('succeeded','failed','cancelled','timed_out','requires_reconcile') "
                "AND (deadline<? OR lease<?)",
                (now, now),
            ).fetchall()
            for item in ids:
                row = self._run(db, item["id"])
                if row["status"] in TERMINAL or row["status"] == "requires_reconcile":
                    continue
                if row["attempt"] is None:
                    self._finish(db, row, "timed_out", ExecutionResult(""))
                elif row["lease"] < now:
                    self._mark_uncertain(db, row)
                else:
                    continue
                count += 1
        return count

    def uncertain(self, run_id: str, attempt: str) -> None:
        """Record uncertain resource cleanup without exposing implementation details."""
        with self._transaction() as db:
            row = self._run(db, run_id)
            if row["attempt"] == attempt and row["status"] not in TERMINAL:
                self._mark_uncertain(db, row)

    def resolve_uncertain(
        self, run_id: str, expected_attempt: str, verify_quiesced: Callable[[dict[str, Any]], bool]
    ) -> bool:
        """Trusted operator recovery after native execution AND resources are stopped.

        The callback must prove the old worker cannot continue (including pending
        creation), and every run-owned sandbox is absent/terminated. For ambiguous
        creation it must inspect run metadata, not just an absent receipt. No
        business HTTP endpoint exposes this operation. Verification executes
        outside database locks; state/attempt/resource are compared again at commit.
        """
        observed = self.get(run_id)
        if observed["status"] != "requires_reconcile" or observed["attempt"] != expected_attempt:
            return False
        receipt = json.loads(observed["resource"]) if observed["resource"] else None
        proof_context = {
            "runId": run_id,
            "attemptId": expected_attempt,
            "applicationRevision": observed["revision"],
            "resource": receipt,
            "executionSnapshot": json.loads(observed["snapshot"]),
        }
        if not verify_quiesced(proof_context):
            return False
        with self._transaction() as db:
            row = self._run(db, run_id)
            if (
                row["status"] != "requires_reconcile"
                or row["attempt"] != expected_attempt
                or row["resource"] != observed["resource"]
            ):
                return False
            status = (
                "cancelled"
                if row["cancel"]
                else "timed_out"
                if time.time() >= row["deadline"]
                else "failed"
            )
            self._finish(
                db,
                row,
                status,
                ExecutionResult(""),
                "execution_reconciled" if status == "failed" else None,
            )
            return True

    def _mark_uncertain(self, db: Any, row: dict[str, Any]) -> None:
        if row["status"] == "requires_reconcile":
            return
        self._execute(
            db,
            "UPDATE app_runs SET status='requires_reconcile',failure=? WHERE id=?",
            ("execution_uncertain", row["id"]),
        )
        self._event(db, row, "run.requires_reconcile", {})

    def events(self, run_id: str, owner: str, after: int = 0) -> list[dict[str, Any]]:
        """Read a bounded page of retained events, checking ownership on reconnect."""
        with self._transaction() as db:
            row = self._run(db, run_id, owner=owner)
            if after > row["seq"]:
                raise ApplicationError(400, "invalid_cursor", "Cursor is ahead of the run")
            return [
                json.loads(event["body"])
                for event in self._execute(
                    db,
                    "SELECT body FROM app_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 1000",
                    (run_id, after),
                ).fetchall()
            ]

    def result(self, run_id: str, owner: str) -> dict[str, Any]:
        """Return durable terminal output; never re-execute an operation."""
        row = self.get(run_id, owner)
        if row["status"] not in TERMINAL:
            raise ApplicationError(409, "not_ready", "Run has no terminal result")
        return json.loads(row["result"])  # type: ignore[no-any-return]

    def artifact(self, run_id: str, owner: str, artifact_id: str) -> tuple[bytes, str]:
        """Resolve a run-owned artifact ID, never an arbitrary path or URL."""
        with self._transaction() as db:
            self._run(db, run_id, owner=owner)
            row = self._execute(
                db, "SELECT * FROM app_artifacts WHERE run_id=? AND id=?", (run_id, artifact_id)
            ).fetchone()
            if row is None:
                raise ApplicationError(404, "not_found", "Artifact was not found")
            return base64.b64decode(row["content"]), row["media_type"]

    def next_dispatch(self, *, lease_seconds: int = 30) -> tuple[str, str] | None:
        """Lease one dispatch; crash before acknowledgement permits duplicate delivery."""
        now, token = time.time(), uuid.uuid4().hex
        with self._transaction() as db:
            suffix = "" if self._sqlite else " FOR UPDATE SKIP LOCKED"
            row = self._execute(
                db,
                "SELECT * FROM app_outbox WHERE delivered=0 AND next_at<=? "
                "AND lease_until<=? ORDER BY next_at LIMIT 1" + suffix,
                (now, now),
            ).fetchone()
            if row is None:
                return None
            self._execute(
                db,
                "UPDATE app_outbox SET lease_until=?,lease_owner=? WHERE run_id=?",
                (now + lease_seconds, token, row["run_id"]),
            )
            return row["run_id"], token

    def dispatched(self, run_id: str, token: str, *, success: bool) -> None:
        """Ack only the dispatch lease owner; ambiguous sends are safely redelivered."""
        with self._transaction() as db:
            run = self._run(db, run_id)
            suffix = "" if self._sqlite else " FOR UPDATE"
            row = self._execute(
                db, "SELECT * FROM app_outbox WHERE run_id=?" + suffix, (run_id,)
            ).fetchone()
            if row is None or row["lease_owner"] != token:
                return
            if success:
                # Retry accepted-but-not-claimed sends after a bounded grace interval.
                delivered = int(run["attempt"] is not None or run["status"] in TERMINAL)
                self._execute(
                    db,
                    "UPDATE app_outbox SET delivered=?,lease_until=0,next_at=? "
                    "WHERE run_id=? AND lease_owner=?",
                    (delivered, time.time() + 30, run_id, token),
                )
            else:
                attempts = row["attempts"] + 1
                self._execute(
                    db,
                    "UPDATE app_outbox SET attempts=attempts+1,lease_until=0,next_at=? "
                    "WHERE run_id=? AND lease_owner=?",
                    (time.time() + min(60, 2 ** min(attempts, 6)), run_id, token),
                )
            if run["status"] == "accepted":
                self._execute(db, "UPDATE app_runs SET status='queued' WHERE id=?", (run_id,))
