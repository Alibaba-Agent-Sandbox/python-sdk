"""AK/SK-only SDK acceptance through the actual CLI engine; own credential and sandboxes only."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

import e2e_helpers as H

pytestmark = pytest.mark.provider_live


def test_managed_key_consent_and_shared_runtime(tmp_path):
    if not all(
        os.environ.get(k)
        for k in ("ALICLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_SECRET", "ABX_BIN")
    ):
        pytest.skip("Requires AccessKeys and the candidate ABX_BIN; no API-key values are printed")
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith(("E2B_", "ABX_")) and key.endswith(("API_KEY", "TOKEN")):
            environment.pop(key)
    environment.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    source = r"""
import asyncio
from agent_sandbox import Sandbox, AsyncSandbox, ProviderSandbox
from agent_sandbox.models.errors import ProviderTrustError, ProviderResourceNotFoundError
from agent_sandbox.providers.alicloud_express import prepare_api_key_sync
from agent_sandbox.providers.commands import run_command

try:
    prepare_api_key_sync()
    raise AssertionError("Missing consent was accepted")
except ProviderTrustError:
    pass
metadata = prepare_api_key_sync(confirm=True)
async def native():
    for client in (AsyncSandbox, ProviderSandbox):
        sandbox = await client.create(template="base", timeout=120)
        try:
            assert (await sandbox.commands.run("echo managed-native")).stdout.strip() == "managed-native"
            await sandbox.files.write("/tmp/managed-native.txt", "verified")
            assert await sandbox.files.read("/tmp/managed-native.txt") == "verified"
        finally:
            await sandbox.kill()
async def cleanup():
    identity = {"api_key_id": metadata["api_key_id"]}
    await run_command("alicloud-express", "api-key.update", {**identity, "status": "inactive"}, confirm=True)
    await run_command("alicloud-express", "api-key.delete", identity, confirm=True)
    try:
        await run_command("alicloud-express", "api-key.get", identity)
    except ProviderResourceNotFoundError:
        return
    raise AssertionError("Owned API key deletion not confirmed")
try:
    sandbox = Sandbox.create(template="base", timeout=120)
    try:
        assert sandbox.commands.run("echo managed-standard").stdout.strip() == "managed-standard"
        sandbox.files.write("/tmp/managed-standard.txt", "verified")
        assert sandbox.files.read("/tmp/managed-standard.txt") == "verified"
    finally:
        sandbox.kill()
    asyncio.run(native())
    print("PASS: SDK explicit preparation; standard/provider create, exec, files and kill")
finally:
    asyncio.run(cleanup())
    print("PASS: owned credential cleanup and absence readback")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", source],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, H.mask(result.stdout + result.stderr)
        assert result.stdout.count("PASS:") == 2
    finally:
        import shlex

        subprocess.run(
            [*shlex.split(environment["ABX_BIN"]), "provider", "engine", "stop"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            timeout=30,
        )
