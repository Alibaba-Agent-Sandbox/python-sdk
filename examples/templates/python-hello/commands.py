"""python-hello — the teaching template for the Server API.

Shows:
- ``@command``: named commands on the server's default registry (``POST /commands/{name}``)
- ``hidden=True``: a command that is callable but not listed by ``GET /commands``
- ``enable_group``: turn an opt-in endpoint group on from code (the built-in file, process and
  system groups are already on)
- ``RouteTable.route()``: one custom HTTP route
- ``registry.freeze()``: no registrations after start-up
"""

from __future__ import annotations

from agent_sandbox.server import (
    CapabilityGroup,
    ServerResponse,
    command,
    default_registry,
    default_table,
    start,
)

table = default_table()
table.enable_group(CapabilityGroup.DEV_TOOLS)  # opt-in: code_run, git_status, git_diff


@command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    """Say hello."""
    return f"Hello, {name}!"


@command("run_script", description="Execute Python code and return stdout.")
def run_script(code: str) -> str:
    """Execute Python code and return stdout."""
    import subprocess

    result = subprocess.run(["python3", "-c", code], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


@command(hidden=True)
def _debug_info() -> dict:
    """Internal debug command — not listed in /commands."""
    import platform

    return {"python": platform.python_version(), "system": platform.system()}


@table.route("GET", "/hello/{name}", group=CapabilityGroup.COMMANDS)
def hello_route(request: object) -> ServerResponse:
    """Custom route: GET /hello/{name} returns a greeting as JSON."""
    name = getattr(request, "path_params", {}).get("name", "World")
    return ServerResponse.ok({"greeting": f"Hello, {name}!"})


default_registry().freeze()

if __name__ == "__main__":
    import os

    start(int(os.environ.get("ABX_SERVER_PORT", "9000")))
