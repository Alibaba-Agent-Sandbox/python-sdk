"""Optional real PostgreSQL integration; pgserver is verification tooling only."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from agent_sandbox.applications import Application, ApplicationError, ExecutionResult, Store


@pytest.mark.integration
def test_real_postgres_transactions_locks_and_restart(tmp_path):
    pgserver = pytest.importorskip(
        "pgserver", reason="Optional local PostgreSQL binary is unavailable"
    )
    pytest.importorskip("psycopg")
    server = pgserver.get_server(tmp_path / "postgres", cleanup_mode="stop")
    try:
        url = server.get_uri()
        with ThreadPoolExecutor(4) as pool:
            stores = list(pool.map(lambda _: Store(url), range(4)))
        app = Application(
            "postgres-revision", "external", {"template": "ready"}, max_concurrent_runs=1
        )
        body = {"applicationRevision": app.revision, "input": {"text": "real postgres"}}
        with ThreadPoolExecutor(8) as pool:
            runs = list(
                pool.map(lambda i: stores[i % 4].create("owner", app, "one", body), range(24))
            )
        assert len({run["id"] for run in runs}) == 1
        run_id = runs[0]["id"]
        with ThreadPoolExecutor(8) as pool:
            claims = list(pool.map(lambda i: stores[i % 4].claim(run_id, app), range(24)))
        attempt = next(claim for claim in claims if claim)
        assert sum(claim is not None for claim in claims) == 1
        store = stores[0]
        store.started(run_id, attempt)
        store.emit(run_id, attempt, "output.delta", {"text": "committed"})
        with pytest.raises(ApplicationError, match="new application revision"):
            store.create("owner", replace(app, snapshot={"changed": True}), "two", body)
        store.cancel(run_id, "owner")
        store.finish(run_id, attempt, "succeeded", ExecutionResult("late"))
        restarted = Store(url)
        assert restarted.result(run_id, "owner")["status"] == "cancelled"
        events = restarted.events(run_id, "owner")
        assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
        assert events[-1]["type"] == "run.cancelled"
        assert restarted.next_dispatch() is None
    finally:
        server.cleanup()
