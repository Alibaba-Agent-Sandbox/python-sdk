"""Transactional managed state. SQLite is explicitly local; FC requires PostgreSQL."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlsplit

from .models import ManagedError, canonical

if TYPE_CHECKING:
    import builtins
    from collections.abc import Iterator


class Transaction:
    """A transaction holding the application admission/ownership lock."""

    def __init__(self, db: Any, sqlite: bool, application: str) -> None:
        self.db, self.sqlite, self.application = db, sqlite, application

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> Any:
        """Execute portable bound SQL, never interpolating business values."""
        return self.db.execute(sql if self.sqlite else sql.replace("?", "%s"), args)

    def field(self, name: str) -> str:
        """Build fixed internal JSON field projections for indexed/bounded queries."""
        if not all(part.replace("_", "").isalnum() for part in name.split(".")):
            raise ValueError("Invalid internal field")
        if self.sqlite:
            return "json_extract(body,'$." + name + "')"
        parts = name.split(".")
        return "body::jsonb" + "".join(
            ("->>" if index == len(parts) - 1 else "->") + "'" + part + "'"
            for index, part in enumerate(parts)
        )

    def get(
        self, rid: str, owner: str | None = None, *, deleted: bool = False, with_data: bool = False
    ) -> dict[str, Any]:
        """Read one application-owned object, concealing foreign resource identities."""
        row = self.execute(
            "SELECT body FROM managed_objects WHERE application=? AND id=?", (self.application, rid)
        ).fetchone()
        if row is None:
            raise ManagedError(404, "resource_not_found", "Resource was not found")
        data: dict[str, Any] = json.loads(row["body"])
        if (owner is not None and data["_owner"] != owner) or (
            data.get("_deleted") and not deleted
        ):
            raise ManagedError(404, "resource_not_found", "Resource was not found")
        if with_data and data.get("_has_blob"):
            blob = self.execute(
                "SELECT data FROM managed_blobs WHERE application=? AND id=?",
                (self.application, rid),
            ).fetchone()
            if blob is None:
                raise ManagedError(503, "content_unavailable", "The stored content is unavailable")
            data["_data"] = blob["data"]
        return data

    def put(self, row: dict[str, Any]) -> None:
        """Create or atomically update an owned JSON record."""
        row["_updated"] = time.time()
        encoded = row.pop("_data", None)
        if encoded is not None:
            self.execute(
                "INSERT INTO managed_blobs(application,id,data) VALUES(?,?,?) ON "
                "CONFLICT(application,id) DO UPDATE SET data=excluded.data",
                (self.application, row["id"], encoded),
            )
            row["_has_blob"] = True
        self.execute(
            "INSERT INTO managed_objects(application,id,kind,parent,owner,body) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(application,id) DO UPDATE SET "
            "body=excluded.body",
            (
                self.application,
                row["id"],
                row["_kind"],
                row.get("_parent", ""),
                row["_owner"],
                canonical(row),
            ),
        )

    def purge_blob(self, row: dict[str, Any]) -> None:
        """Remove private bytes without removing the ownership tombstone."""
        self.execute(
            "DELETE FROM managed_blobs WHERE application=? AND id=?", (self.application, row["id"])
        )
        row.pop("_data", None)
        row["_has_blob"] = False

    def list(
        self,
        kind: str,
        owner: str | None = None,
        parent: str | None = None,
        *,
        deleted: bool = False,
        pending: bool = False,
        work: bool = False,
        occupied: bool = False,
        has_blob: bool = False,
        recent_after: float | None = None,
    ) -> list[dict[str, Any]]:
        """Read a bounded application resource family under the same lock."""
        sql = "SELECT body FROM managed_objects WHERE application=? AND kind=?"
        args: list[Any] = [self.application, kind]
        if owner is not None:
            sql += " AND owner=?"
            args.append(owner)
        if parent is not None:
            sql += " AND parent=?"
            args.append(parent)
        if not deleted:
            sql += (
                " AND COALESCE(" + self.field("_deleted") + ", 'false') NOT IN ('true', '1', 1)"
                if self.sqlite
                else (" AND COALESCE(" + self.field("_deleted") + ", 'false') <> 'true'")
            )
        if pending:
            sql += (
                " AND "
                + self.field("status")
                + " NOT IN ('completed','failed','cancelled','uncertain')"
            )
        if not deleted:
            sql += (
                " AND CAST(COALESCE("
                + self.field("_expired")
                + ", 'false') AS TEXT) NOT IN ('true','1')"
            )
        if work:
            sql += (
                " AND (" + self.field("x_agent_sandbox.lifecycle") + " NOT IN ('closed','expired')"
            )
            sql += " OR " + self.field("_resource.sandbox_id") + " IS NOT NULL)"
        if occupied:
            sql += " AND (" + self.field("_resource.sandbox_id") + " IS NOT NULL OR "
            sql += (
                "CAST(COALESCE("
                + self.field("_creation_started")
                + ", 'false') AS TEXT) IN ('true','1'))"
            )
        if has_blob:
            sql += (
                " AND CAST(COALESCE("
                + self.field("_has_blob")
                + ", 'false') AS TEXT) IN ('true','1')"
            )
        if recent_after is not None:
            sql += " AND CAST(" + self.field("created_at") + " AS DOUBLE PRECISION)>=?"
            args.append(recent_after)
        rows = self.execute(sql + " LIMIT 10001", tuple(args)).fetchall()
        if len(rows) > 10000:
            raise ManagedError(
                429, "collection_limit", "Collection exceeds the configured local query budget"
            )
        out = [json.loads(r["body"]) for r in rows]
        return sorted(
            (
                r
                for r in out
                if (owner is None or r["_owner"] == owner)
                and (parent is None or r.get("_parent") == parent)
                and (deleted or not r.get("_deleted"))
            ),
            key=lambda r: (r["created_at"], r["id"]),
        )

    def event(self, session: dict[str, Any], kind: str, data: dict[str, Any]) -> None:
        """Commit an immutable public event before it can be delivered to SSE."""
        session["_seq"] = session.get("_seq", 0) + 1
        event = {
            "type": kind,
            "event_id": f"evt_{session['id']}_{session['_seq']}",
            "session_id": session["id"],
            "created_at": time.time(),
            **data,
        }
        self.execute(
            "INSERT INTO managed_events(application,session_id,seq,body) VALUES(?,?,?,?)",
            (self.application, session["id"], session["_seq"], canonical(event)),
        )
        self.put(session)

    def events(self, sid: str, after: int) -> builtins.list[dict[str, Any]]:
        """Read the already committed event sequence."""
        rows = self.execute(
            "SELECT body FROM managed_events WHERE application=? AND session_id=? AND "
            "seq>? ORDER BY seq LIMIT 256",
            (self.application, sid, after),
        ).fetchall()
        return [json.loads(r["body"]) for r in rows]


def new_object(
    resource_kind: str, owner: str, *, parent: str = "", **fields: Any
) -> dict[str, Any]:
    """Build a private record; public projection must explicitly remove private fields."""
    prefix = {"session": "sess", "submission": "sub", "operation": "op", "environment": "env"}.get(
        resource_kind, resource_kind
    )
    return {
        "id": f"{prefix}_{uuid.uuid4().hex}",
        "object": {
            "agent": "agent",
            "turn": "agent.session.turn",
            "artifact": "agent.session.artifact",
            "file": "file",
        }.get(resource_kind, f"agent.{resource_kind}"),
        "created_at": time.time(),
        "_kind": resource_kind,
        "_owner": owner,
        "_parent": parent,
        **fields,
    }


class ManagedStore:
    """A fixed application database with a cross-process admission lock."""

    def __init__(
        self,
        url: str,
        application: str = "agents-api",
        *,
        local: bool = False,
        expected_state_id: str | None = None,
        database_ca_file: str | None = None,
        statement_timeout_ms: int = 10000,
        lock_timeout_ms: int = 5000,
    ) -> None:
        self.url, self.application = url, application
        self.database_ca_file = database_ca_file
        if any(
            not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= bound
            for v, bound in ((statement_timeout_ms, 10000), (lock_timeout_ms, 5000))
        ):
            raise ValueError(
                "Database statement/lock deadlines must be positive bounded milliseconds"
            )
        if any(key.lower() == "options" for key, _ in parse_qsl(urlsplit(url).query)):
            raise ValueError(
                "Database URI options are not supported; runtime deadlines are explicit"
            )
        self.pg_options = {
            "options": (
                f"-c statement_timeout={statement_timeout_ms} -c lock_timeout={lock_timeout_ms}"
            )
        }
        if database_ca_file:
            self.pg_options["sslrootcert"] = database_ca_file
        self.sqlite = url.startswith("sqlite:///")
        if self.sqlite:
            if database_ca_file is not None:
                raise ValueError("Database CA configuration requires PostgreSQL")
            if (
                not local
                or os.getenv("FC_FUNCTION_NAME")
                or os.getenv("FC_INSTANCE_ID")
                or url == "sqlite:///:memory:"
            ):
                raise ValueError("File-backed SQLite requires explicit non-FC local mode")
            if expected_state_id is not None and not os.path.isfile(url[len("sqlite:///") :]):
                raise ValueError("Expected managed state is absent; refusing initialization")
        elif not url.startswith(("postgres://", "postgresql://")):
            raise ValueError("Managed storage requires PostgreSQL or explicit local SQLite")
        with self.transaction(initialize=True) as tx:
            if expected_state_id is not None:
                if self.sqlite:
                    found = tx.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name='managed_identity'"
                    ).fetchone()
                else:
                    found = tx.execute("SELECT to_regclass('managed_identity') AS name").fetchone()
                    found = found if found and found["name"] else None
                if not found:
                    raise ValueError("Expected managed state is absent; refusing initialization")
                identity = tx.execute(
                    "SELECT state_id FROM managed_identity WHERE application=?", (application,)
                ).fetchone()
                if identity is None or identity["state_id"] != expected_state_id:
                    raise ValueError("Managed state identity does not match the pinned deployment")
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_identity(application TEXT PRIMARY KEY,"
                " state_id TEXT NOT NULL)"
            )
            tx.execute(
                "INSERT INTO managed_identity(application,state_id) VALUES(?,?) "
                "ON CONFLICT(application) DO NOTHING",
                (application, secrets.token_hex(16)),
            )
            self.state_instance_id = tx.execute(
                "SELECT state_id FROM managed_identity WHERE application=?",
                (application,),
            ).fetchone()["state_id"]
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_meta(application TEXT PRIMARY KEY, "
                "secret TEXT NOT NULL)"
            )
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_control(application TEXT PRIMARY "
                "KEY, body TEXT NOT NULL)"
            )
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_objects(application TEXT NOT "
                "NULL,id TEXT NOT NULL,kind TEXT NOT NULL,parent TEXT NOT NULL,owner "
                "TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(application,id))"
            )
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_events(application TEXT NOT "
                "NULL,session_id TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT "
                "NULL,PRIMARY KEY(application,session_id,seq))"
            )
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_blobs(application TEXT NOT NULL,id "
                "TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(application,id))"
            )
            tx.execute(
                "CREATE INDEX IF NOT EXISTS managed_objects_owner_parent ON "
                "managed_objects(application,kind,owner,parent)"
            )
            tx.execute(
                "CREATE TABLE IF NOT EXISTS managed_idempotency(application TEXT NOT "
                "NULL,scope TEXT NOT NULL,key TEXT NOT NULL,digest TEXT NOT NULL,result"
                " TEXT NOT NULL,PRIMARY KEY(application,scope,key))"
            )
            tx.execute(
                "INSERT INTO managed_meta(application,secret) VALUES(?,?) ON "
                "CONFLICT(application) DO NOTHING",
                (application, secrets.token_hex(32)),
            )
            tx.execute(
                "INSERT INTO managed_control(application,body) VALUES(?,?) ON "
                "CONFLICT(application) DO NOTHING",
                (application, canonical({"accepting": True, "draining_revisions": []})),
            )
            self.cursor_secret = tx.execute(
                "SELECT secret FROM managed_meta WHERE application=?", (application,)
            ).fetchone()["secret"]

    @contextlib.contextmanager
    def session_gate(self, sid: str) -> Iterator[None]:
        """Order frame writes and deletion across processes without holding the app lock."""
        identity = hashlib.sha256((self.application + ":stream:" + sid).encode()).digest()
        if self.sqlite:
            import fcntl

            path = self.url[len("sqlite:///") :] + ".stream-gate"
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise ManagedError(
                                503, "stream_gate_busy", "Try the operation again"
                            ) from None
                        time.sleep(0.01)
                yield
            finally:
                os.close(descriptor)
        else:
            import psycopg

            options = self.pg_options
            with psycopg.connect(self.url, autocommit=True, connect_timeout=10, **options) as db:
                key = int.from_bytes(identity[:8], "big", signed=True)
                db.execute("SELECT pg_advisory_lock(%s)", (key,))
                try:
                    yield
                finally:
                    db.execute("SELECT pg_advisory_unlock(%s)", (key,))

    @contextlib.contextmanager
    def transaction(self, *, initialize: bool = False) -> Iterator[Transaction]:
        """Serialize application mutation across Gateway, Worker and Dispatcher."""
        db: Any = None
        try:
            if self.sqlite:
                db = sqlite3.connect(self.url[len("sqlite:///") :], timeout=30)
                db.row_factory = sqlite3.Row
                db.execute("BEGIN IMMEDIATE")
            else:
                try:
                    import psycopg
                    from psycopg.rows import dict_row
                except ImportError as exc:
                    raise RuntimeError("Install agent-sandbox-client[managed-agents]") from exc
                options = self.pg_options
                db = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10, **options)
                lock = int.from_bytes(
                    hashlib.sha256(self.application.encode()).digest()[:8], "big", signed=True
                )
                db.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
            transaction = Transaction(db, self.sqlite, self.application)
            if not initialize:
                actual = transaction.execute(
                    "SELECT state_id FROM managed_identity WHERE application=?",
                    (self.application,),
                ).fetchone()
                if actual is None or actual["state_id"] != self.state_instance_id:
                    raise ManagedError(
                        503, "state_identity_changed", "The deployment state identity changed"
                    )
            yield transaction
            db.commit()
        except BaseException:
            if db is not None:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()
