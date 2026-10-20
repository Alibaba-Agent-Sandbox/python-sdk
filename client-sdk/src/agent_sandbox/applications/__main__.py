"""Explicit HTTP application entrypoint for local and FC custom-container roles."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys

from .http import make_server
from .runtime import ApplicationRuntime


def main() -> None:
    """Serve one deployment role or execute a finite local invocation from stdin."""
    parser = argparse.ArgumentParser(description="Agent Sandbox application control plane")
    parser.add_argument("role", choices=("gateway", "worker", "dispatcher"))
    parser.add_argument("--once", action="store_true", help="Read one JSON invocation from stdin")
    args = parser.parse_args()
    target = os.getenv("ABX_APP_FACTORY", "agent_sandbox.applications.config:default_factory")
    module, separator, function = target.partition(":")
    if not separator:
        parser.error("ABX_APP_FACTORY must name a trusted module:function")
    runtime = getattr(importlib.import_module(module), function)()
    if not isinstance(runtime, ApplicationRuntime):
        parser.error("Application factory must return ApplicationRuntime")
    if args.once:
        if args.role == "gateway":
            parser.error("--once requires worker or dispatcher")
        payload = json.loads(sys.stdin.buffer.read(262145))
        result = (
            {"claimed": asyncio.run(runtime.work(payload["runId"]))}
            if args.role == "worker"
            else {"dispatched": runtime.dispatch(limit=payload.get("limit", 20))}
        )
        print(json.dumps(result))
        return
    server = make_server(
        runtime,
        mode=args.role,
        host=os.getenv("ABX_APP_BIND", "0.0.0.0"),
        port=int(os.getenv("ABX_APP_PORT", "9000")),
        internal_token=os.getenv("ABX_APP_INTERNAL_TOKEN", ""),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
