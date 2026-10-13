"""Platform control plane: auth, template catalogue, sandbox listing, error mapping."""

from __future__ import annotations

import pytest

import e2e_helpers as H


def test_list_sandboxes_returns_sandbox_infos(run):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    infos = run(Sandbox.list(limit=50))
    assert isinstance(infos, list)
    for info in infos:
        assert info.sandbox_id.startswith("sbx-")


def test_wrong_api_key_is_rejected(run):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox

    with pytest.raises(Exception) as err:  # noqa: PT011
        run(Sandbox.list(api_key="e2e-invalid-key-0000000000000000"))
    assert "401" in str(err.value) or "uthenticat" in str(err.value)


def test_wrong_api_key_raises_authentication_error(run):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox
    from agent_sandbox.models.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        run(Sandbox.list(api_key="e2e-invalid-key-0000000000000000"))


def test_create_with_unknown_template_fails_cleanly(run):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox
    from agent_sandbox.models.errors import SandboxError

    with pytest.raises(SandboxError):
        run(
            Sandbox.create(
                template="e2e-template-that-does-not-exist-zz",
                timeout=60,
                metadata=H.tag_metadata("unknown-template"),
            )
        )


def test_kill_unknown_sandbox_is_not_fatal(run):  # type: ignore[no-untyped-def]
    """Killing an id that does not exist must not hang; the platform answers 404 or 2xx."""
    from agent_sandbox.api.sandbox import Sandbox

    try:
        run(Sandbox.kill_by_id("sbx-00000000-0000-0000-0000-000000000000"))
    except Exception as exc:  # noqa: BLE001
        assert "404" in str(exc) or "not found" in str(exc).lower()


def test_connect_to_missing_sandbox_raises_sdk_error(run):  # type: ignore[no-untyped-def]
    from agent_sandbox.api.sandbox import Sandbox
    from agent_sandbox.models.errors import SandboxNotFoundError

    with pytest.raises(SandboxNotFoundError):
        run(Sandbox.connect("sbx-00000000-0000-0000-0000-000000000000"))
