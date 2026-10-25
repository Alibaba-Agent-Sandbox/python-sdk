#!/usr/bin/env python3
"""Exercise public SDK capabilities against Alibaba Express.

Install agent-sandbox-client[all], then configure ABX_SANDBOX_API_KEY (and the
endpoint/domain for your region). Run from any directory. This example uses an
existing provider-native template; source-template build/launch is documented in
the CLI guide. No local-registry fallback or simulated cloud result is used.
安装公开 SDK 并配置极速版账号后运行；所有断言失败都会使进程非零退出。
"""

import asyncio
import json

from agent_sandbox import ProviderSandbox
from agent_sandbox.declarative import sandbox
from agent_sandbox.models.errors import SandboxNotFoundError


@sandbox(template="code-interpreter-v1", timeout=120)
def square_sum(values: list[int]) -> int:
    """Execute remotely / 在云端执行。"""
    return sum(value * value for value in values)


async def cloud_capabilities() -> None:
    instance = await ProviderSandbox.create(template="base", timeout=300)
    owned_id = instance.id
    try:
        info = await ProviderSandbox.get_info_by_id(owned_id)
        assert info.sandbox_id == owned_id
        success = await instance.commands.run("python -c 'print(6 * 7)'")
        assert success.exit_code == 0 and success.stdout.strip() == "42"
        failure = await instance.commands.run("python -c 'import sys; sys.exit(7)'")
        assert failure.exit_code == 7
        payload = bytes(range(256))
        await instance.files.write("/tmp/capability.bin", payload)
        assert await instance.files.read_bytes("/tmp/capability.bin") == payload
        await instance.files.write("/tmp/input.json", json.dumps([3, 5, 8]))
        result = await instance.commands.run(
            'python -c "import json; from pathlib import Path; '
            "data=json.loads(Path('/tmp/input.json').read_text()); "
            "Path('/tmp/output.json').write_text(json.dumps({'sum': sum(data)}))\""
        )
        assert result.exit_code == 0
        assert json.loads(await instance.files.read("/tmp/output.json")) == {"sum": 16}
        await instance.files.remove("/tmp/capability.bin")
        assert not await instance.files.exists("/tmp/capability.bin")
        print("PASS: lifecycle, exit status, binary files and JSON workflow")
    finally:
        await instance.kill()
        await instance.close()
    try:
        remaining = await ProviderSandbox.connect(owned_id)
    except SandboxNotFoundError:
        print("PASS: independent cleanup check")
    else:
        await remaining.close()
        raise AssertionError("Owned sandbox still exists after kill")


def main() -> None:
    asyncio.run(cloud_capabilities())
    values = [2, 3, 7, -4]
    assert square_sum(values) == sum(value**2 for value in values)
    print("PASS: declarative remote execution")


if __name__ == "__main__":
    main()
