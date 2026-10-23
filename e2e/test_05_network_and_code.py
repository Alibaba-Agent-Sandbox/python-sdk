"""Port URLs, in-sandbox HTTP services, and code execution."""

from __future__ import annotations

import e2e_helpers as H
import httpx
import pytest


def test_port_url_format_is_computed_locally(base_sandbox):  # type: ignore[no-untyped-def]
    host = base_sandbox.network.get_host(8080)
    assert host == f"8080-{base_sandbox.id}.{base_sandbox._domain}"
    assert base_sandbox.network.get_url(8080) == f"https://{host}"


def test_service_started_in_sandbox_is_reachable_through_the_gateway(  # type: ignore[no-untyped-def]
    run, base_sandbox, workdir
):
    d = workdir(base_sandbox)
    run(base_sandbox.files.write(f"{d}/index.txt", "served-from-sandbox"))
    port = 18080
    run(
        base_sandbox.commands.run(
            f"nohup python3 -m http.server {port} --directory {d} >/tmp/http-{port}.log 2>&1 &"
        )
    )
    url = base_sandbox.network.get_url(port) + "/index.txt"
    headers = base_sandbox.network.get_access_headers()

    def _fetch() -> str:
        r = httpx.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return r.text

    assert H.eventually(_fetch, timeout=45, interval=2, what="HTTP service through gateway") == (
        "served-from-sandbox"
    )


def test_port_without_listener_is_not_a_success(base_sandbox):  # type: ignore[no-untyped-def]
    url = base_sandbox.network.get_url(18999)
    r = httpx.get(url, headers=base_sandbox.network.get_access_headers(), timeout=30)
    assert r.status_code >= 400


@pytest.mark.parametrize("mode", ["stateless", "default-context"])
def test_project_interpreter_is_explicitly_unimplemented(run, base_sandbox, mode):
    """No guessed RPC or shell execution is used as an interpreter substitute."""
    from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

    expected = "code.execute" if mode == "stateless" else "code.default-context.execute"
    with pytest.raises(ProviderFeatureNotSupportedError, match=expected):
        run(base_sandbox.run_code("raise RuntimeError('must not execute')", mode=mode))


def test_project_context_not_inferred_from_platform_runtime(run, base_sandbox):
    from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

    with pytest.raises(ProviderFeatureNotSupportedError, match="code.context.create"):
        run(base_sandbox.code.create_context())


def test_project_stream_not_inferred_from_buffered_shell(run, base_sandbox):
    from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

    seen = []
    with pytest.raises(ProviderFeatureNotSupportedError):
        run(base_sandbox.run_code("print('must not execute')", on_stdout=seen.append))
    assert seen == []
