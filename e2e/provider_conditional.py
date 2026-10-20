#!/usr/bin/env python3
"""Local-only CLI + Python -> real engine -> one Express provider acceptance.

Requires a ready, allowlisted generation2 template, a built abx binary and local
credentials. Never collected by pytest or dispatched from Actions. Only resources
created with this invocation's metadata are cleaned up.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abx", default=os.environ.get("ABX_BIN", "abx"))
    parser.add_argument("--template", default=os.environ.get("E2E_SNAPSHOT_TEMPLATE"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.template:
        parser.error("a ready generation2 --template or E2E_SNAPSHOT_TEMPLATE is required")
    from dotenv import dotenv_values

    values = {**dotenv_values(args.env_file), **os.environ}
    settings = {
        "api_key": values.get("ABX_SANDBOX_API_KEY") or values.get("E2B_API_KEY"),
        "api_url": values.get("ABX_SANDBOX_BASE_URL") or values.get("E2B_API_URL"),
        "domain": values.get("ABX_SANDBOX_DOMAIN") or values.get("E2B_DOMAIN"),
    }
    if not all(settings.values()):
        parser.error("local Express API key, origin and domain are required")
    from urllib.parse import urlparse

    if not (urlparse(settings["api_url"]).hostname or "").endswith(".aliyuncs.com"):
        parser.error("this acceptance is limited to an explicit Alibaba Cloud Express origin")
    argv = shlex.split(args.abx)
    result = {
        "scope": "local real CLI + Python engine shared-provider acceptance",
        "status": "RUNNING",
        "steps": [],
        "owned_sandboxes_remaining": None,
        "owned_snapshots_remaining": None,
    }
    if len(argv) == 1 and Path(argv[0]).is_file():
        result["binary_sha256"] = hashlib.sha256(Path(argv[0]).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="provider-conditional-") as profile_dir:
        child_env = dict(
            os.environ,
            HOME=profile_dir,
            NO_COLOR="1",
            ABX_PROVIDER="alicloud-express",
            ABX_PROVIDER_UPDATE_CHECK="0",
        )
        for wire, project in [
            ("api_key", "ABX_SANDBOX_API_KEY"),
            ("api_url", "ABX_SANDBOX_BASE_URL"),
            ("domain", "ABX_SANDBOX_DOMAIN"),
        ]:
            child_env[project] = settings[wire]
        # The real engine and SDK use this isolated profile; the developer's engine is untouched.
        import agent_sandbox.transport.config as config
        from agent_sandbox.providers import engine_client

        config._CONFIG_FILE = Path(profile_dir) / ".abx" / "config.toml"
        with open(os.devnull, "wb") as discard:
            engine = subprocess.Popen(
                [*argv, "provider", "engine", "serve", "--idle-timeout", "0"],
                env=child_env,
                stdout=discard,
                stderr=discard,
            )
            try:
                asyncio.run(exercise(args, argv, child_env, settings, result, engine_client))
            finally:
                engine.terminate()
                try:
                    engine.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    engine.kill()
                    engine.wait()
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


async def exercise(args, argv, child_env, settings, result, engine_client):
    import httpx

    from agent_sandbox import AsyncSandbox, SandboxQuery, SandboxState
    from agent_sandbox.providers import commands

    run_id = "provider-conditional-" + uuid.uuid4().hex[:12]
    owned = set()
    snapshots = set()
    source_id = None
    failure = None
    canonical = {
        "sandbox_api_key": settings["api_key"],
        "sandbox_base_url": settings["api_url"],
        "sandbox_domain": settings["domain"],
    }

    def passed(label):
        result["steps"].append({"scenario": label, "result": "PASS"})
        print("PASS:", label, flush=True)

    async def cli(command_id, payload, confirm=False):
        invocation = [
            *argv,
            "--json",
            "provider",
            "command",
            "run",
            "alicloud-express",
            command_id,
            "--input",
            json.dumps(payload),
        ]
        if confirm:
            invocation.append("--yes")
        proc = await asyncio.create_subprocess_exec(
            *invocation,
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), 370)
        if proc.returncode:
            if b"HTTP409" in stdout + _stderr:
                raise RuntimeError("known-transition-HTTP409")
            raise RuntimeError(
                f"CLI provider command {command_id} failed "
                f"(exit {proc.returncode}); output withheld"
            )
        return json.loads(stdout)

    async def sdk(command_id, payload, confirm=False):
        return await commands.run_command(
            "alicloud-express", command_id, payload, confirm=confirm, **canonical
        )

    async def until(check, timeout=120):
        deadline = time.monotonic() + timeout
        while True:
            if await check():
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("Owned resource transition/index did not settle")
            await asyncio.sleep(2)

    async def tagged_ids(state=None):
        paginator = AsyncSandbox.list(
            query=SandboxQuery(
                metadata={"acceptance": run_id}, **({"state": [state]} if state else {})
            ),
            **settings,
        )
        found = set()
        while paginator.has_next:
            found.update(item.sandbox_id for item in await paginator.next_items())
        return found

    async def snapshot_ids():
        cursor = None
        found = set()
        while True:
            data = await sdk(
                "snapshot.list",
                {"sandbox_id": source_id, "limit": 1, **({"next_token": cursor} if cursor else {})},
            )
            found.update(row["snapshot_id"] for row in data["snapshots"])
            cursor = data["next_token"]
            if not cursor:
                return found

    async def kill(sandbox_id):
        async def settled():
            try:
                await AsyncSandbox.kill(sandbox_id, **settings)
                return True
            except Exception as exc:
                if str(exc).startswith("409:"):
                    return False
                raise

        await until(settled)
        async with httpx.AsyncClient(timeout=30) as transport:
            response = await transport.get(
                settings["api_url"].rstrip("/") + "/sandboxes/" + sandbox_id,
                headers={"X-API-Key": settings["api_key"]},
            )
            assert response.status_code == 404
        owned.discard(sandbox_id)

    try:

        async def engine_ready():
            try:
                await engine_client.discover(spawn=False)
                return True
            except Exception:
                return False

        await until(engine_ready, timeout=30)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            "--json",
            "provider",
            "command",
            "list",
            "alicloud-express",
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()
        assert proc.returncode == 0
        descriptors = await commands.list_commands("alicloud-express")
        assert json.loads(stdout) == descriptors
        expected = {
            "sandbox.pause",
            "sandbox.resume",
            "snapshot.create",
            "snapshot.list",
            "snapshot.restore",
            "snapshot.delete",
        }
        assert expected <= {item["id"] for item in descriptors}
        passed(
            "CLI and Python discover identical provider-owned descriptors through the actual engine"
        )

        source = await AsyncSandbox.create(
            template=args.template, timeout=900, metadata={"acceptance": run_id}, **settings
        )
        source_id = source.sandbox_id
        owned.add(source_id)
        path = "/tmp/provider-checkpoint.txt"
        await source.files.write(path, "source-state")
        program = (
            "import http.server,uuid; token=uuid.uuid4().hex; "
            "Handler=type('Handler',(http.server.BaseHTTPRequestHandler,),{"
            "'do_GET':lambda self:(self.send_response(200),self.end_headers(),"
            "self.wfile.write(token.encode())),'log_message':lambda *args:None}); "
            "http.server.HTTPServer(('127.0.0.1',8765),Handler).serve_forever()"
        )
        await source.commands.run("python3 -u -c " + shlex.quote(program), background=True)
        probe = "python3 -c " + shlex.quote(
            "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765',timeout=3).read().decode())"
        )

        async def probe_ready():
            try:
                return bool((await source.commands.run(probe)).stdout.strip())
            except Exception:
                return False

        await until(probe_ready, timeout=30)
        token = (await source.commands.run(probe)).stdout.strip()
        assert len(token) == 32
        for pause_client, resume_client, label in [
            (cli, sdk, "CLI pause / Python resume"),
            (sdk, cli, "Python pause / CLI resume"),
        ]:
            await pause_client("sandbox.pause", {"sandbox_id": source_id}, confirm=True)

            async def paused():
                return source_id in await tagged_ids(SandboxState.PAUSED)

            await until(paused)
            await resume_client(
                "sandbox.resume", {"sandbox_id": source_id, "timeout": 900}, confirm=True
            )
            assert await source.files.read(path) == "source-state"
            assert (await source.commands.run(probe)).stdout.strip() == token
            passed(label + " preserves memory and files")

        async def running_again():
            return source_id in await tagged_ids(
                SandboxState.RUNNING
            ) and source_id not in await tagged_ids(SandboxState.PAUSED)

        await until(running_again)
        # Resume's data plane can answer before snapshot admission has settled.
        # Observe running state and a quiet interval before the first mutation;
        # this is not a replay of any failed/ambiguous Snapshot request.
        await asyncio.sleep(30)

        for create_client, restore_client, delete_client, label in [
            (sdk, cli, sdk, "Python Snapshot / CLI restore"),
            (cli, sdk, cli, "CLI Snapshot / Python restore"),
        ]:
            checkpoint = "checkpoint-" + uuid.uuid4().hex[:12]
            deadline = time.monotonic() + 120
            while True:
                try:
                    info = await create_client(
                        "snapshot.create",
                        {"sandbox_id": source_id, "name": checkpoint},
                        confirm=True,
                    )
                    break
                except Exception as exc:
                    # A definite409 rejection after our pause/resume is a known busy
                    # transition, not an ambiguous timeout/5xx mutation. Never replay
                    # any other failure, and reconcile our unique name before retrying.
                    message = getattr(exc, "message", str(exc))
                    if "HTTP409" not in message or time.monotonic() >= deadline:
                        raise
                    page = await sdk("snapshot.list", {"sandbox_id": source_id, "name": checkpoint})
                    if page["snapshots"]:
                        assert len(page["snapshots"]) == 1
                        info = page["snapshots"][0]
                        break
                    result["snapshot_busy_rejections"] = (
                        result.get("snapshot_busy_rejections", 0) + 1
                    )
                    await asyncio.sleep(2)
            snapshot_id = info["snapshot_id"]
            snapshots.add(snapshot_id)

            async def indexed(snapshot_id=snapshot_id):
                return snapshot_id in await snapshot_ids()

            await until(indexed)
            page = await cli("snapshot.list", {"sandbox_id": source_id})
            assert snapshot_id in {row["snapshot_id"] for row in page["snapshots"]}
            restored = await restore_client(
                "snapshot.restore",
                {"snapshot_id": snapshot_id, "timeout": 300, "metadata": {"acceptance": run_id}},
                confirm=True,
            )
            restored_id = restored["sandbox_id"]
            owned.add(restored_id)
            clone = await AsyncSandbox.connect(restored_id, **settings)
            assert await clone.files.read(path) == "source-state"
            assert (await clone.commands.run(probe)).stdout.strip() == token
            await clone.files.write(path, "clone-state")
            assert await source.files.read(path) == "source-state"
            await kill(restored_id)
            assert (
                await delete_client("snapshot.delete", {"snapshot_id": snapshot_id}, confirm=True)
            )["deleted"]

            async def deleted(snapshot_id=snapshot_id):
                return snapshot_id not in await snapshot_ids()

            await until(deleted)
            snapshots.discard(snapshot_id)
            passed(label + ": list, memory/files, clone isolation and independent deletion")
    except Exception as exc:
        # Exceptions and subprocess output may contain private endpoints/identifiers.
        failure = type(exc).__name__
        result["failure_code"] = getattr(exc, "code", None)
        message = getattr(exc, "message", "")
        if message.startswith(
            ("Express operation", "Express returned an invalid", "Provider command")
        ):
            result["failure_summary"] = message
        import traceback

        result["failure_frames"] = [
            {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
            for f in traceback.extract_tb(exc.__traceback__)[-5:]
        ]
        result["steps"].append(
            {"scenario": "real provider acceptance", "result": "FAIL", "error_type": failure}
        )
    finally:
        cleanup_errors = []
        # Reconcile tags after uncertain create/restore results; never touch untagged resources.
        try:
            owned.update(await tagged_ids())
        except Exception as exc:
            cleanup_errors.append(type(exc).__name__)
        for sandbox_id in sorted(owned):
            try:
                await kill(sandbox_id)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if source_id:
            try:
                snapshots.update(await snapshot_ids())
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        for snapshot_id in list(snapshots):
            try:
                await sdk("snapshot.delete", {"snapshot_id": snapshot_id}, confirm=True)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if source_id:
            try:

                async def snapshots_gone():
                    return not await snapshot_ids()

                await until(snapshots_gone)
                snapshots.clear()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        result.update(
            owned_sandboxes_remaining=len(owned),
            owned_snapshots_remaining=len(snapshots),
            cleanup_errors=cleanup_errors,
        )
        result["status"] = (
            "PASS" if not failure and not owned and not snapshots and not cleanup_errors else "FAIL"
        )
        if result["status"] == "PASS":
            passed(
                "API404 readbacks and source-filtered Snapshot lists confirm zero owned residuals"
            )


if __name__ == "__main__":
    main()
