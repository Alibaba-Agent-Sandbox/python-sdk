"""Custom-template flow: DockerBuilder -> ACR push -> official CreateTemplate -> sandbox -> server-sdk.

Marked ``e2e_docker``: it self-skips when Docker or the ACR/AccessKey environment is unavailable,
and also when a *canary* push to ACR cannot complete (see ``docker_ctx``). Everything created is
named ``e2e-<run suffix>`` so ``scripts/e2e-cleanup.py --templates --acr`` can remove leftovers.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import e2e_acr
import e2e_helpers as H
from conftest import ServerHandle, create_tracked, wait_envd_ready

pytestmark = [pytest.mark.e2e_docker, pytest.mark.e2e_slow]

CANARY_PUSH_TIMEOUT = int(os.environ.get("E2E_CANARY_PUSH_TIMEOUT", "120"))
CANARY_BYTES = int(os.environ.get("E2E_CANARY_BYTES", "2000000"))
TEMPLATE_READY_TIMEOUT = int(os.environ.get("E2E_TEMPLATE_READY_TIMEOUT", "900"))

DOCKERFILE = """\
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONPATH=/opt/py
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \\
    && rm -rf /var/lib/apt/lists/* && pip3 install --no-cache-dir websockets
COPY py /opt/py
COPY app.py /app/app.py
WORKDIR /app
EXPOSE 9000
CMD ["python3", "/app/app.py"]
"""

APP = '''\
from easy_sandbox.server import CapabilityGroup, CommandRegistry, SandboxServer, default_table

table = default_table()
table.enable_group(CapabilityGroup.FILE_OPS)
table.enable_group(CapabilityGroup.PROCESS)
table.enable_group(CapabilityGroup.SYSTEM)
registry = CommandRegistry()


@registry.command("echo_back", description="Echo a message")
def echo_back(message: str = "none") -> str:
    return "e2e-custom:" + message


registry.freeze()
SandboxServer(registry=registry).serve(port=9000)
'''


def _buildx_available(prefix: list[str]) -> bool:
    proc = subprocess.run([*prefix, "buildx", "version"], capture_output=True, text=True, timeout=30)
    return proc.returncode == 0


@pytest.fixture(scope="module")
def docker_ctx(tracker):  # type: ignore[no-untyped-def]
    """Docker shim with an isolated DOCKER_CONFIG + a canary push; skips when the registry path is unusable."""
    from easy_sandbox.api.docker_builder import ACRConfig, DockerBuilder

    prefix = H.docker_cmd()
    assert prefix is not None  # guaranteed by the collection-time skip
    cfg_dir = Path(tempfile.mkdtemp(prefix="e2e-dockercfg-"))
    cfg_dir.chmod(0o700)
    shim = H.make_docker_shim(prefix, cfg_dir, Path(tempfile.mkdtemp(prefix="e2e-dockershim-")))
    if not _buildx_available(prefix):
        os.environ["DOCKER_BUILDKIT"] = "0"  # the SDK adds buildx-only flags otherwise
    builder = DockerBuilder(docker_cmd=str(shim))
    ns = os.environ["ACR_NAMESPACE"]
    ak, sk = os.environ["AccessKey"], os.environ["AccessSecret"]
    canary = ACRConfig(namespace=ns, repo=f"{H.TEMPLATE_PREFIX}canary")

    try:
        builder.login_acr_with_aksk(canary.registry, ak, sk)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"e2e_docker skipped: ACR login failed ({type(exc).__name__}: {H.mask(str(exc))[:120]})")

    ref = canary.tagged_ref("canary")
    canary_ctx = Path(tempfile.mkdtemp(prefix="e2e-canary-ctx-"))
    (canary_ctx / "blob").write_bytes(os.urandom(CANARY_BYTES))  # fresh layer: cannot be deduplicated
    (canary_ctx / "Dockerfile").write_text("FROM alpine:latest\nCOPY blob /blob\n")
    build = subprocess.run(
        [str(shim), "build", "-q", "-t", ref, str(canary_ctx)], capture_output=True, text=True, timeout=300
    )
    shutil.rmtree(canary_ctx, ignore_errors=True)
    if build.returncode != 0:
        shutil.rmtree(cfg_dir, ignore_errors=True)
        pytest.skip(f"e2e_docker skipped: canary image build failed: {H.mask(build.stderr[-200:])}")
    tracker.local_images.append(ref)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [str(shim), "push", ref], capture_output=True, text=True, timeout=CANARY_PUSH_TIMEOUT
        )
        pushed = proc.returncode == 0
        detail = H.mask(proc.stderr[-200:])
    except subprocess.TimeoutExpired:
        kbps = "<%d" % (CANARY_BYTES / 1000 / CANARY_PUSH_TIMEOUT + 1)
        pushed = False
        detail = (
            f"a {CANARY_BYTES // 1000} KB layer did not finish uploading within {CANARY_PUSH_TIMEOUT}s "
            f"(upload throughput {kbps} KB/s to the ACR public endpoint); real template images are far larger"
        )
    if not pushed:
        shutil.rmtree(cfg_dir, ignore_errors=True)
        try:
            e2e_acr.delete_repo(ak, sk, ns, canary.repo)
        except Exception:  # noqa: BLE001
            pass
        pytest.skip(f"e2e_docker skipped: ACR push not usable from this host: {detail.replace(ns, '<ns>')}")
    print(f"[e2e_docker] canary push ok in {time.monotonic() - started:.0f}s")
    yield SimpleNamespace(prefix=prefix, shim=shim, builder=builder, ns=ns, ak=ak, sk=sk)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    try:
        e2e_acr.delete_repo(ak, sk, ns, f"{H.TEMPLATE_PREFIX}canary")
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(scope="module")
def built_template(docker_ctx, tracker, run):  # type: ignore[no-untyped-def]
    from easy_sandbox.api.docker_builder import ACRConfig
    from easy_sandbox.api.fc_template import wait_for_template_ready

    name = f"{H.TEMPLATE_PREFIX}srv-{H.RUN_ID[-6:]}"
    ctx = Path(tempfile.mkdtemp(prefix="e2e-template-ctx-"))
    server_src = H.REPO_ROOT / "server-sdk" / "src" / "easy_sandbox" / "server"
    shutil.copytree(
        server_src,
        ctx / "py" / "easy_sandbox" / "server",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (ctx / "Dockerfile").write_text(DOCKERFILE)
    (ctx / "app.py").write_text(APP)

    acr = ACRConfig(namespace=docker_ctx.ns, repo=name)
    tracker.template_names.append(name)
    tracker.local_images.append(f"{name}:e2e")
    tracker.local_images.append(acr.tagged_ref("e2e"))
    progress: list[str] = []
    result = run(
        docker_ctx.builder.build_and_register_official(
            ctx,
            acr,
            name=name,
            tag="e2e",
            cpu_count=2,
            memory_mb=2048,
            access_key_id=docker_ctx.ak,
            access_key_secret=docker_ctx.sk,
            on_progress=lambda m: progress.append(H.mask(m)),
        )
    )
    assert result.template_id, f"CreateTemplate returned no template id; progress={progress[-3:]}"
    tracker.template_ids.append(result.template_id)
    ready = wait_for_template_ready(
        result.template_id,
        access_key_id=docker_ctx.ak,
        access_key_secret=docker_ctx.sk,
        timeout=TEMPLATE_READY_TIMEOUT,
        poll_interval=10,
    )
    yield SimpleNamespace(name=name, template_id=result.template_id, ready=ready, progress=progress)
    shutil.rmtree(ctx, ignore_errors=True)
    try:
        e2e_acr.delete_repo(docker_ctx.ak, docker_ctx.sk, docker_ctx.ns, name)
    except Exception:  # noqa: BLE001
        pass


def test_build_push_and_create_official_template(built_template):  # type: ignore[no-untyped-def]
    status = built_template.ready.get("status") or {}
    state = status.get("state") if isinstance(status, dict) else status
    assert str(state).lower() == "ready"
    assert any("Template created" in m for m in built_template.progress)


@pytest.fixture(scope="module")
def custom_sandbox(built_template, run, tracker):  # type: ignore[no-untyped-def]
    sb = run(create_tracked(tracker, built_template.template_id, "custom-template", timeout=600))
    run(wait_envd_ready(sb, timeout=90))
    yield sb
    from conftest import _kill_quietly

    run(_kill_quietly(sb.id))


def test_sandbox_from_custom_template_serves_envd(run, custom_sandbox):  # type: ignore[no-untyped-def]
    assert run(custom_sandbox.commands.run("python3 --version")).stdout.startswith("Python 3")
    assert run(custom_sandbox.commands.run("cat /app/app.py")).exit_code == 0


@pytest.fixture(scope="module")
def custom_server(run, custom_sandbox):  # type: ignore[no-untyped-def]
    run(custom_sandbox.commands.run("nohup python3 /app/app.py >/tmp/e2e-server.log 2>&1 &", timeout=30))
    handle = ServerHandle(custom_sandbox)
    H.eventually(
        lambda: handle.get("/commands").status_code == 200,
        timeout=90,
        interval=3,
        what="custom-template server to serve /commands",
    )
    return handle


def test_server_sdk_endpoints_in_custom_template(custom_server):  # type: ignore[no-untyped-def]
    names = {c["name"] for c in custom_server.get("/commands").json()["commands"]}
    assert "echo_back" in names
    assert custom_server.post("/commands/echo_back", json={"message": "hi"}).json() == {
        "result": "e2e-custom:hi"
    }
    assert custom_server.get("/capabilities").json()["groups"]["file_ops"] is True
    assert custom_server.get("/system/info").json()["os"] == "Linux"


def test_sdk_custom_command_roundtrip_in_custom_template(run, custom_sandbox, custom_server):  # type: ignore[no-untyped-def]
    result = run(custom_sandbox.custom("echo_back", message="via-sdk"))
    assert result.value == "e2e-custom:via-sdk"
    assert asyncio.iscoroutinefunction(custom_sandbox.list_commands)
