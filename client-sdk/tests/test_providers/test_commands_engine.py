"""Python -> real Node engine -> provider command contract, without cloud requests.

Set ABX_COMMAND_TEST_BIN to a compatible abx command line to run these tests.
The temporary provider executes in the real engine and owns no external resources.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox.models.errors import ProviderConfigError, ProviderTrustError
from agent_sandbox.providers import commands, engine_client, installer
from tests.iso import iso  # noqa: F401

if TYPE_CHECKING:
    from pathlib import Path

TEST_BIN = os.environ.get("ABX_COMMAND_TEST_BIN")
pytestmark = pytest.mark.skipif(
    not TEST_BIN,
    reason="set ABX_COMMAND_TEST_BIN to a compatible abx engine command",
)


@pytest.fixture
async def real_engine(iso: Any, monkeypatch: pytest.MonkeyPatch):  # noqa: F811
    monkeypatch.setenv("HOME", str(iso.home.parent))
    assert TEST_BIN is not None
    monkeypatch.setenv("ABX_BIN", TEST_BIN)
    yield
    if engine_client.read_record() is not None:
        client = engine_client.EngineClient({"provider": "alicloud-express"})
        try:
            with contextlib.suppress(Exception):
                await client.call("POST", "/v1/shutdown", retry=False)
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_builtin_discovery_through_real_engine(real_engine: Any) -> None:
    descriptors = await commands.list_commands("alicloud-express")
    expected = {
        "volume.create",
        "volume.get",
        "volume.list",
        "volume.update",
        "volume.delete",
        "team.create",
        "team.get",
        "team.list",
        "team.update",
        "team.delete",
        "api-key.create",
        "api-key.get",
        "api-key.list",
        "api-key.update",
        "api-key.reset",
        "api-key.delete",
        "quota.get",
        "quota.list",
        "quota.update",
        "quota.delete",
    }
    assert len(descriptors) == 20
    assert {descriptor["id"] for descriptor in descriptors} == expected
    descriptor = await commands.get_command("alicloud-express", "volume.list")
    assert descriptor["effect"] == "read" and descriptor["idempotent"]
    assert descriptor["input_schema"]["additionalProperties"] is False


@pytest.mark.asyncio
async def test_node_invocation_and_confirmation_through_real_engine(
    real_engine: Any, tmp_path: Path
) -> None:
    source = tmp_path / "plugin"
    source.mkdir()
    schema = (
        '{type="object",properties={message={type="string"}},'
        'required=["message"],additionalProperties=false}'
    )
    entry_template = """
[[commands.entries]]
id = "echo.{effect}"
description = "Echo a value"
description_zh = "返回输入值"
input_schema = {schema}
output_schema = {schema}
effect = "{effect}"
idempotent = true
"""
    entries = "\n".join(
        entry_template.format(effect=effect, schema=schema) for effect in ("read", "write")
    )
    (source / "abx-provider.toml").write_text(
        """
manifest_version = 1
[provider]
id = "engine-command-fixture"
version = "1.0.0"
[runtime]
kind = "node"
entry = "provider.mjs"
[features]
supported = []
[commands]
protocol = "provider-commands/1"
"""
        + entries
    )
    (source / "provider.mjs").write_text("""
export default () => ({
  async buildInfra() {
    return {
      sandbox_protocol: {},
      provider_commands: { async run(commandId, input, signal) {
        if (signal.aborted) throw new Error("unexpected abort");
        return { message: input.message };
      } }
    };
  }
});
""")
    installer.install(str(source), yes=True)
    provider = "engine-command-fixture"
    assert len(await commands.list_commands(provider)) == 2
    assert await commands.run_command(provider, "echo.read", {"message": "read"}) == {
        "message": "read"
    }
    with pytest.raises(ProviderTrustError):
        await commands.run_command(provider, "echo.write", {"message": "write"})
    assert await commands.run_command(
        provider, "echo.write", {"message": "write"}, confirm=True
    ) == {"message": "write"}
    with pytest.raises(ProviderConfigError):
        await commands.run_command(provider, "echo.read", {"message": "read", "extra": True})
