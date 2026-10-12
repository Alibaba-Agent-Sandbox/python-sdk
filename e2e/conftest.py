"""Fixtures for the real-cloud E2E suite.

Guarantees:

* every sandbox/template a test creates is tagged ``metadata e2e=<run id>`` and tracked;
* the session finalizer deletes everything tracked, then sweeps by tag, even when tests fail;
* secrets are masked in any report text pytest produces;
* with missing credentials every test is skipped with an explicit message.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import e2e_helpers as H  # noqa: E402

H.load_env()


def pytest_configure(config: pytest.Config) -> None:
    for line in (
        "e2e: runs against the real cloud",
        "e2e_docker: needs Docker + ACR",
        "e2e_slow: slow test",
        "known_issue: strict xfail for a recorded product bug",
    ):
        config.addinivalue_line("markers", line)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    missing = H.missing_env(H.REQUIRED_ENV)
    docker_missing_env = H.missing_env(H.DOCKER_ENV)
    docker_reason = None
    if any("e2e_docker" in i.keywords for i in items):
        docker_reason = H.docker_unavailable_reason()
    for item in items:
        item.add_marker(pytest.mark.e2e)
        if missing:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"E2E skipped: missing credentials {missing}; fill python-sdk/.env "
                    "(see .env.example) or export them"
                )
            )
            continue
        if "e2e_docker" in item.keywords:
            if docker_missing_env:
                item.add_marker(
                    pytest.mark.skip(reason=f"e2e_docker skipped: missing env {docker_missing_env}")
                )
            elif docker_reason:
                item.add_marker(pytest.mark.skip(reason=f"e2e_docker skipped: {docker_reason}"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):  # type: ignore[no-untyped-def]
    outcome = yield
    report = outcome.get_result()
    if report.longrepr is not None and report.failed:
        report.longrepr = H.mask(str(report.longrepr))
    report.sections = [(name, H.mask(content)) for name, content in report.sections]


# --------------------------------------------------------------------------- core fixtures


@pytest.fixture(scope="session")
def run_id() -> str:
    return H.RUN_ID


@pytest.fixture(scope="session")
def loop():  # type: ignore[no-untyped-def]
    lp = asyncio.new_event_loop()
    asyncio.set_event_loop(lp)
    yield lp
    lp.run_until_complete(lp.shutdown_asyncgens())
    lp.close()


@pytest.fixture(scope="session")
def run(loop):  # type: ignore[no-untyped-def]
    def _run(coro):  # type: ignore[no-untyped-def]
        return loop.run_until_complete(coro)

    return _run


async def _kill_quietly(sandbox_id: str) -> str:
    from easy_sandbox.api.sandbox import Sandbox

    try:
        await Sandbox.kill_by_id(sandbox_id)
        return f"killed {sandbox_id}"
    except Exception as exc:  # noqa: BLE001
        return f"kill {sandbox_id} failed: {type(exc).__name__}: {H.mask(str(exc))[:120]}"


async def _sweep_by_tag() -> list[str]:
    from easy_sandbox.api.sandbox import Sandbox

    notes: list[str] = []
    for info in await Sandbox.list(limit=200):
        if (info.metadata or {}).get(H.TAG_KEY) == H.RUN_ID:
            notes.append(await _kill_quietly(info.sandbox_id))
    return notes


@pytest.fixture(scope="session")
def tracker(loop, request):  # type: ignore[no-untyped-def]
    tr = H.Tracker()

    def _finalize() -> None:
        if H.missing_env(H.REQUIRED_ENV):
            return
        for sid in list(tr.sandbox_ids):
            tr.cleanup_log.append(loop.run_until_complete(_kill_quietly(sid)))
        try:
            tr.cleanup_log.extend(loop.run_until_complete(_sweep_by_tag()))
        except Exception as exc:  # noqa: BLE001
            tr.cleanup_log.append(f"sweep failed: {type(exc).__name__}: {H.mask(str(exc))[:120]}")
        _delete_templates(tr)
        _remove_local_images(tr)
        leaked = _leaked()
        print(
            f"\n[e2e cleanup] run={H.RUN_ID} sandboxes_tracked={len(tr.sandbox_ids)} "
            f"templates_tracked={len(tr.template_ids)} leaked_after_cleanup={len(leaked)}"
        )
        if leaked:
            print("[e2e cleanup] LEAKED:", ", ".join(leaked))

    def _leaked() -> list[str]:
        from easy_sandbox.api.sandbox import Sandbox

        try:
            infos = loop.run_until_complete(Sandbox.list(limit=200))
        except Exception:  # noqa: BLE001
            return []
        return [i.sandbox_id for i in infos if (i.metadata or {}).get(H.TAG_KEY) == H.RUN_ID]

    request.addfinalizer(_finalize)
    return tr


def _delete_templates(tr: H.Tracker) -> None:
    import os

    for tid in tr.template_ids:
        try:
            from easy_sandbox.api.template import TemplateManager
            from easy_sandbox.transport.auth import create_auth_provider
            from easy_sandbox.transport.config import load_config
            from easy_sandbox.transport.http import HttpClient

            async def _del(template_id: str = tid) -> None:
                cfg = load_config()
                http = HttpClient(cfg, create_auth_provider(api_key=cfg.api_key))
                try:
                    await TemplateManager(http).delete(template_id)
                finally:
                    await http.close()

            asyncio.new_event_loop().run_until_complete(_del())
            tr.cleanup_log.append(f"deleted template {tid}")
        except Exception as exc:  # noqa: BLE001
            tr.cleanup_log.append(f"delete template {tid} failed: {type(exc).__name__}: {H.mask(str(exc))[:120]}")
    _ = os


def _remove_local_images(tr: H.Tracker) -> None:
    prefix = H.docker_cmd()
    if not prefix:
        return
    import subprocess

    for ref in tr.local_images:
        subprocess.run([*prefix, "rmi", "-f", ref], capture_output=True, timeout=60)


# --------------------------------------------------------------------------- sandbox factories


async def create_tracked(tracker: H.Tracker, template: str, test_name: str = "", **kwargs: Any):  # type: ignore[no-untyped-def]
    from easy_sandbox.api.sandbox import Sandbox

    metadata = H.tag_metadata(test_name)
    metadata.update(kwargs.pop("metadata", {}) or {})
    kwargs.setdefault("timeout", H.SANDBOX_TTL)
    sandbox = await Sandbox.create(template=template, metadata=metadata, **kwargs)
    tracker.sandbox(sandbox.id)
    return sandbox


async def wait_envd_ready(sandbox: Any, timeout: float = 45.0) -> None:
    """envd needs a moment after create (known eventual operation)."""

    async def _probe() -> bool:
        await sandbox.commands.list()
        return True

    await H.eventually_async(_probe, timeout=timeout, interval=1.5, what="envd to accept requests")


@pytest.fixture()
def sandbox_factory(run, tracker, request):  # type: ignore[no-untyped-def]
    """Create tagged sandboxes inside one test; they are always killed on teardown."""
    made: list[Any] = []

    def _make(template: str = H.OFFICIAL_BASE, **kwargs: Any):  # type: ignore[no-untyped-def]
        sb = run(create_tracked(tracker, template, request.node.name, **kwargs))
        made.append(sb)
        run(wait_envd_ready(sb))
        return sb

    yield _make
    for sb in made:
        run(_kill_quietly(sb.id))


def _module_sandbox(run, tracker, request, template: str, **kwargs):  # type: ignore[no-untyped-def]
    sb = run(create_tracked(tracker, template, request.module.__name__, **kwargs))
    run(wait_envd_ready(sb))
    yield sb
    run(_kill_quietly(sb.id))


@pytest.fixture(scope="module")
def base_sandbox(run, tracker, request):  # type: ignore[no-untyped-def]
    yield from _module_sandbox(run, tracker, request, H.OFFICIAL_BASE, timeout=600)


@pytest.fixture(scope="module")
def code_sandbox(run, tracker, request):  # type: ignore[no-untyped-def]
    yield from _module_sandbox(run, tracker, request, H.OFFICIAL_CODE, timeout=600)


@pytest.fixture(scope="module")
def server_sandbox(run, tracker, request):  # type: ignore[no-untyped-def]
    """Official ``python-hello`` template (ships easy-sandbox-server); the server is started on demand."""
    sb = run(create_tracked(tracker, H.SERVER_TEMPLATE, request.module.__name__, timeout=600))
    run(wait_envd_ready(sb))
    yield sb
    run(_kill_quietly(sb.id))


@pytest.fixture()
def workdir(run):  # type: ignore[no-untyped-def]
    """Hand out per-test remote directories so tests sharing a sandbox stay independent."""

    def _make(sandbox: Any) -> str:
        path = H.unique_dir()
        run(sandbox.files.make_dir(path))
        return path

    return _make


@pytest.fixture()
def local_tmp():  # type: ignore[no-untyped-def]
    with tempfile.TemporaryDirectory(prefix="e2e-local-") as d:
        yield Path(d)


class ServerHandle:
    """HTTP client for the in-sandbox easy-sandbox-server reached through the port gateway."""

    def __init__(self, sandbox: Any, port: int = 9000) -> None:
        self.sandbox = sandbox
        self.port = port
        self.base = sandbox.network.get_url(port)
        self.headers = sandbox.network.get_access_headers()

    def request(self, method: str, path: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        import httpx

        return httpx.request(
            method, self.base + path, headers=self.headers, timeout=kwargs.pop("timeout", 30), **kwargs
        )

    def get(self, path: str, **kw: Any):  # type: ignore[no-untyped-def]
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any):  # type: ignore[no-untyped-def]
        return self.request("POST", path, **kw)


@pytest.fixture(scope="module")
def server(run, server_sandbox):  # type: ignore[no-untyped-def]
    """Start ``python3 /app/commands.py`` (the python-hello server) and wait until it serves routes.

    ``/health`` is answered by the gateway even when nothing listens on the port, so readiness is
    probed with ``/commands`` which only the real server serves.
    """
    run(
        server_sandbox.commands.run(
            "nohup python3 /app/commands.py >/tmp/e2e-server.log 2>&1 &", timeout=30
        )
    )
    handle = ServerHandle(server_sandbox)

    def _ready() -> bool:
        return handle.get("/commands").status_code == 200

    H.eventually(_ready, timeout=60, interval=2, what="easy-sandbox-server to serve /commands")
    return handle
