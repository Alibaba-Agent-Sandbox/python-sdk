"""The creation benchmark uses installed public APIs and closes owned resources."""

import importlib.util
from pathlib import Path

import pytest

from agent_sandbox import ProviderSandbox

spec = importlib.util.spec_from_file_location(
    "bench_create", Path(__file__).resolve().parents[1] / "benchmarks/bench_create.py"
)
assert spec and spec.loader
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.parametrize("failure", [None, "second-create", "kill"])
async def test_benchmark_has_bounded_public_calls_and_preserves_cleanup_errors(
    monkeypatch, capsys, failure
):
    events = []
    count = 0
    monkeypatch.setenv("ABX_SANDBOX_API_KEY", "placeholder")
    monkeypatch.setenv("ABX_SANDBOX_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("ABX_SANDBOX_DOMAIN", "example.invalid")

    class OwnedSandbox:
        async def kill(self):
            events.append("kill")
            if failure == "kill":
                raise RuntimeError("owned cleanup failed")

        async def close(self):
            events.append("close")

    async def create(**kwargs):
        nonlocal count
        count += 1
        events.append("create")
        assert kwargs == {
            "template": "base",
            "provider": "alicloud-express",
            "timeout": 60,
            "sandbox_api_key": "placeholder",
            "sandbox_base_url": "https://example.invalid",
            "sandbox_domain": "example.invalid",
        }
        if failure == "second-create" and count == 2:
            raise RuntimeError("creation failed")
        return OwnedSandbox()

    monkeypatch.setattr(ProviderSandbox, "create", create)
    if failure:
        with pytest.raises(RuntimeError, match="creation failed|owned cleanup failed"):
            await benchmark.bench_create()
    else:
        await benchmark.bench_create()
    expected = {
        None: ["create", "kill", "close"] * 3,
        "second-create": ["create", "kill", "close", "create"],
        "kill": ["create", "kill", "close"],
    }
    assert events == expected[failure]
    output = capsys.readouterr().out
    assert "id=" not in output
    assert "p95" not in output.lower()
