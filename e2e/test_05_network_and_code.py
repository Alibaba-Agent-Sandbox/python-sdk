"""Port URLs, in-sandbox HTTP services, and code execution."""

from __future__ import annotations

import httpx
import pytest

import e2e_helpers as H


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


def test_run_code_python_returns_stdout(run, code_sandbox):  # type: ignore[no-untyped-def]
    result = run(code_sandbox.run_code("print('hi')"))
    assert result.exit_code == 0
    assert result.stdout == "hi\n"
    assert result.success


@pytest.mark.known_issue
@pytest.mark.xfail(
    strict=True,
    reason="KI-009 (platform): the Jupyter code-interpreter service answers HTTP 404 on this cloud, so "
    "run_code falls back to a shell and the value of a trailing expression is not returned",
)
def test_run_code_returns_last_expression_value(run, code_sandbox):  # type: ignore[no-untyped-def]
    result = run(code_sandbox.run_code("21 * 2"))
    assert result.text.strip() == "42"


def test_run_code_reports_exceptions(run, code_sandbox):  # type: ignore[no-untyped-def]
    result = run(code_sandbox.run_code("1/0"))
    assert result.exit_code != 0 or "ZeroDivisionError" in result.stderr
    assert "ZeroDivisionError" in result.stderr


def test_run_code_state_is_not_shared_between_shell_runs(run, code_sandbox):  # type: ignore[no-untyped-def]
    run(code_sandbox.run_code("e2e_value = 5"))
    again = run(code_sandbox.run_code("print('e2e_value' in dir())"))
    assert again.exit_code == 0


def test_run_code_streams_callbacks(run, code_sandbox):  # type: ignore[no-untyped-def]
    seen: list[str] = []
    run(code_sandbox.run_code("print('cb-line')", on_stdout=seen.append))
    assert any("cb-line" in s for s in seen)


@pytest.mark.parametrize("language", ["python", "bash"])
def test_run_code_languages(run, code_sandbox, language):  # type: ignore[no-untyped-def]
    code = "print(1+1)" if language == "python" else "echo $((1+1))"
    result = run(code_sandbox.run_code(code, language=language))
    assert result.exit_code == 0
    assert "2" in result.stdout
