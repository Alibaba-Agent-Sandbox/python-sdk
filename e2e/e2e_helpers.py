"""Shared helpers for the real-cloud E2E suite (no secrets are ever logged here)."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

E2E_DIR = Path(__file__).resolve().parent
REPO_ROOT = E2E_DIR.parent

for _src in (REPO_ROOT / "client-sdk" / "src", REPO_ROOT / "server-sdk" / "src"):
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

T = TypeVar("T")

REQUIRED_ENV = ("E2B_API_KEY",)
DOCKER_ENV = ("AccessKey", "AccessSecret", "ACR_NAMESPACE")
SECRET_ENV = (
    "E2B_API_KEY",
    "AccessKey",
    "AccessSecret",
    "OPENAI_API_KEY",
)

RUN_ID = os.environ.get("E2E_RUN_ID") or (
    "e2e-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
)
os.environ["E2E_RUN_ID"] = RUN_ID

TAG_KEY = "e2e"
TEMPLATE_PREFIX = "e2e-"
SANDBOX_TTL = int(os.environ.get("E2E_SANDBOX_TTL", "300"))

OFFICIAL_BASE = "base"
OFFICIAL_CODE = "code-interpreter-v1"
SERVER_TEMPLATE = os.environ.get("E2E_SERVER_TEMPLATE", "python-hello")


def load_env() -> None:
    """Load the gitignored ``.env`` files; the process environment always wins."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv ships with client-sdk
        return
    for candidate in (E2E_DIR / ".env", REPO_ROOT / ".env", REPO_ROOT / "client-sdk" / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def missing_env(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not (os.environ.get(n) or "").strip()]


def mask(text: str) -> str:
    """Replace every known secret value (and sandbox tokens) in *text*."""
    out = text
    for name in SECRET_ENV:
        value = (os.environ.get(name) or "").strip()
        if len(value) >= 6:
            out = out.replace(value, f"<{name}:masked>")
    out = re.sub(r"(?i)(x-access-token|authorization|envdAccessToken)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+",
                 r"\1\2<masked>", out)
    return out


def tag_metadata(test_name: str = "") -> dict[str, str]:
    meta = {TAG_KEY: RUN_ID}
    if test_name:
        meta["e2e_test"] = re.sub(r"[^A-Za-z0-9_.-]", "_", test_name)[:60]
    return meta


class Tracker:
    """Records every cloud resource a run creates so finalizers can delete it."""

    def __init__(self) -> None:
        self.sandbox_ids: list[str] = []
        self.template_ids: list[str] = []
        self.template_names: list[str] = []
        self.local_images: list[str] = []
        self.cleanup_log: list[str] = []

    def sandbox(self, sandbox_id: str) -> None:
        if sandbox_id not in self.sandbox_ids:
            self.sandbox_ids.append(sandbox_id)


def eventually(
    fn: Callable[[], T],
    *,
    timeout: float = 30.0,
    interval: float = 1.0,
    what: str = "condition",
    swallow: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Poll *fn* until it returns a truthy value (known eventually-consistent ops only)."""
    deadline = time.monotonic() + timeout
    last_exc: BaseException | None = None
    while True:
        try:
            value = fn()
            if value:
                return value
            last_exc = None
        except swallow as exc:  # noqa: PERF203
            last_exc = exc
        if time.monotonic() >= deadline:
            detail = f" (last error: {type(last_exc).__name__}: {mask(str(last_exc))[:200]})" if last_exc else ""
            raise AssertionError(f"timed out after {timeout:.0f}s waiting for {what}{detail}")
        time.sleep(interval)


async def eventually_async(
    fn: Callable[[], Awaitable[T]],
    *,
    timeout: float = 30.0,
    interval: float = 1.0,
    what: str = "condition",
) -> T:
    deadline = time.monotonic() + timeout
    last_exc: BaseException | None = None
    while True:
        try:
            value = await fn()
            if value:
                return value
            last_exc = None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        if time.monotonic() >= deadline:
            detail = f" (last error: {type(last_exc).__name__}: {mask(str(last_exc))[:200]})" if last_exc else ""
            raise AssertionError(f"timed out after {timeout:.0f}s waiting for {what}{detail}")
        await asyncio.sleep(interval)


def unique_dir(prefix: str = "e2e") -> str:
    return f"/tmp/{prefix}-{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------- docker


def docker_cmd() -> list[str] | None:
    """Return an argv prefix that can talk to the Docker daemon, or ``None``.

    Order: plain ``docker`` -> ``sudo -n docker`` (the VM's ``ubuntu`` user is not
    in the ``docker`` group, but has passwordless sudo).
    """
    if not shutil.which("docker"):
        return None
    for prefix in (["docker"], ["sudo", "-n", "docker"]):
        try:
            proc = subprocess.run(
                [*prefix, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return prefix
    return None


def docker_unavailable_reason() -> str | None:
    """Exact reason Docker cannot be used (``None`` when it can)."""
    if not shutil.which("docker"):
        return "docker CLI not found on PATH"
    if docker_cmd() is not None:
        return None
    try:
        proc = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=20
        )
        err = (proc.stderr or proc.stdout).strip().splitlines()
        return "docker daemon unreachable: " + (err[-1] if err else "no output")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"docker info failed: {exc}"


def make_docker_shim(prefix: list[str], docker_config_dir: Path, shim_dir: Path) -> Path:
    """Write a ``docker`` executable that forwards to *prefix* with an isolated DOCKER_CONFIG.

    ``DockerBuilder`` takes a single executable path, so the shim lets it use
    ``sudo docker`` and keeps registry credentials out of ``~/.docker``.
    """
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "docker"
    if prefix[0] == "sudo":
        body = (
            "#!/bin/sh\n"
            f'exec sudo -n env DOCKER_CONFIG="{docker_config_dir}" docker "$@"\n'
        )
    else:
        body = f'#!/bin/sh\nDOCKER_CONFIG="{docker_config_dir}" exec docker "$@"\n'
    shim.write_text(body)
    shim.chmod(0o755)
    return shim


def run_async(loop: asyncio.AbstractEventLoop, coro: Awaitable[T]) -> T:
    return loop.run_until_complete(coro)


def json_safe(obj: Any) -> Any:
    return obj
