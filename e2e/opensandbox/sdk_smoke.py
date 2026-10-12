#!/usr/bin/env python3
"""Smoke test of the official `opensandbox` Python SDK against a local server.

Reference/oracle only: the provider plugin itself uses stdlib REST (see the design doc).
Needs `pip install opensandbox`. Honors OPENSANDBOX_DOMAIN / OPENSANDBOX_API_KEY /
OPENSANDBOX_TEST_IMAGE (defaults match local-up.sh).
"""

import asyncio
import os
from datetime import timedelta

from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig


async def main():
    cfg = ConnectionConfig(
        domain=os.environ.get("OPENSANDBOX_DOMAIN", "127.0.0.1:8080"),
        api_key=os.environ.get("OPENSANDBOX_API_KEY", "local-dev-key"),
        protocol="http",
        use_server_proxy=False,
    )
    image = os.environ.get("OPENSANDBOX_TEST_IMAGE", "python:3.12-slim")
    sb = await Sandbox.create(
        image,
        connection_config=cfg,
        timeout=timedelta(minutes=10),
        entrypoint=["tail", "-f", "/dev/null"],
    )
    try:
        r = await sb.commands.run("echo hi && uname -a")
        print(
            "stdout:",
            [m.text for m in r.logs.stdout],
            "exit:",
            getattr(r, "exit_code", None),
            "id:",
            r.id,
        )
        info = await sb.get_info()
        print("state:", info.status.state)
        ep = await sb.get_endpoint(8000)
        print("endpoint:", ep.endpoint, ep.headers)
    finally:
        await sb.kill()
        await sb.close()


asyncio.run(main())
