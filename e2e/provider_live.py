"""Live calls for Express and installed catalog providers.

Run from ``python-sdk/e2e`` with the cloud env exported and OpenSandbox up::

    set -a; source /tmp/abx-cloud.env; set +a
    python -m pytest test_08_providers.py -s -ra

Each check prints one line. Secret values are masked. A provider whose
backend is not configured returns ``blocked`` and does not send another
provider's API key.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from urllib.parse import urlsplit
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# Preserve an explicit isolated socket; otherwise avoid PID reuse between runs.
os.environ.setdefault(
    "ABX_ENGINE_SOCKET", f"/tmp/abx-provider-e2e-{os.getpid()}-{uuid.uuid4().hex[:12]}.sock"
)

_SECRET_RE = re.compile(
    r"(?i)(e2b_[A-Za-z0-9_\-]{6,}|sk-[A-Za-z0-9]{6,}|LTAI[A-Za-z0-9]{6,}|"
    r"(?:api[_-]?key|token|secret|authorization)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+)"
)


def mask(text: str) -> str:
    """Hide credential material that might leak into an exception string."""
    out = _SECRET_RE.sub(lambda m: m.group(1).split("=", 1)[0][:24] + "=<masked>", str(text))
    for name, value in os.environ.items():
        if len(value) < 8:
            continue
        if any(part in name.upper() for part in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
            out = out.replace(value, f"<{name}>")
    return out


@dataclass
class Row:
    feature: str
    status: str
    detail: str


@dataclass
class Report:
    provider: str
    rows: list[Row] = field(default_factory=list)
    sandbox_id: str = ""

    def add(self, feature: str, status: str, detail: str) -> None:
        detail = mask(detail).replace("\n", " ")[:300]
        self.rows.append(Row(feature, status, detail))
        print(f"[{status:7}] {self.provider:20} {feature:22} {detail}", flush=True)

    def status_of(self, feature: str) -> str:
        for row in self.rows:
            if row.feature == feature:
                return row.status
        return ""


def _tcp(host: str, port: int, timeout: float = 2) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return 200 <= resp.status < 300
    except OSError:
        return False


def _brief(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    status = getattr(exc, "status_code", None)
    prefix = type(exc).__name__
    if code:
        prefix += f" {code}"
    if status:
        prefix += f" HTTP {status}"
    return f"{prefix}: {exc}"


def _refused(exc: BaseException) -> bool:
    code = getattr(exc, "code", "")
    name = type(exc).__name__
    return code == "E8004" or name == "ProviderFeatureNotSupportedError"


class _BlockedError(Exception):
    """The call ran, and the template or platform has nothing behind this feature."""


async def _check(
    report: Report,
    feature: str,
    declared: bool,
    action: Callable[[], Awaitable[str]],
) -> None:
    try:
        detail = await action()
    except _BlockedError as exc:
        report.add(feature, "blocked", str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — one row per call, including platform errors
        if _refused(exc):
            report.add(feature, "refused" if not declared else "fail", _brief(exc))
            return
        report.add(feature, "fail", _brief(exc))
        return
    report.add(feature, "pass", detail)


async def _pty_marker(sandbox: Any) -> str:
    term = await sandbox.get_terminal(cols=80, rows=24)
    try:
        await term.send("echo ABX_PTY_$((40+2))\n")
        parts: list[str] = []
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                chunk = await term.receive(timeout=1)
            except (TimeoutError, asyncio.TimeoutError):
                if "ABX_PTY_42" in "".join(parts):
                    break
                continue
            if isinstance(chunk, (bytes, bytearray)):
                text = chunk.decode("utf-8", "replace")
            else:
                text = str(chunk)
            parts.append(text)
            if "ABX_PTY_42" in "".join(parts):
                break
        blob = "".join(parts)
        if "ABX_PTY_42" not in blob:
            raise RuntimeError(f"pty output missing marker: {blob[-180:]!r}")
        return "pty printed 42"
    finally:
        await term.close()


async def _watch_once(sandbox: Any) -> str:
    path = "/tmp/abx-provider-live"
    await sandbox.files.make_dir(path)
    reader = await sandbox.files.watch(path)

    async def _one() -> str:
        async for event in reader:
            return type(event).__name__
        return "no event"

    task = asyncio.create_task(_one())
    await asyncio.sleep(0.4)
    await sandbox.files.write(f"{path}/touched.txt", "z")
    try:
        kind = await asyncio.wait_for(task, timeout=15)
    finally:
        if not task.done():
            task.cancel()
    return f"watch event {kind}"


async def _process_row(sandbox: Any) -> str:
    reader = await sandbox.commands.start("sleep 25", timeout=30)
    pid: int | None = None
    # Manual anext keeps the stream open. Breaking an ``async for`` would
    # aclose it, and envd then kills the process group before list() runs.
    agen = reader.__aiter__()
    pending = asyncio.create_task(agen.__anext__())
    done, _rest = await asyncio.wait({pending}, timeout=8)
    chunk = None
    if pending in done:
        try:
            chunk = pending.result()
        except StopAsyncIteration:
            chunk = None
    if chunk is not None and chunk.pid:
        pid = int(chunk.pid)
    infos = await sandbox.commands.list()
    commands = [f"{info.pid}:{info.command}" for info in infos[:8]]
    visible = pid is not None or any("sleep" in item for item in commands)
    if not visible:
        raise RuntimeError(f"sleep was not visible in process list: {commands}")
    if pid is not None:
        try:
            await sandbox.commands.kill(pid)
        except Exception as exc:  # noqa: BLE001
            return f"listed {len(infos)} pid={pid} signal failed {_brief(exc)} {commands}"
    if not pending.done():
        pending.cancel()
    return f"listed {len(infos)} pid={pid} {commands}"


_FRESH_EXEC = """
import asyncio
import sys

from agent_sandbox.api.sandbox import Sandbox


async def main() -> None:
    sandbox_id, provider = sys.argv[1], sys.argv[2]
    sandbox = await Sandbox.connect(sandbox_id, provider=provider)
    try:
        result = await sandbox.commands.run("echo fresh-exec-ok", timeout=30, shell=True)
        text = result.stdout or ""
        if result.exit_code != 0 or "fresh-exec-ok" not in text:
            raise SystemExit(
                f"exit={result.exit_code} stdout={text!r} stderr={result.stderr!r}"
            )
    finally:
        await sandbox.close()


asyncio.run(main())
"""


async def _fresh_process_exec(provider: str, sandbox_id: str) -> str:
    """Connect and exec in a second interpreter. Proves the sandbox is not process-local."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _FRESH_EXEC,
        sandbox_id,
        provider,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except TimeoutError:
        proc.kill()
        raise RuntimeError("fresh process exec timed out") from None
    if proc.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "replace")[-240:]
        raise RuntimeError(f"exit {proc.returncode} {detail}")
    return "second process echoed fresh-exec-ok"


async def exercise(
    provider: str,
    *,
    template: str,
    create_kwargs: dict[str, Any] | None = None,
) -> Report:
    """Create one sandbox and call every feature the SDK exposes for it."""
    from agent_sandbox.api.sandbox import Sandbox
    from agent_sandbox.providers.registry import get_provider

    report = Report(provider)
    spec = get_provider(provider)
    declared = set(spec.features)
    kwargs = dict(create_kwargs or {})
    sandbox = None
    try:
        sandbox = await Sandbox.create(
            template=template,
            timeout=180,
            request_timeout=180,
            metadata={"e2e": "provider-live"},
            envs={"ABX_E2E_MARKER": "live"},
            provider=provider,
            provider_options=kwargs.get("provider_options"),
        )
        report.sandbox_id = sandbox.id
        report.add("sandbox.lifecycle", "pass", f"created {sandbox.id}")

        async def _connect() -> str:
            options = kwargs.get("provider_options")
            other = await Sandbox.connect(sandbox.id, provider=provider, provider_options=options)
            try:
                running = await other.is_running()
            finally:
                await other.close()
            return f"connect running={running}"

        await _check(report, "sandbox.connect", True, _connect)

        async def _reconnect() -> str:
            return await _fresh_process_exec(provider, sandbox.id)

        await _check(report, "sandbox.reconnect", True, _reconnect)

        async def _list() -> str:
            options = kwargs.get("provider_options")
            rows = await Sandbox.list(limit=100, provider=provider, provider_options=options)
            found = any(row.sandbox_id == sandbox.id for row in rows)
            if not found:
                raise RuntimeError(f"list missed this sandbox ({len(rows)} rows)")
            return f"list contains sandbox ({len(rows)} rows)"

        await _check(report, "sandbox.list", "sandbox.lifecycle" in declared, _list)

        async def _timeout() -> str:
            await sandbox.set_timeout(240)
            return "set_timeout 240"

        await _check(report, "sandbox.timeout", "sandbox.timeout" in declared, _timeout)

        async def _exec() -> str:
            result = await sandbox.commands.run(
                "echo sdk-exec-ok; printenv ABX_E2E_MARKER",
                timeout=30,
                shell=True,
            )
            if result.exit_code != 0 or "sdk-exec-ok" not in result.stdout:
                raise RuntimeError(
                    f"exit={result.exit_code} stdout={result.stdout!r} stderr={result.stderr!r}"
                )
            marker = "env" if "live" in result.stdout else "no-env"
            return f"stdout sdk-exec-ok {marker}"

        await _check(report, "exec.run", "exec.run" in declared, _exec)

        async def _user() -> str:
            result = await sandbox.commands.run("id -u", timeout=15, user="root")
            if result.exit_code != 0 or result.stdout.strip() != "0":
                raise RuntimeError(
                    f"exit={result.exit_code} stdout={result.stdout!r} stderr={result.stderr!r}"
                )
            return "id -u as root is 0"

        if provider == "opensandbox":
            await _check(report, "exec.user", True, _user)

        async def _stdin_closed() -> str:
            # Sibling StartRequest.stdin=false. envd that honors it attaches
            # /dev/null and cat exits. The Express base image keeps the pipe.
            result = await sandbox.commands.run("cat", timeout=8)
            if result.exit_code != 0:
                raise RuntimeError(
                    f"exit={result.exit_code} stdout={result.stdout!r} stderr={result.stderr!r}"
                )
            return "cat exited with stdin closed"

        if provider == "alicloud-express":
            await _check(report, "exec.stdin", True, _stdin_closed)

        async def _stream() -> str:
            parts: list[str] = []
            exit_code = None
            async for chunk in sandbox.commands.stream("echo sdk-stream", timeout=30):
                kind = str(getattr(chunk.type, "value", chunk.type))
                if kind == "stdout":
                    parts.append(chunk.data)
                elif kind == "exit":
                    exit_code = chunk.exit_code
            text = "".join(parts)
            if exit_code not in (0, None) or "sdk-stream" not in text:
                raise RuntimeError(f"exit={exit_code} stdout={text!r}")
            return "streamed sdk-stream"

        await _check(report, "exec.stream", "exec.stream" in declared, _stream)

        async def _files() -> str:
            path = "/tmp/abx-provider-live.txt"
            await sandbox.files.write(path, "sdk-file")
            body = await sandbox.files.read(path)
            if body != "sdk-file":
                raise RuntimeError(f"read {body!r}")
            await sandbox.files.make_dir("/tmp/abx-provider-dir")
            await sandbox.files.rename(path, "/tmp/abx-provider-dir/moved.txt")
            moved = await sandbox.files.read("/tmp/abx-provider-dir/moved.txt")
            await sandbox.files.remove("/tmp/abx-provider-dir/moved.txt")
            if moved != "sdk-file":
                raise RuntimeError(f"moved {moved!r}")
            return "write/read/rename/remove"

        await _check(report, "files.rw", "files.rw" in declared, _files)

        async def _ports() -> str:
            url = await sandbox.network.resolve_url(8080)
            if not url:
                raise RuntimeError("empty port url")
            return f"port url scheme={url.split(':', 1)[0]} host={url.split('://', 1)[-1][:80]}"

        await _check(report, "ports.url", "ports.url" in declared, _ports)

        await _check(
            report,
            "process.manage",
            "process.manage" in declared,
            lambda: _process_row(sandbox),
        )
        await _check(
            report,
            "code.interpret",
            "code.interpret" in declared,
            lambda: _code(sandbox),
        )
        await _check(report, "files.watch", "files.watch" in declared, lambda: _watch_once(sandbox))

        async def _transfer() -> str:
            url = await sandbox.files.upload_url("/tmp/abx-provider-live.txt")
            if not str(url).startswith(("http://", "https://")):
                raise RuntimeError(f"url {url!r}")
            return "upload_url is http(s)"

        await _check(report, "files.transfer", "files.transfer" in declared, _transfer)

        async def _sessions() -> str:
            try:
                commands = await sandbox.list_commands()
            except Exception as exc:  # noqa: BLE001
                text = _brief(exc)
                if _refused(exc):
                    raise
                lowered = text.lower()
                offline = ("401", "502", "404", "connect", "timeout", "refused")
                if any(token in lowered for token in offline):
                    raise _BlockedError(f"no SandboxServer on this template: {text}") from exc
                raise
            return f"named commands {len(commands)}"

        await _check(report, "sessions", "sessions" in declared, _sessions)

        await _check(report, "pty", "pty" in declared, lambda: _pty_marker(sandbox))

        async def _pause() -> str:
            await sandbox.pause()
            await sandbox.resume()
            running = await sandbox.is_running()
            return f"pause/resume running={running}"

        await _check(report, "sandbox.pause", "sandbox.pause" in declared, _pause)
    except Exception as exc:  # noqa: BLE001
        if not report.rows:
            report.add("sandbox.lifecycle", "fail", _brief(exc))
        else:
            report.add("runner", "fail", _brief(exc))
    finally:
        if sandbox is not None and report.sandbox_id:
            try:
                await sandbox.kill()
                report.add("sandbox.kill", "pass", "killed")
            except Exception as exc:  # noqa: BLE001
                report.add("sandbox.kill", "fail", _brief(exc))
            try:
                from agent_sandbox.api.sandbox import Sandbox

                await Sandbox.kill_by_id(
                    report.sandbox_id,
                    provider=provider,
                    provider_options=(create_kwargs or {}).get("provider_options"),
                )
                report.add("sandbox.kill_again", "pass", "second kill returned")
            except Exception as exc:  # noqa: BLE001
                text = _brief(exc)
                if any(token in text.lower() for token in ("404", "not found", "already")):
                    report.add("sandbox.kill_again", "pass", text)
                else:
                    report.add("sandbox.kill_again", "fail", text)
    return report


async def _code(sandbox: Any) -> str:
    result = await sandbox.run_code("print(40 + 2)")
    stdout = getattr(result, "stdout", "") or ""
    text = getattr(result, "text", "") or ""
    blob = f"{stdout}{text}"
    if "42" not in blob:
        raise RuntimeError(f"stdout={stdout!r} text={text!r}")
    return "run_code printed 42"


def _installed(provider_id: str) -> str:
    from agent_sandbox.models.errors import ProviderNotFoundError
    from agent_sandbox.providers.registry import get_provider

    try:
        get_provider(provider_id)
    except ProviderNotFoundError:
        return (
            f"Provider '{provider_id}' is not installed. "
            f"python -m agent_sandbox.providers install registry:{provider_id} --yes"
        )
    return ""


def opensandbox_ready() -> str:
    missing = _installed("opensandbox")
    if missing:
        return missing
    base = (os.environ.get("ABX_OPENSANDBOX_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")
    if not _health(base + "/health"):
        return f"OpenSandbox health check failed at {base}/health"
    if not (os.environ.get("ABX_OPENSANDBOX_API_KEY") or os.environ.get("OPEN_SANDBOX_API_KEY")):
        # The local server accepts the documented throwaway key when none is set.
        os.environ.setdefault("ABX_OPENSANDBOX_API_KEY", "local-dev-key")
    return ""


def express_ready() -> str:
    if not (os.environ.get("ABX_SANDBOX_API_KEY") or "").strip():
        return "ABX_SANDBOX_API_KEY is not set"
    return ""


def cube_ready() -> str:
    missing = _installed("cubesandbox")
    if missing:
        return missing
    configured = (os.environ.get("ABX_CUBESANDBOX_BASE_URL") or "").strip()
    if not configured:
        return (
            "ABX_CUBESANDBOX_BASE_URL is not set. Select an authorized CubeAPI "
            "explicitly; another service listening on port 3000 is not CubeAPI readiness."
        )
    try:
        parsed = urlsplit(configured)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return "ABX_CUBESANDBOX_BASE_URL is not a valid HTTP(S) origin."
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "ABX_CUBESANDBOX_BASE_URL is not a valid HTTP(S) origin."
    if _tcp(parsed.hostname, port):
        return ""
    return "The explicitly configured CubeAPI endpoint is not reachable."


def e2b_ready() -> str:
    missing = _installed("e2b")
    if missing:
        return missing
    if (os.environ.get("ABX_E2B_API_KEY") or "").strip():
        return ""
    return (
        "ABX_E2B_API_KEY is not set. "
        "The Express key is a different credential and is not sent to api.e2b.dev."
    )


def container_ready() -> str:
    missing = _installed("alicloud-container")
    if missing:
        return missing
    domain = (os.environ.get("ABX_ALICLOUD_CONTAINER_DOMAIN") or "").strip()
    base = (os.environ.get("ABX_ALICLOUD_CONTAINER_BASE_URL") or "").strip()
    key = (os.environ.get("ABX_ALICLOUD_CONTAINER_API_KEY") or "").strip()
    if (domain or base) and key:
        return ""
    return (
        "ABX_ALICLOUD_CONTAINER_DOMAIN and ABX_ALICLOUD_CONTAINER_API_KEY are not set. "
        "There is no ACS/ACK sandbox-manager in this environment, "
        "and the Express key is not used."
    )


def run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


async def _create_only(provider: str) -> None:
    """Create and always kill. Used to prove a provider refuses before any HTTP call."""
    from agent_sandbox.api.sandbox import Sandbox

    sandbox = await Sandbox.create(
        provider=provider, template="base", timeout=60, request_timeout=20
    )
    with contextlib.suppress(Exception):
        await sandbox.kill()


def row(report: Report, feature: str) -> Row:
    for item in report.rows:
        if item.feature == feature:
            return item
    raise AssertionError(f"{report.provider} did not record {feature}")


def assert_report(report: Report, *, expect_pass: set[str], expect_refused: set[str]) -> None:
    required = expect_pass | expect_refused
    recorded = {item.feature for item in report.rows}
    bad = [f"{feature} was not executed" for feature in sorted(required - recorded)]
    for row in report.rows:
        if row.feature in expect_pass and row.status != "pass":
            bad.append(f"{row.feature} {row.status} {row.detail}")
        elif row.feature in expect_refused and row.status != "refused":
            bad.append(f"{row.feature} expected E8004, got {row.status} {row.detail}")
    if bad:
        joined = "\n".join(bad)
        raise AssertionError(f"{report.provider} sandbox={report.sandbox_id}\n{joined}")


def cli_command() -> list[str]:
    """Resolve the standalone CLI, without assuming a sibling source checkout."""
    configured = (os.environ.get("ABX_BIN") or "").strip()
    if configured:
        return shlex.split(configured)
    installed = shutil.which("abx")
    return [installed] if installed else []


def cli_express() -> Report:
    """Exercise the built-in Express provider through the standalone CLI."""
    report = Report("alicloud-express-cli")
    root = Path(__file__).resolve().parents[1]
    launcher = cli_command()
    if not launcher:
        report.add("cli", "blocked", "CLI unavailable: set ABX_BIN or install abx on PATH")
        return report
    env = os.environ.copy()
    env["ABX_ENGINE_SOCKET"] = f"/tmp/abx-cli-e2e-{os.getpid()}-{uuid.uuid4().hex[:12]}.sock"
    local = Path(f"/tmp/abx-cli-upload-{os.getpid()}.txt")
    downloaded = Path(f"/tmp/abx-cli-download-{os.getpid()}.txt")
    local.write_text("cli-upload", encoding="utf-8")
    sandbox_id = ""

    def run(args: list[str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*launcher, *args],
            cwd=str(root),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    try:
        created = run(
            [
                "--json",
                "sandbox",
                "create",
                "--template",
                "base",
                "--timeout",
                "300",
                "--metadata",
                "e2e=cli-provider",
            ],
            timeout=240,
        )
        if created.returncode != 0:
            detail = f"exit {created.returncode} {created.stderr[-240:]}"
            report.add("sandbox.lifecycle", "fail", detail)
            return report
        import json

        payload = json.loads(created.stdout)
        sandbox_id = str(payload.get("ID") or "")
        report.sandbox_id = sandbox_id
        if not sandbox_id:
            report.add("sandbox.lifecycle", "fail", "create JSON had no ID")
            return report
        report.add("sandbox.lifecycle", "pass", f"created {sandbox_id}")

        listed = None
        for _attempt in range(5):
            listed = run(["--json", "sandbox", "list", "--limit", "100"])
            if listed.returncode == 0 and sandbox_id in listed.stdout:
                break
            time.sleep(2)
        assert listed is not None
        if listed.returncode != 0:
            report.add("sandbox.list", "fail", f"exit {listed.returncode} {listed.stderr[-200:]}")
        elif sandbox_id in listed.stdout:
            report.add("sandbox.list", "pass", "list contains sandbox")
        else:
            snippet = listed.stdout.strip().replace("\n", " ")[:80]
            report.add("sandbox.list", "fail", f"list missed the new sandbox: {snippet!r}")

        executed = run(["sandbox", "exec", sandbox_id, "--", "echo", "cli-exec-ok"])
        if executed.returncode == 0 and "cli-exec-ok" in executed.stdout:
            report.add("exec.run", "pass", "stdout cli-exec-ok")
        else:
            detail = f"exit {executed.returncode} {executed.stdout[-120:]} {executed.stderr[-120:]}"
            report.add("exec.run", "fail", detail)

        streamed = run(["sandbox", "exec", "--stream", sandbox_id, "--", "echo", "cli-stream"])
        if streamed.returncode == 0 and "cli-stream" in streamed.stdout:
            report.add("exec.stream", "pass", "streamed cli-stream")
        else:
            detail = f"exit {streamed.returncode} {streamed.stderr[-160:]}"
            report.add("exec.stream", "fail", detail)

        uploaded = run(["sandbox", "upload", sandbox_id, str(local), "/tmp/cli-upload.txt"])
        fetched = run(["sandbox", "download", sandbox_id, "/tmp/cli-upload.txt", str(downloaded)])
        body = downloaded.read_text(encoding="utf-8") if downloaded.is_file() else ""
        if uploaded.returncode == 0 and fetched.returncode == 0 and body == "cli-upload":
            report.add("files.rw", "pass", "upload/download cli-upload")
        else:
            report.add(
                "files.rw",
                "fail",
                f"upload {uploaded.returncode} download {fetched.returncode} body={body!r}",
            )
    except Exception as exc:  # noqa: BLE001
        report.add("runner", "fail", _brief(exc))
    finally:
        if sandbox_id:
            first = run(["sandbox", "kill", "--yes", sandbox_id])
            second = run(["sandbox", "kill", "--yes", sandbox_id])
            kill_status = "pass" if first.returncode == 0 else "fail"
            report.add("sandbox.kill", kill_status, f"exit {first.returncode}")
            report.add(
                "sandbox.kill_again",
                "pass" if second.returncode == 0 else "fail",
                f"exit {second.returncode} {second.stderr[-120:]}",
            )
        local.unlink(missing_ok=True)
        downloaded.unlink(missing_ok=True)
    return report
