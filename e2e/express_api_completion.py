"""Manual real-service acceptance for Express lifecycle, traffic and runtime extensions.

Requires matched client/server source and ABX_BIN pointing at the candidate CLI.
Uses an existing ready generation-2 template; creates and deletes only its own
sandbox. Optional ABX_E2E_MOUNTS_FILE supplies real append-mount fixtures. No
management credential is created or renewed, and no user storage is deleted.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import tempfile
import time
import uuid
from pathlib import Path

import httpx


async def main() -> int:
    # A private test home isolates the candidate engine from existing user sessions.
    test_home = Path(tempfile.mkdtemp(prefix="express-api-acceptance-"))
    os.environ["HOME"] = str(test_home)
    from agent_sandbox import ProviderSandbox
    from agent_sandbox.providers.commands import run_command

    api = (os.environ.get("ABX_SANDBOX_BASE_URL") or os.environ["E2B_API_URL"]).rstrip("/")
    key = os.environ.get("ABX_SANDBOX_API_KEY") or os.environ["E2B_API_KEY"]
    domain = os.environ.get("ABX_SANDBOX_DOMAIN") or os.environ["E2B_DOMAIN"]
    run_id = uuid.uuid4().hex
    results: list[dict[str, object]] = []
    owned: set[str] = set()
    sandbox = None
    local_clients = []
    recovery = Path(tempfile.gettempdir()) / f"express-api-owned-{run_id}.json"

    def persist() -> None:
        recovery.write_text(json.dumps({"sandbox_ids": sorted(owned)}))
        recovery.chmod(0o600)

    def created(sandbox_id: str) -> None:
        owned.add(sandbox_id)
        persist()

    async def command(name: str, value: dict[str, object]) -> object:
        return await run_command("alicloud-express", name, value, confirm=True)

    async def stage(name: str, action) -> bool:
        try:
            await action()
            result: dict[str, object] = {"scenario": name, "result": "PASS"}
        except Exception as error:
            # Raw cloud exceptions may contain headers, resource identifiers or rules.
            result = {"scenario": name, "result": "FAIL", "error_type": type(error).__name__}
            code = getattr(error, "code", None)
            if isinstance(code, str) and code.startswith("E") and code[1:].isdigit():
                result["error_code"] = code
            status = getattr(error, "status_code", None)
            if not isinstance(status, int):
                matched = re.search(r"\bHTTP\s?(\d{3})\b", str(getattr(error, "message", "")))
                status = int(matched[1]) if matched else None
            if isinstance(status, int):
                result["http_status"] = status
            endpoint = getattr(error, "endpoint", None)
            if endpoint in {"capabilities", "commands", "commands_run", "health"}:
                result["endpoint"] = endpoint
        results.append(result)
        print(json.dumps(result), flush=True)
        return result["result"] == "PASS"

    async def until(check, timeout: float = 90) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await check():
                return
            await asyncio.sleep(2)
        raise TimeoutError("Service did not reach its expected state")

    async def choose_template() -> str:
        explicit = os.environ.get("ABX_E2E_GEN2_TEMPLATE")
        if explicit:
            return explicit
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(api + "/templates", headers={"X-API-Key": key})
            response.raise_for_status()
            data = response.json()
            entries = data if isinstance(data, list) else data["templates"]
            allowed = {item.get("templateID", item.get("templateId")) for item in entries}
        page = await run_command("alicloud-express", "team.list", {"page_size": 100})
        for team in page["data"]["teams"]:
            cursor = None
            while True:
                inputs = {"team_id": team["team_id"], "max_results": 100}
                if cursor:
                    inputs["next_token"] = cursor
                page = await run_command("alicloud-express", "template.list", inputs)
                for item in page["data"]["templates"]:
                    config = item.get("runtime_config", {}).get("sandbox_config", {})
                    if (
                        item["template_id"] in allowed
                        and config.get("generation") == 2
                        and item.get("status", {}).get("state") == "ready"
                    ):
                        return item["template_id"]
                cursor = page["data"].get("next_token")
                if not cursor:
                    break
        raise RuntimeError("No ready generation-2 template belongs to this configured key")

    try:
        template = await choose_template()

        async def create_private() -> None:
            nonlocal sandbox
            sandbox = await ProviderSandbox.create(
                template,
                timeout=900,
                secure=True,
                network={"allow_public_traffic": False},
                metadata={"abx_api_review": run_id},
                sandbox_api_key=key,
                sandbox_base_url=api,
                sandbox_domain=domain,
                on_created=created,
            )
            local_clients.append(sandbox)
            assert sandbox._info.traffic_access_token
            await sandbox.files.write("/tmp/express-api-marker", "before-resume")
            assert (
                await sandbox.commands.run("cat /tmp/express-api-marker")
            ).stdout == "before-resume"

        if not await stage("private create, command and file", create_private):
            return 1
        assert sandbox is not None

        async def lifecycle() -> None:
            await sandbox.pause()
            await sandbox.resume()

            async def readable() -> bool:
                # This explicitly repeats an idempotent read while the backend resumes.
                try:
                    result = await sandbox.commands.run("cat /tmp/express-api-marker")
                    return result.stdout == "before-resume"
                except Exception:
                    return False

            await until(readable)
            await sandbox.files.write("/tmp/express-api-marker", "after-resume")
            assert await sandbox.files.read("/tmp/express-api-marker") == "after-resume"

        await stage("same-object pause/resume and subsequent execution/files", lifecycle)

        async def application() -> None:
            # Lifecycle fixtures may intentionally omit a language runtime. Use
            # the documented interpreter template for the application scenario.
            app_sandbox = await ProviderSandbox.create(
                os.environ.get("ABX_E2E_APPLICATION_TEMPLATE", "code-interpreter-v1"),
                timeout=600,
                secure=True,
                network={"allow_public_traffic": False},
                metadata={"abx_api_review": run_id},
                sandbox_api_key=key,
                sandbox_base_url=api,
                sandbox_domain=domain,
                on_created=created,
            )
            local_clients.append(app_sandbox)
            available = await app_sandbox.commands.run(
                'python3 -c "import importlib.util; '
                "print('installed' if importlib.util.find_spec('agent_sandbox') "
                "else 'missing')\""
            )
            if available.stdout.strip() != "installed":
                installed = await app_sandbox.commands.run(
                    "python3 -m pip install --index-url https://pypi.org/simple "
                    "agent-sandbox-server==0.4.0a6",
                    timeout=180,
                )
                assert installed.exit_code == 0
            source = """from agent_sandbox.server import command
@command("review_inputs")
def review_inputs(timeout: int, name: str, arguments: str) -> dict:
    return {"timeout": timeout, "name": name, "arguments": arguments}
"""
            await app_sandbox.files.write("/tmp/express-api-commands.py", source)
            application_token = uuid.uuid4().hex
            app_port = 9017
            service_stream = await app_sandbox.commands.run(
                f"python3 -m agent_sandbox.server serve --host 0.0.0.0 --port {app_port} "
                "--commands /tmp/express-api-commands.py",
                timeout=480,
                background=True,
                env={"ABX_SERVER_TOKEN": application_token},
            )

            async def drain_service() -> None:
                # envd streaming execution starts on iteration. Keep the stream
                # alive and consume it without printing potentially sensitive logs.
                async for _ in service_stream:
                    pass

            service_task = asyncio.create_task(drain_service())
            client = await app_sandbox.application_client(app_port, token=application_token)
            try:
                local_probe = """import json, os, urllib.request
payload = {"timeout": 5, "name": "review", "arguments": "preserved"}
checks = []
for method, suffix in [("GET", "/commands"), ("POST", "/commands/review_inputs")]:
    request = urllib.request.Request("http://127.0.0.1:9017" + suffix,
        data=json.dumps(payload).encode() if method == "POST" else None,
        headers={"Authorization": "Bearer " + os.environ["ABX_DIAG_APP_TOKEN"],
                 "Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
        matched = (any(item.get("name") == "review_inputs" for item in data.get("commands", []))
                   if method == "GET" else data.get("result") == payload)
        checks.append(response.status == 200 and matched)
print(json.dumps({"registered_and_invoked": all(checks)}))
"""
                await app_sandbox.files.write("/tmp/express-api-local-probe.py", local_probe)

                async def local_ready() -> bool:
                    result = await app_sandbox.commands.run(
                        "python3 /tmp/express-api-local-probe.py",
                        env={"ABX_DIAG_APP_TOKEN": application_token},
                        timeout=20,
                    )
                    return (
                        result.exit_code == 0
                        and json.loads(result.stdout).get("registered_and_invoked") is True
                    )

                await until(local_ready, 60)
                print(
                    json.dumps({"checkpoint": "envd localhost registered and invoked"}), flush=True
                )
                await until(client.health, 60)
                print(json.dumps({"checkpoint": "application health ready"}), flush=True)
                payload = {"timeout": 5, "name": "review", "arguments": "preserved"}
                assert any(item.name == "review_inputs" for item in await client.commands.list())
                assert (
                    await app_sandbox.invoke(
                        "review_inputs",
                        payload,
                        server_port=app_port,
                        application_token=application_token,
                    )
                    == payload
                )
                print(json.dumps({"checkpoint": "application first invoke"}), flush=True)
                async with httpx.AsyncClient(timeout=20) as http:
                    url = app_sandbox.network.get_url(app_port)
                    direct = await http.post(
                        url + "/commands/review_inputs",
                        json=payload,
                        headers={
                            "Authorization": "Bearer " + application_token,
                            "e2b-traffic-access-token": app_sandbox._info.traffic_access_token,
                        },
                    )
                    assert direct.status_code == 200 and direct.json().get("result") == payload
                    anonymous = await http.get(url + "/commands")
                    assert anonymous.status_code == 403
                print(json.dumps({"checkpoint": "anonymous denied"}), flush=True)
                attached = await ProviderSandbox.connect(
                    app_sandbox.id,
                    sandbox_api_key=key,
                    sandbox_base_url=api,
                    sandbox_domain=domain,
                    traffic_access_token=app_sandbox._info.traffic_access_token,
                )
                try:
                    assert (
                        await attached.invoke(
                            "review_inputs",
                            payload,
                            server_port=app_port,
                            application_token=application_token,
                        )
                        == payload
                    )
                    print(json.dumps({"checkpoint": "GET attach application invoke"}), flush=True)
                finally:
                    await attached.close()
                node_module = os.environ.get("ABX_E2E_NODE_MODULE")
                if node_module:
                    node = await asyncio.create_subprocess_exec(
                        "node",
                        "--input-type=module",
                        "-",
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env={
                            "PATH": os.environ.get("PATH", ""),
                            **{
                                name: os.environ[name]
                                for name in ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR")
                                if name in os.environ
                            },
                            "ABX_DIAG_MODULE": Path(node_module).resolve().as_uri(),
                            "ABX_DIAG_URL": app_sandbox.network.get_url(app_port),
                            "ABX_DIAG_APP_TOKEN": application_token,
                            "ABX_DIAG_TRAFFIC": app_sandbox._info.traffic_access_token,
                        },
                    )
                    node_source = b"""
const { ServerClient } = await import(process.env.ABX_DIAG_MODULE);
const { isDeepStrictEqual } = await import("node:util");
const client = new ServerClient(process.env.ABX_DIAG_URL, {
  token: process.env.ABX_DIAG_APP_TOKEN,
  gatewayHeaders: { "e2b-traffic-access-token": process.env.ABX_DIAG_TRAFFIC }
});
try {
  const commands = await client.commands.list();
  const payload = { timeout: 5, name: "review", arguments: "preserved" };
  const result = await client.commands.invoke("review_inputs", payload, { requestTimeout: 30 });
  const listed = commands.some(item => item.name === "review_inputs");
  const matched = isDeepStrictEqual(result, payload);
  console.log(JSON.stringify({ listed, matched }));
  if (!listed || !matched) process.exitCode = 1;
} catch (error) {
  console.log(JSON.stringify({ listed: false, matched: false,
    error_type: error.name, status: error.statusCode ?? null }));
  process.exitCode = 1;
} finally { await client.close(); }
"""
                    try:
                        node_stdout, _ = await asyncio.wait_for(
                            node.communicate(node_source), timeout=60
                        )
                        summary = json.loads(node_stdout)
                        print(
                            json.dumps(
                                {
                                    "checkpoint": "Node command response",
                                    "listed": summary.get("listed"),
                                    "matched": summary.get("matched"),
                                    "error_type": summary.get("error_type"),
                                    "http_status": summary.get("status"),
                                }
                            ),
                            flush=True,
                        )
                        assert node.returncode == 0
                    finally:
                        if node.returncode is None:
                            node.kill()
                            await node.wait()
                    print(
                        json.dumps({"checkpoint": "Node private gateway list and invoke"}),
                        flush=True,
                    )
            finally:
                service_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await service_task
                await client.aclose()
                await app_sandbox.close()

        async def network() -> None:
            await command(
                "sandbox.network.update",
                {
                    "sandbox_id": sandbox.id,
                    "network": {"allow_out": ["example.com"], "deny_out": ["0.0.0.0/0"]},
                },
            )
            async with httpx.AsyncClient(timeout=30) as http:
                response = await http.get(
                    api + "/sandboxes/" + sandbox.id, headers={"X-API-Key": key}
                )
                response.raise_for_status()
                assert "example.com" in response.json().get("network", {}).get("allowOut", [])
            await command("sandbox.network.update", {"sandbox_id": sandbox.id, "network": {}})

        await stage("provider network replacement and clearing", network)

        async def lifetime() -> None:
            await command("sandbox.timeout", {"sandbox_id": sandbox.id, "timeout": 600})

        await stage("provider runtime timeout", lifetime)
        await stage(
            "private gateway authentication and collision-free application invocation", application
        )
        mounts_file = os.environ.get("ABX_E2E_MOUNTS_FILE")
        if mounts_file:

            async def mounts() -> None:
                inputs = json.loads(Path(mounts_file).read_text())
                inputs["sandbox_id"] = sandbox.id
                await command("sandbox.mounts.append", inputs)
                for mount in inputs.get("named_volume_mounts", []):
                    await sandbox.files.list(mount["path"])
                for storage in inputs.get("inline_volume_mounts", {}).values():
                    for mount in storage.get("mount_points", []):
                        await sandbox.files.list(mount["mount_dir"])

            await stage("runtime append mounts and independent directory read", mounts)
        else:
            results.append(
                {
                    "scenario": "runtime append mounts",
                    "result": "BLOCKED",
                    "reason": "No real storage fixture supplied",
                }
            )
            print(json.dumps(results[-1]), flush=True)
    finally:
        for local in local_clients:
            await local.close()
        async with httpx.AsyncClient(timeout=30) as http:
            # Reconcile a create whose response was lost before on_created ran.
            response = await http.get(api + "/sandboxes", headers={"X-API-Key": key})
            response.raise_for_status()
            listed = response.json()
            entries = listed if isinstance(listed, list) else listed.get("sandboxes", [])
            for item in entries:
                if item.get("metadata", {}).get("abx_api_review") == run_id:
                    owned.add(item["sandboxID"])
            persist()
            for sandbox_id in list(owned):
                response = await http.delete(
                    api + "/sandboxes/" + sandbox_id, headers={"X-API-Key": key}
                )
                assert response.status_code in (200, 204, 404), (
                    "Owned sandbox deletion was not confirmed"
                )
                response = await http.get(
                    api + "/sandboxes/" + sandbox_id, headers={"X-API-Key": key}
                )
                assert response.status_code == 404, "Owned sandbox is still present"
                owned.remove(sandbox_id)
                persist()
        record = test_home / ".abx" / "engine.json"
        if record.exists():
            value = json.loads(record.read_text())
            with contextlib.suppress(ProcessLookupError):
                os.kill(value["pid"], signal.SIGTERM)
        if not owned:
            recovery.unlink(missing_ok=True)
            shutil.rmtree(test_home)
        print(
            json.dumps(
                {
                    "scenario": "independent owned cleanup",
                    "result": "PASS" if not owned else "FAIL",
                    "remaining": len(owned),
                }
            ),
            flush=True,
        )
    return (
        1
        if any(item["result"] == "FAIL" for item in results)
        else 2
        if any(item["result"] == "BLOCKED" for item in results)
        else 0
    )


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception as error:
        print(
            json.dumps(
                {
                    "scenario": "acceptance controller",
                    "result": "FAIL",
                    "error_type": type(error).__name__,
                }
            ),
            flush=True,
        )
        code = 1
    raise SystemExit(code)
