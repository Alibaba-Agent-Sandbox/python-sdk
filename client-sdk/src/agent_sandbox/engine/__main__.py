"""Run the provider engine until interrupted: ``python -m agent_sandbox.engine``."""

from __future__ import annotations

import asyncio

from agent_sandbox.engine.client import _harden, _serve, socket_path


def main() -> None:
    path = socket_path()
    created = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    async def _run() -> None:
        server = await _serve(path)
        _harden(path, created_parent=created)
        print(f"provider engine listening on {path}", flush=True)
        await server.wait_for_termination()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
