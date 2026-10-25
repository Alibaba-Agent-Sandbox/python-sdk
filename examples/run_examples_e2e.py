#!/usr/bin/env python3
"""Run the SDK examples that can execute on this machine, and record the rest.

Cloud examples (``Sandbox.create`` against Alibaba Cloud, pip installs, a real
Codex binary) are not started. They are compiled, then marked as needing a
provider. Local examples must exit 0.

    python examples/run_examples_e2e.py
"""

from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
PY = sys.executable
# These call a real provider or install packages. Compiling them is the check
# this runner can do without a cloud account.
NEEDS_PROVIDER = [
    "examples/quickstart/03_web_service.py",
    "examples/quickstart/04_data_analysis.py",
    "examples/quickstart/05_decorator_usage.py",
    "examples/agents/codex_agent.py",
    "examples/agents/browser_automation.py",
    "examples/compat-demos/comparison.py",
    "examples/compat-demos/e2b_data_analysis.py",
    "examples/compat-demos/e2b_web_scraper.py",
    "examples/compat-demos/modal_compute.py",
    "examples/compat-demos/modal_data_analysis.py",
    "examples/compat-demos/e2e_capability_validation.py",
]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "ABX_SERVER_TOKEN",
        "ABX_SANDBOX_API_KEY",
        "E2B_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
    ):
        env.pop(name, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run(args: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"Example exceeded its {timeout}s deadline"
    return proc.returncode, proc.stdout


def _record(rows: list[tuple[str, str, str]], status: str, name: str, detail: str) -> None:
    rows.append((status, name, detail.replace("\n", " ")[:240]))
    print(f"[{status}] {name} — {detail.splitlines()[-1][:200] if detail else ''}", flush=True)


def compile_examples(rows: list[tuple[str, str, str]]) -> None:
    failed: list[str] = []
    for path in sorted(EXAMPLES.rglob("*.py")):
        if path.name == "run_examples_e2e.py":
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failed.append(f"{path.relative_to(ROOT)}: {exc.msg}")
    if failed:
        _record(rows, "fail", "py_compile examples", "; ".join(failed))
    else:
        _record(rows, "ok", "py_compile examples", "every example .py compiles")


def run_script(rows: list[tuple[str, str, str]], rel: str, *args: str, timeout: int = 60) -> None:
    code, out = _run([PY, str(ROOT / rel), *args], cwd=ROOT, env=_base_env(), timeout=timeout)
    _record(rows, "ok" if code == 0 else "fail", rel, out.strip() or f"exit {code}")


def run_local_process_examples(rows: list[tuple[str, str, str]]) -> None:
    env = _base_env()
    code, out = _run(
        [
            PY,
            "-m",
            "agent_sandbox.providers",
            "install",
            str(EXAMPLES / "providers" / "local-process"),
            "--force",
            "--yes",
        ],
        cwd=ROOT,
        env=env,
        timeout=60,
    )
    if code != 0:
        _record(rows, "fail", "install local-process provider", out.strip() or f"exit {code}")
        return
    env["ABX_PROVIDER"] = "local-process"
    for rel in ("examples/quickstart/01_hello.py", "examples/quickstart/02_file_ops.py"):
        code, out = _run([PY, str(ROOT / rel)], cwd=ROOT, env=env, timeout=60)
        _record(
            rows,
            "ok" if code == 0 else "fail",
            rel + " via local-process",
            out.strip() or f"exit {code}",
        )


def run_python_hello(rows: list[tuple[str, str, str]]) -> None:
    directory = EXAMPLES / "templates" / "python-hello"
    env = _base_env()
    env["ABX_SERVER_BASE_DIR"] = tempfile.mkdtemp(prefix="abx-hello-base-")
    env["ABX_SERVER_PORT"] = "0"
    # commands.py reads ABX_SERVER_PORT only as a default; call_api needs a real port.
    # Start on an ephemeral port by wrapping a tiny launcher.
    launcher = r"""
import os, socket, runpy
from pathlib import Path
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ["ABX_SERVER_PORT"] = str(port)
open(os.environ["ABX_PORT_FILE"], "w").write(str(port))
os.chdir(os.environ["ABX_TEMPLATE_DIR"])
runpy.run_path("commands.py", run_name="__main__")
"""
    port_file = Path(tempfile.mkstemp(prefix="abx-port-")[1])
    env["ABX_PORT_FILE"] = str(port_file)
    env["ABX_TEMPLATE_DIR"] = str(directory)
    proc = subprocess.Popen(
        [PY, "-c", launcher],
        cwd=directory,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for _ in range(50):
            if port_file.exists() and port_file.read_text().strip():
                break
            if proc.poll() is not None:
                log = proc.stdout.read() if proc.stdout else ""
                _record(
                    rows, "fail", "examples/templates/python-hello", log.strip() or "server exited"
                )
                return
            import time

            time.sleep(0.1)
        port = port_file.read_text().strip()
        import time
        import urllib.request

        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            _record(rows, "fail", "examples/templates/python-hello", "health timeout")
            return
        code, out = _run(
            [PY, str(directory / "call_api.py"), f"http://127.0.0.1:{port}"],
            cwd=directory,
            env=env,
            timeout=30,
        )
        _record(
            rows,
            "ok" if code == 0 else "fail",
            "examples/templates/python-hello/call_api.py",
            out.strip() or f"exit {code}",
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        port_file.unlink(missing_ok=True)


def run_agents_cli(rows: list[tuple[str, str, str]]) -> None:
    directory = EXAMPLES / "templates" / "agents-cli"
    env = _base_env()
    env["E2E_RUN_LLM"] = "0"
    env["ABX_SERVER_BASE_DIR"] = tempfile.mkdtemp(prefix="abx-agents-base-")
    env["ABX_AGENTS_PERSIST"] = "0"
    launcher = r"""
import os, socket, runpy, time
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
os.environ["ABX_SERVER_PORT"] = str(port)
open(os.environ["ABX_PORT_FILE"], "w").write(str(port))
os.chdir(os.environ["ABX_TEMPLATE_DIR"])
runpy.run_path("commands.py", run_name="__main__")
"""
    port_file = Path(tempfile.mkstemp(prefix="abx-agents-port-")[1])
    env["ABX_PORT_FILE"] = str(port_file)
    env["ABX_TEMPLATE_DIR"] = str(directory)
    proc = subprocess.Popen(
        [PY, "-c", launcher],
        cwd=directory,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        import time
        import urllib.request

        deadline = time.time() + 20
        port = ""
        while time.time() < deadline:
            if proc.poll() is not None:
                log = proc.stdout.read() if proc.stdout else ""
                _record(
                    rows, "fail", "examples/templates/agents-cli", log.strip() or "server exited"
                )
                return
            text = port_file.read_text().strip() if port_file.exists() else ""
            if text:
                port = text
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=1
                    ) as resp:
                        if resp.status == 200:
                            break
                except OSError:
                    pass
            time.sleep(0.1)
        else:
            log = ""
            if proc.stdout:
                proc.kill()
                log = proc.stdout.read() or ""
            _record(rows, "fail", "examples/templates/agents-cli", log.strip() or "health timeout")
            return
        child = env.copy()
        child["E2E_BASE_URL"] = f"http://127.0.0.1:{port}"
        child["ABX_AGENT_WORKDIR"] = env["ABX_SERVER_BASE_DIR"]
        code, out = _run([PY, str(directory / "e2e_test.py")], cwd=directory, env=child, timeout=40)
        _record(
            rows,
            "ok" if code == 0 else "fail",
            "examples/templates/agents-cli/e2e_test.py",
            out.strip() or f"exit {code}",
        )
        for script in ("hosted_codex.py", "hosted_qwen.py"):
            code, out = _run(
                [PY, str(EXAMPLES / "agents" / script), f"http://127.0.0.1:{port}"],
                cwd=EXAMPLES / "agents",
                env=child,
                timeout=40,
            )
            _record(
                rows,
                "ok" if code == 0 else "fail",
                f"examples/agents/{script}",
                out.strip() or f"exit {code}",
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        port_file.unlink(missing_ok=True)


def main() -> int:
    rows: list[tuple[str, str, str]] = []
    compile_examples(rows)
    run_script(rows, "examples/scenarios/agent_loop_local.py", timeout=40)
    run_script(rows, "examples/agents/local_files_and_session.py", timeout=40)
    run_script(rows, "examples/agents/complete_case.py", timeout=60)
    run_python_hello(rows)
    run_agents_cli(rows)
    run_local_process_examples(rows)
    for rel in NEEDS_PROVIDER:
        _record(
            rows,
            "needs-provider",
            rel,
            "not started here; it needs a sandbox provider or a live third-party API",
        )

    print("\n# example e2e")
    print("| status | example | detail |")
    print("|---|---|---|")
    for status, name, detail in rows:
        safe = detail.replace("|", "/")
        print(f"| {status} | `{name}` | {safe} |")
    failed = [row for row in rows if row[0] == "fail"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
