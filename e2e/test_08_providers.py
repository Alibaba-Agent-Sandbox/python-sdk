"""Live end-to-end calls for Express and the installed catalog providers.

These tests dial a real backend. They are not collected by unit CI.
A backend that is not configured is skipped after a local refusal check
that proves the Express credential is not sent in its place.
"""

from __future__ import annotations

import provider_live as live
import pytest

pytestmark = pytest.mark.provider_live

_OPEN_PASS = {
    "sandbox.lifecycle",
    "sandbox.connect",
    "sandbox.reconnect",
    "sandbox.list",
    "sandbox.timeout",
    "exec.run",
    "exec.user",
    "exec.stream",
    "files.rw",
    "ports.url",
    "process.manage",
    "pty",
    "sandbox.pause",
    "sandbox.kill",
    "sandbox.kill_again",
}
_OPEN_REFUSED = {
    "code.execute",
    "code.default-context.execute",
    "files.watch",
    "files.transfer",
    "sessions",
}

_EXPRESS_PASS = {
    "sandbox.lifecycle",
    "sandbox.connect",
    "sandbox.reconnect",
    "sandbox.list",
    "sandbox.timeout",
    "exec.run",
    "exec.stream",
    "files.rw",
    "ports.url",
    "process.manage",
    "files.watch",
    "files.transfer",
    "sandbox.kill",
    "sandbox.kill_again",
}
_CLI_PASS = {
    "sandbox.lifecycle",
    "sandbox.list",
    "exec.run",
    "exec.stream",
    "files.rw",
    "sandbox.kill",
    "sandbox.kill_again",
}


def test_opensandbox_live() -> None:
    reason = live.opensandbox_ready()
    if reason:
        pytest.skip(reason)
    report = live.run(live.exercise("opensandbox", template="base"))
    live.assert_report(report, expect_pass=_OPEN_PASS, expect_refused=_OPEN_REFUSED)


def test_alicloud_express_sdk_live() -> None:
    reason = live.express_ready()
    if reason:
        pytest.skip(reason)
    report = live.run(live.exercise("alicloud-express", template="base"))
    live.assert_report(
        report,
        expect_pass=_EXPRESS_PASS,
        expect_refused={"code.execute", "code.default-context.execute"},
    )
    # The base template has no in-sandbox command server. Pause is refused
    # by the adapter before a platform call, while the envd
    # terminal is not implemented by this project adapter. StartRequest.stdin
    # is false, and this envd still keeps the stdin pipe, so cat waits.
    assert live.row(report, "sessions").status == "blocked"
    assert live.row(report, "sandbox.pause").status == "refused"
    assert "E8004" in live.row(report, "sandbox.pause").detail
    assert live.row(report, "pty").status == "fail"
    assert live.row(report, "exec.stdin").status == "fail"
    assert "did not finish" in live.row(report, "exec.stdin").detail


def test_alicloud_express_cli_live() -> None:
    reason = live.express_ready()
    if reason:
        pytest.skip(reason)
    report = live.cli_express()
    live.assert_report(report, expect_pass=_CLI_PASS, expect_refused=set())


def test_cubesandbox_live() -> None:
    reason = live.cube_ready()
    if reason:
        pytest.skip(reason)
    report = live.run(live.exercise("cubesandbox", template="base"))
    live.assert_report(
        report,
        expect_pass={
            "code.default-context.execute",
            "sandbox.lifecycle",
            "sandbox.connect",
            "sandbox.reconnect",
            "sandbox.list",
            "sandbox.timeout",
            "sandbox.pause",
            "exec.run",
            "exec.stream",
            "files.rw",
            "ports.url",
            "sandbox.kill",
            "sandbox.kill_again",
        },
        expect_refused={
            "code.execute",
            "process.manage",
            "pty",
            "files.watch",
            "files.transfer",
            "sessions",
        },
    )


def test_e2b_live() -> None:
    reason = live.e2b_ready()
    if reason:
        pytest.skip(reason)
    report = live.run(live.exercise("e2b", template="base"))
    live.assert_report(
        report,
        expect_pass={
            "sandbox.lifecycle",
            "sandbox.connect",
            "sandbox.reconnect",
            "sandbox.list",
            "sandbox.timeout",
            "sandbox.pause",
            "exec.run",
            "exec.stream",
            "process.manage",
            "files.rw",
            "files.watch",
            "ports.url",
            "sandbox.kill",
            "sandbox.kill_again",
        },
        expect_refused={
            "code.execute",
            "code.default-context.execute",
            "files.transfer",
            "sessions",
            "pty",
        },
    )


def test_alicloud_container_live() -> None:
    reason = live.container_ready()
    if reason:
        pytest.skip(reason)
    report = live.run(live.exercise("alicloud-container", template="code-interpreter"))
    live.assert_report(
        report,
        expect_pass={
            "code.default-context.execute",
            "sandbox.lifecycle",
            "sandbox.connect",
            "sandbox.reconnect",
            "sandbox.list",
            "sandbox.timeout",
            "exec.run",
            "exec.stream",
            "process.manage",
            "files.rw",
            "ports.url",
            "sandbox.pause",
            "sandbox.kill",
            "sandbox.kill_again",
        },
        expect_refused={"code.execute", "pty", "files.watch", "files.transfer", "sessions"},
    )


def test_e2b_refuses_without_its_own_key() -> None:
    """The Express key must not be forwarded when the E2B key is absent."""
    if live.e2b_ready() == "":
        pytest.skip("ABX_ABX_SANDBOX_API_KEY is set; the live test covers this provider")
    from agent_sandbox.models.errors import (
        InvalidAPIKeyError,
        InvalidCredentialsError,
        ProviderNotFoundError,
    )

    if live._installed("e2b"):
        with pytest.raises(ProviderNotFoundError):
            live.run(live._create_only("e2b"))
        return
    with pytest.raises((InvalidAPIKeyError, InvalidCredentialsError)):
        live.run(live._create_only("e2b"))


def test_container_refuses_without_its_own_endpoint() -> None:
    if live.container_ready() == "":
        pytest.skip("container endpoint is set; the live test covers this provider")
    from agent_sandbox.models.errors import (
        InvalidAPIKeyError,
        InvalidCredentialsError,
        ProviderConfigError,
        ProviderNotFoundError,
    )

    if live._installed("alicloud-container"):
        with pytest.raises(ProviderNotFoundError):
            live.run(live._create_only("alicloud-container"))
        return
    with pytest.raises((InvalidAPIKeyError, InvalidCredentialsError, ProviderConfigError)):
        live.run(live._create_only("alicloud-container"))
