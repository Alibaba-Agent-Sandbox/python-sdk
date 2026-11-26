"""Create and clean up an OpenSandbox sandbox with a locked Provider runtime."""

import asyncio
import os
import tempfile
import uuid
from pathlib import Path

from agent_sandbox.models.errors import SandboxNotFoundError
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers import ProviderClient, ProviderLock
from agent_sandbox.transport.config import TransportConfig


async def main() -> None:
    lock = ProviderLock.model_validate_json(
        Path(__file__).with_name("provider.lock.json").read_bytes()
    )
    config = TransportConfig(
        provider="opensandbox",
        provider_options={
            "base_url": os.environ["OPENSANDBOX_BASE_URL"],
            "api_key": os.environ.get("OPENSANDBOX_API_KEY"),
        },
    )
    with tempfile.TemporaryDirectory(prefix="opensandbox-cache-") as cache:
        cache_dir = Path(cache)
        async with await ProviderClient.prepare(
            lock,
            config,
            cache_dir=cache_dir,
            download=True,
            required_features=("sandbox.lifecycle", "exec.run", "files.rw"),
        ) as client:
            run_id = f"locked-provider-{uuid.uuid4().hex}"
            sandbox = await client.create(
                SandboxConfig(
                    template=os.environ.get("OPENSANDBOX_TEST_IMAGE", "base"),
                    metadata={"e2e": run_id},
                )
            )
            sandbox_id = sandbox.id
            try:
                result = await sandbox.commands.run("printf expected")
                assert result.stdout == "expected" and result.exit_code == 0
                await sandbox.files.write("/tmp/locked-provider.txt", "verified")
                assert await sandbox.files.read("/tmp/locked-provider.txt") == "verified"
                assert (await client.get(sandbox_id)).sandbox_id == sandbox_id
            finally:
                try:
                    await client.delete(sandbox_id)
                finally:
                    await sandbox.close()

        async with await ProviderClient.prepare(lock, config, cache_dir=cache_dir) as client:
            try:
                await client.get(sandbox_id)
            except SandboxNotFoundError:
                print("Command, files, offline preparation and cleanup confirmed.")
            else:
                raise RuntimeError("The sandbox still exists after deletion.")


if __name__ == "__main__":
    asyncio.run(main())
