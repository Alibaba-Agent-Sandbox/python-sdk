"""Sandbox lifecycle on the real cloud: create / info / list / connect / timeout / kill."""

from __future__ import annotations

import pytest

import e2e_helpers as H


def test_create_info_and_kill(run, sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE, timeout=180)
    assert sb.id.startswith("sbx-")
    assert sb.url.startswith("https://49983-" + sb.id)
    info = run(sb.refresh_info())
    assert info.sandbox_id == sb.id
    assert info.status.value == "running"
    assert info.metadata.get(H.TAG_KEY) == H.RUN_ID
    assert info.started_at is not None and info.end_at is not None
    assert (info.end_at - info.started_at).total_seconds() == pytest.approx(180, abs=30)
    assert run(sb.is_running()) is True

    run(sb.kill())

    def _gone() -> bool:
        return run(_not_running(sb.id))

    H.eventually(_gone, timeout=30, interval=2, what="killed sandbox to stop running")


async def _not_running(sandbox_id: str) -> bool:
    from agent_sandbox.api.sandbox import Sandbox

    infos = await Sandbox.list(limit=200)
    return all(i.sandbox_id != sandbox_id for i in infos)


def test_created_sandbox_appears_in_list_with_metadata(run, sandbox_factory):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    sb = sandbox_factory(H.OFFICIAL_BASE, metadata={"e2e_kind": "list-check"})

    def _find():  # type: ignore[no-untyped-def]
        infos = run(Sandbox.list(limit=200))
        return next((i for i in infos if i.sandbox_id == sb.id), None)

    info = H.eventually(_find, timeout=40, interval=2, what="sandbox in list (eventually consistent)")
    assert info.metadata.get("e2e_kind") == "list-check"
    assert info.metadata.get(H.TAG_KEY) == H.RUN_ID


def test_connect_from_second_handle_shares_state(run, sandbox_factory):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    sb = sandbox_factory(H.OFFICIAL_BASE)
    path = H.unique_dir() + ".txt"
    run(sb.files.write(path, "shared-state"))
    other = run(Sandbox.connect(sb.id))
    try:
        assert other.id == sb.id
        assert run(other.files.read(path)) == "shared-state"
    finally:
        run(other._http_client.close())


def test_envs_at_create_time_reach_processes(run, sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE, envs={"E2E_CREATE_ENV": "from-create"})
    result = run(sb.commands.run("printenv E2E_CREATE_ENV"))
    assert result.exit_code == 0
    assert result.stdout.strip() == "from-create"


def test_set_timeout_extends_the_deadline(run, sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(H.OFFICIAL_BASE, timeout=120)
    before = run(sb.refresh_info()).end_at
    run(sb.set_timeout(600))

    def _extended() -> bool:
        after = run(sb.refresh_info()).end_at
        return after is not None and before is not None and (after - before).total_seconds() > 200

    H.eventually(_extended, timeout=30, interval=2, what="end_at to move after set_timeout")


def test_async_context_manager_kills_on_exit(run, tracker):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    async def _scenario() -> str:
        async with await Sandbox.create(
            template=H.OFFICIAL_BASE, timeout=120, metadata=H.tag_metadata("ctx-manager")
        ) as sb:
            tracker.sandbox(sb.id)
            result = await sb.commands.run("echo inside")
            assert result.stdout.strip() == "inside"
            return sb.id

    sandbox_id = run(_scenario())
    H.eventually(
        lambda: run(_not_running(sandbox_id)), timeout=30, interval=2, what="context-manager kill"
    )


def test_invalid_request_timeout_is_rejected_locally(run):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    with pytest.raises(ValueError):
        run(Sandbox.create(template=H.OFFICIAL_BASE, request_timeout=0))


def test_kill_by_id_is_idempotent(run, sandbox_factory):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    sb = sandbox_factory(H.OFFICIAL_BASE)
    run(Sandbox.kill_by_id(sb.id))
    run(Sandbox.kill_by_id(sb.id))


@pytest.mark.e2e_slow
def test_sandbox_expires_after_its_ttl(run, sandbox_factory):  # type: ignore[no-untyped-def]
    """A sandbox created with a short TTL disappears without an explicit kill."""
    sb = sandbox_factory(H.OFFICIAL_BASE, timeout=45)
    H.eventually(
        lambda: run(_not_running(sb.id)), timeout=150, interval=5, what="TTL expiry of a 45 s sandbox"
    )


def test_background_work_survives_independent_handle_polling(run, sandbox_factory):  # type: ignore[no-untyped-def]
    """Issue35: a live builtin sandbox has no process-local session dependency."""
    from agent_sandbox import Sandbox

    held = sandbox_factory(H.OFFICIAL_BASE, timeout=180)
    path = H.unique_dir() + ".native-poll"
    other = run(Sandbox.connect(held.id))
    try:
        # The worker runs independently; its creation is never replayed by polling.
        started = run(
            held.commands.run(
                f"nohup sh -c 'sleep 4; printf completed > {path}' </dev/null >/dev/null 2>&1 &",
                shell=True,
            )
        )
        assert started.exit_code == 0
        observations = 0

        def _completed():  # type: ignore[no-untyped-def]
            nonlocal observations
            info = run(held.refresh_info())
            assert info.sandbox_id == held.id
            assert info.status.value == "running"
            result = run(other.commands.run(f"cat {path} 2>/dev/null || true", shell=True))
            observations += 1
            return result.stdout == "completed"

        H.eventually(_completed, timeout=30, interval=0.5, what="background worker completion")
        assert observations >= 1
        assert run(held.files.read(path)) == "completed"
        assert run(other.refresh_info()).sandbox_id == held.id
    finally:
        run(other.close())
