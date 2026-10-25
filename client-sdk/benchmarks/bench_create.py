"""Measure three sandbox creation samples using an installed SDK."""

import asyncio
import os
import sys
import time


async def bench_create() -> None:
    """Report this run's samples; delete each owned sandbox before the next one."""
    from agent_sandbox import ProviderSandbox

    api_key = os.environ.get("ABX_SANDBOX_API_KEY", "")
    if not api_key:
        print("ERROR: ABX_SANDBOX_API_KEY environment variable is required.")
        sys.exit(1)
    api_url = os.environ.get("ABX_SANDBOX_BASE_URL", "https://api.cn-hangzhou.e2b.fc.aliyuncs.com")
    domain = os.environ.get("ABX_SANDBOX_DOMAIN", "cn-hangzhou.e2b.fc.aliyuncs.com")
    times = []

    for i in range(3):
        start = time.perf_counter()
        sandbox = await ProviderSandbox.create(
            template="base",
            provider="alicloud-express",
            timeout=60,
            sandbox_api_key=api_key,
            sandbox_base_url=api_url,
            sandbox_domain=domain,
        )
        try:
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            print(f"  Create #{i + 1}: {elapsed:.3f}s")
        finally:
            try:
                await sandbox.kill()
            finally:
                await sandbox.close()

    print(f"\nCreate sandbox: sample mean={sum(times) / len(times):.3f}s (3 samples)")


if __name__ == "__main__":
    print("=== Sandbox Create Benchmark ===")
    asyncio.run(bench_create())
