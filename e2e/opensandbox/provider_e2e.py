#!/usr/bin/env python3
"""End-to-end check of the ``opensandbox`` exec-provider plugin against a live OpenSandbox server.

Stages (each prints PASS/FAIL; exit code is non-zero if any fails):

1. ``node-unit``     plugin unit + mock-server tests (no server needed)
2. ``node-live``     plugin driven directly over EPP/1 (``tests/live``)
3. ``install``       ``python -m easy_sandbox.providers install <plugin dir>`` + ``doctor``
4. ``kit``           the shared ``ProviderContractTests`` with ``--provider-under-test opensandbox``
5. ``sdk``           ``Sandbox.create(provider="opensandbox")`` scenarios (``tests/contract``)
6. ``env``           configuration precedence: canonical ``EBX_OPENSANDBOX_*`` beats native
                   ``OPEN_SANDBOX_*``

Configuration (environment, never written anywhere):

* ``EBX_OPENSANDBOX_BASE_URL`` (or ``OPENSANDBOX_BASE_URL``)  server URL, default ``http://127.0.0.1:8080``
* ``EBX_OPENSANDBOX_API_KEY`` / ``OPEN_SANDBOX_API_KEY`` / ``OPENSANDBOX_API_KEY``  API key
* ``OPENSANDBOX_TEST_IMAGE``  image for the sandboxes (default ``python:3.12-slim``)

Usage::

    eval "$(./local-up.sh env)"      # or point the variables above at any reachable server
    python3 provider_e2e.py [--stages node-unit,install,kit,sdk,env] [--keep]

All provider state lives in a throwaway ``HOME`` so the real ``~/.ebx`` is never touched.
Requires: Node >= 20, Python >= 3.11 with ``easy_sandbox`` importable (the script adds the
sibling ``client-sdk/src`` and ``server-sdk/src`` to ``PYTHONPATH`` when they exist) and pytest.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "examples" / "providers" / "opensandbox"
ALL_STAGES = ["node-unit", "node-live", "install", "kit", "sdk", "env"]

BASE_URL = (
    os.environ.get("EBX_OPENSANDBOX_BASE_URL")
    or os.environ.get("OPENSANDBOX_BASE_URL")
    or "http://127.0.0.1:8080"
)
BASE_URL = BASE_URL.rstrip("/").removesuffix("/v1")
API_KEY = (
    os.environ.get("EBX_OPENSANDBOX_API_KEY")
    or os.environ.get("OPEN_SANDBOX_API_KEY")
    or os.environ.get("OPENSANDBOX_API_KEY")
    or ""
)


def sh_env(
    home: str, extra: dict[str, str] | None = None, *, strip: tuple[str, ...] = ()
) -> dict[str, str]:
    env = dict(os.environ)
    for name in list(env):
        if (
            name.startswith(("EBX_OPENSANDBOX_", "OPEN_SANDBOX_", "OPENSANDBOX_"))
            and name != "OPENSANDBOX_TEST_IMAGE"
        ):
            del env[name]
    paths = [str(ROOT / "client-sdk" / "src"), str(ROOT / "server-sdk" / "src")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env.update(
        HOME=home,
        USERPROFILE=home,
        PYTHONPATH=os.pathsep.join(p for p in paths if p),
        PYTHONDONTWRITEBYTECODE="1",
        EBX_OPENSANDBOX_BASE_URL=BASE_URL,
        OPEN_SANDBOX_API_KEY=API_KEY,
    )
    env.update(extra or {})
    for name in strip:
        env.pop(name, None)
    return env


def run(
    cmd: list[str], env: dict[str, str], cwd: Path | str, timeout: int = 900
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, env=env, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False
    )


def server_healthy() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL + "/health", timeout=5):
            return True
    except OSError:
        return False


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))
        print(
            f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True
        )

    def tail(self, proc: subprocess.CompletedProcess[str], lines: int = 25) -> str:
        return "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-lines:])


def stage_node_unit(rep: Report, home: str) -> None:
    p = run(["node", "tests/run.mjs", "unit", "mock"], sh_env(home), PLUGIN)
    rep.add(
        "node-unit: plugin unit + mock tests",
        p.returncode == 0,
        "" if p.returncode == 0 else rep.tail(p),
    )


def stage_node_live(rep: Report, home: str) -> None:
    env = sh_env(home, {"OPENSANDBOX_LIVE": "1", "EBX_OPENSANDBOX_API_KEY": API_KEY})
    p = run(["node", "tests/run.mjs", "live"], env, PLUGIN)
    rep.add(
        "node-live: EPP/1 directly against the server",
        p.returncode == 0,
        "" if p.returncode == 0 else rep.tail(p),
    )


def stage_install(rep: Report, home: str) -> None:
    env = sh_env(home)
    p = run(
        [sys.executable, "-m", "easy_sandbox.providers", "install", str(PLUGIN), "--yes"], env, home
    )
    rep.add("install: local path", p.returncode == 0, "" if p.returncode == 0 else rep.tail(p))
    p = run([sys.executable, "-m", "easy_sandbox.providers", "doctor", "opensandbox"], env, home)
    rep.add(
        "install: doctor (spawn + initialize handshake)",
        p.returncode == 0,
        "" if p.returncode == 0 else rep.tail(p),
    )


def stage_kit(rep: Report, home: str) -> None:
    env = sh_env(home)
    cmd = [sys.executable, "-m", "easy_sandbox.providers", "test", "opensandbox"]
    p = run(cmd, env, home)
    last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    passed = re.search(r"(\d+) passed", last)
    rep.add(
        "kit: python -m easy_sandbox.providers test opensandbox",
        p.returncode == 0 and bool(passed) and int(passed.group(1)) >= 12,
        last or rep.tail(p),
    )


def stage_sdk(rep: Report, home: str) -> None:
    env = sh_env(home, {"OPENSANDBOX_LIVE": "1"})
    cmd = [
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--rootdir", home, "--confcutdir", str(PLUGIN), str(PLUGIN / "tests" / "contract"),
    ]  # fmt: skip
    p = run(cmd, env, home)
    last = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    rep.add(
        "sdk: Sandbox.create(provider='opensandbox') scenarios",
        p.returncode == 0 and "passed" in last,
        last if p.returncode == 0 else rep.tail(p),
    )


_PROBE = """
import asyncio, sys
from easy_sandbox.api.sandbox import Sandbox
async def main():
    try:
        sb = await Sandbox.create(provider="opensandbox", timeout=120)
    except Exception as exc:
        print("ERR", getattr(exc, "code", type(exc).__name__)); return
    try:
        r = await sb.commands.run("echo ok")
        print("OK", r.stdout.strip())
    finally:
        await sb.kill()
asyncio.run(main())
"""


def probe(home: str, extra: dict[str, str], strip: tuple[str, ...] = ()) -> str:
    p = run([sys.executable, "-c", _PROBE], sh_env(home, extra, strip=strip), home, timeout=300)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "ERR"))]
    return lines[-1] if lines else "CRASH " + rep_tail(p)


def rep_tail(p: subprocess.CompletedProcess[str]) -> str:
    return " | ".join((p.stdout + p.stderr).strip().splitlines()[-3:])


def stage_env(rep: Report, home: str) -> None:
    parts = urlsplit(BASE_URL)
    host_port = parts.netloc
    dead = "http://127.0.0.1:9"
    base_names = ("EBX_OPENSANDBOX_BASE_URL",)
    key_names = ("OPEN_SANDBOX_API_KEY",)

    r = probe(home, {})
    rep.add("env: canonical base_url + native API key works", r.startswith("OK"), r)

    r = probe(home, {"EBX_OPENSANDBOX_BASE_URL": dead, "OPEN_SANDBOX_DOMAIN": host_port})
    rep.add(
        "env: canonical EBX_OPENSANDBOX_BASE_URL beats native OPEN_SANDBOX_DOMAIN",
        r.startswith("ERR"),
        r,
    )

    r = probe(
        home,
        {"OPEN_SANDBOX_DOMAIN": host_port, "OPEN_SANDBOX_PROTOCOL": parts.scheme or "http"},
        strip=base_names,
    )
    rep.add("env: native OPEN_SANDBOX_DOMAIN alone is enough", r.startswith("OK"), r)

    r = probe(home, {"EBX_OPENSANDBOX_API_KEY": "wrong-key"})
    rep.add(
        "env: canonical EBX_OPENSANDBOX_API_KEY beats native OPEN_SANDBOX_API_KEY",
        r.startswith("ERR"),
        r,
    )

    r = probe(home, {}, strip=key_names)
    wants_key = r.startswith("ERR") or r.startswith("OK")
    rep.add("env: missing API key is reported (server decides if auth is required)", wants_key, r)

    r = probe(home, {"OPEN_SANDBOX_API_KEY": "wrong-key"})
    rep.add("env: wrong API key is an error, not a crash", r.startswith("ERR"), r)


STAGES = {
    "node-unit": stage_node_unit,
    "node-live": stage_node_live,
    "install": stage_install,
    "kit": stage_kit,
    "sdk": stage_sdk,
    "env": stage_env,
}
NEEDS_SERVER = {"node-live", "kit", "sdk", "env"}
NEEDS_INSTALL = {"kit", "sdk", "env"}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--stages",
        default=",".join(ALL_STAGES),
        help="comma-separated subset of: " + ", ".join(ALL_STAGES),
    )
    ap.add_argument("--keep", action="store_true", help="keep the throwaway HOME for inspection")
    args = ap.parse_args()
    chosen = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in chosen if s not in STAGES]
    if unknown:
        ap.error(f"unknown stage(s): {', '.join(unknown)}")
    if not shutil.which("node"):
        print("node (>= 20) is required", file=sys.stderr)
        return 2
    if NEEDS_SERVER & set(chosen) and not server_healthy():
        print(
            f"OpenSandbox server not reachable at {BASE_URL}/health (see local-up.sh).",
            file=sys.stderr,
        )
        return 2

    home = tempfile.mkdtemp(prefix="ebx-osb-e2e-")
    rep = Report()
    started = time.monotonic()
    try:
        if NEEDS_INSTALL & set(chosen) and "install" not in chosen:
            stage_install(Report(), home)
        for name in chosen:
            STAGES[name](rep, home)
    finally:
        if args.keep:
            print(f"kept {home}")
        else:
            shutil.rmtree(home, ignore_errors=True)
    failed = [n for n, ok, _ in rep.rows if not ok]
    print(
        f"\n{len(rep.rows) - len(failed)}/{len(rep.rows)} checks passed"
        f" in {time.monotonic() - started:.0f}s"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
