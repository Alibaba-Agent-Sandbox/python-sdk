# ruff: noqa: E501, N812
"""``Sandbox`` against the installed reference plugin, plus default-path guarantees."""

from __future__ import annotations

import pytest

from agent_sandbox import ProviderSandbox as Sandbox
from agent_sandbox.models import errors as E
from agent_sandbox.providers import registry, store


async def _create(**kw):
    return await Sandbox.create(provider="local-process", **kw)


async def test_create_run_files_kill(local_process):
    sb = await _create(metadata={"k": "v"}, envs={"A": "1"})
    try:
        assert sb.provider == "local-process"
        assert sb.id.startswith("lp-")
        res = await sb.commands.run("echo hello")
        assert res.exit_code == 0 and res.stdout.strip() == "hello"
        failing = await sb.commands.run("sh -c 'exit 3'")
        assert failing.exit_code == 3
        await sb.files.write("/dir/a.txt", "payload")
        assert await sb.files.read("/dir/a.txt") == "payload"
        names = [f.name for f in await sb.files.list("/dir")]
        assert names == ["a.txt"]
        assert (await sb.files.exists("/dir/a.txt")) is True
        await sb.files.remove("/dir/a.txt")
        assert (await sb.files.exists("/dir/a.txt")) is False
    finally:
        await sb.kill()


async def test_streaming_commands(local_process):
    sb = await _create()
    try:
        stream = await sb.commands.run("sh -c 'echo one; echo two'", background=True)
        chunks = [c async for c in stream]
        text = "".join(c.data for c in chunks if getattr(c, "data", None))
        assert "one" in text and "two" in text
    finally:
        await sb.kill()


async def test_connect_list_and_kill_by_id(local_process):
    sb = await _create()
    other = await Sandbox.connect(sb.id, provider="local-process")
    assert other.id == sb.id and other.provider == "local-process"
    listed = await Sandbox.list(provider="local-process")
    assert sb.id in {i.sandbox_id for i in listed}
    await Sandbox.kill_by_id(sb.id, provider="local-process")
    with pytest.raises(E.SandboxNotFoundError) as exc:
        await Sandbox.connect(sb.id, provider="local-process")
    assert exc.value.code == "E2009"
    await other.close()


async def test_qualified_sandbox_reference(local_process):
    sb = await _create()
    try:
        again = await Sandbox.connect(f"local-process:{sb.id}")
        assert again.provider == "local-process"
        with pytest.raises(E.ProviderMismatchError) as exc:
            await Sandbox.connect(f"local-process:{sb.id}", provider="alicloud-express")
        assert exc.value.code == "E8030"
    finally:
        await sb.kill()


async def test_unsupported_features_raise_e8004(local_process):
    sb = await _create()
    try:
        for call in (
            lambda: sb.pause(),
            lambda: sb.run_code("1 + 1"),
            lambda: sb.files.watch("/"),
            lambda: sb.list_commands(),
            lambda: sb.run("anything"),
        ):
            with pytest.raises(E.ProviderFeatureNotSupportedError) as exc:
                await call()
            assert exc.value.code == "E8004"
            assert isinstance(exc.value, E.CapabilityNotSupportedError)
            assert exc.value.provider == "local-process"
    finally:
        await sb.kill()


async def test_set_timeout_supported(local_process):
    sb = await _create()
    try:
        await sb.set_timeout(120)
    finally:
        await sb.kill()


async def test_capabilities_follow_the_declared_features(local_process):
    sb = await _create()
    try:
        assert sb.capabilities == frozenset({"shell", "files"})
        assert sb.info.region == ""
    finally:
        await sb.kill()


async def test_unknown_provider_is_typed(iso):
    with pytest.raises(E.ProviderNotFoundError) as exc:
        await Sandbox.create(provider="nothing-here")
    assert exc.value.code == "E8001"


async def test_unknown_option_is_typed(local_process):
    with pytest.raises(E.ProviderConfigError):
        await Sandbox.create(provider="local-process", provider_options={"nope": 1})


async def test_default_provider_from_config_and_env(local_process, monkeypatch):
    from agent_sandbox.providers import settings

    settings.set_default_provider("local-process")
    sb = await Sandbox.create()
    try:
        assert sb.provider == "local-process"
    finally:
        await sb.kill()
    settings.set_default_provider(None)
    monkeypatch.setenv("ABX_PROVIDER", "local-process")
    sb = await Sandbox.create()
    try:
        assert sb.provider == "local-process"
    finally:
        await sb.kill()


async def test_explicit_provider_beats_ambient_default(local_process, monkeypatch):
    monkeypatch.setenv("ABX_PROVIDER", "local-process")
    from agent_sandbox.api import sandbox as sandbox_mod

    prov, _ = sandbox_mod._select_provider("alicloud-express")
    assert prov is None  # built-in path


async def test_tampered_plugin_refuses_to_start(local_process):
    (store.provider_dir("local-process") / "provider.py").write_text("print('evil')\n")
    with pytest.raises(E.ProviderIntegrityError):
        await _create()


async def test_missing_required_config_is_a_config_error(iso, tmp_path):
    from agent_sandbox.providers import installer
    from tests.test_providers.helpers import write_plugin

    src = write_plugin(
        tmp_path / "src",
        extra='[config.fields.api_token]\ntype = "string"\nsecret = true\ncredential = true\nrequired = true\n',
    )
    installer.install(str(src), yes=True)
    with pytest.raises(E.InvalidCredentialsError) as exc:
        await Sandbox.create(provider="demo-prov")
    assert "ABX_DEMO_PROV_API_TOKEN" in str(exc.value)


async def test_python_provider_object(iso):
    from agent_sandbox.providers import Provider, ProviderInfra

    class Fake(Provider):
        id = "fake-py"
        kind = "python"
        features = frozenset({"sandbox.lifecycle"})

        async def build_infra(self, config):
            from agent_sandbox.models.sandbox import SandboxInfo

            class Proto:
                async def create(self, cfg, *, request_timeout=None):
                    return SandboxInfo(sandbox_id="fake-1", template=cfg.template)

                async def kill(self, sandbox_id):
                    self.killed = sandbox_id

            self.proto = Proto()
            return ProviderInfra(
                config=config, auth=None, http_client=None, sandbox_protocol=self.proto
            )

    fake = Fake()
    sb = await Sandbox.create(provider=fake)
    assert sb.id == "fake-1" and sb.provider == "fake-py"
    await sb.kill()
    assert fake.proto.killed == "fake-1"
    assert registry.get_provider("fake-py") is fake


async def test_builtin_default_path_is_untouched(iso, monkeypatch):
    """No provider named anywhere: the original build path (auth + http + SandboxProtocol) is used."""
    import agent_sandbox.api.sandbox as mod

    built = {}

    class FakeProto:
        def __init__(self, http):
            built["http"] = http

        async def create(self, cfg, *, request_timeout=None):
            from agent_sandbox.models.sandbox import SandboxInfo

            return SandboxInfo(sandbox_id="sb-1", template=cfg.template, envd_url="https://x")

    monkeypatch.setattr(mod, "SandboxProtocol", FakeProto)
    sb = await Sandbox.create(api_key="k", api_url="https://api.example")
    assert sb.provider == "alicloud-express"
    assert built["http"] is not None
    await built["http"].close()


async def test_contract_kit_passes_for_reference_plugin(local_process):
    """Run the shipped contract tests against the reference plugin."""
    from agent_sandbox.providers.testing import ProviderContractTests

    class Suite(ProviderContractTests):
        provider_id = "local-process"

    suite = Suite()
    import asyncio

    loop = asyncio.get_running_loop()

    def run_all():
        import inspect

        for name in (
            "test_declared_features_are_known",
            "test_lifecycle",
            "test_exec_run",
            "test_files_roundtrip",
            "test_undeclared_feature_fails_with_e8004",
        ):
            method = getattr(suite, name)
            args = ["local-process", {}][: len(inspect.signature(method).parameters)]
            method(*args)

    await loop.run_in_executor(None, run_all)
