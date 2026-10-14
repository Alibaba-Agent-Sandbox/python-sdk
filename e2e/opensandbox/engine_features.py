#!/usr/bin/env python3
"""Exercise every OpenSandbox feature through the in-engine adapter.

The local server is ``http://127.0.0.1:8080`` unless ``ABX_OPENSANDBOX_BASE_URL``
is set. The API key is ``ABX_OPENSANDBOX_API_KEY`` or the local-up default
``local-dev-key`` (a throwaway dev key, not a credential).

Prints one PASS/FAIL line per feature and exits non-zero if any failed.
Sandboxes created here are killed before the script returns.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

BASE = os.environ.get("ABX_OPENSANDBOX_BASE_URL", "http://127.0.0.1:8080")
KEY = os.environ.get("ABX_OPENSANDBOX_API_KEY", "local-dev-key")


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            self.failed += 1
        line = f"[{'PASS' if ok else 'FAIL'}] {name}"
        if detail:
            line += f" — {detail}"
        print(line, flush=True)


async def _expect_unsupported(report: Report, name: str, coro) -> None:  # type: ignore[no-untyped-def]
    try:
        await coro
    except ProviderFeatureNotSupportedError as exc:
        report.add(name, exc.code == "E8004", exc.code)
        return
    except Exception as exc:
        report.add(name, False, f"{type(exc).__name__}: {exc}")
        return
    report.add(name, False, "call succeeded; expected E8004")


async def main() -> int:
    report = Report()
    sb = None
    try:
        sb = await Sandbox.create(
            provider="opensandbox",
            template="base",
            timeout=120,
            api_url=BASE,
            api_key=KEY,
        )
        report.add("lifecycle.create", bool(sb.id) and sb.provider == "opensandbox", sb.id)
    except Exception as exc:
        report.add("lifecycle.create", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc(), file=sys.stderr)
        return 1

    try:
        connected = await Sandbox.connect(sb.id, provider="opensandbox", api_url=BASE, api_key=KEY)
        report.add("lifecycle.connect", connected.id == sb.id)
        info = await connected.refresh_info()
        status = info.status.value if hasattr(info.status, "value") else str(info.status)
        report.add("lifecycle.get", info.sandbox_id == sb.id and status == "running", status)
        listed = await Sandbox.list(provider="opensandbox", api_url=BASE, api_key=KEY)
        report.add("lifecycle.list", any(item.sandbox_id == sb.id for item in listed), f"{len(listed)} rows")
        await sb.set_timeout(180)
        report.add("sandbox.timeout", True)
        await sb.pause()
        report.add("sandbox.pause", True)
        await sb.resume()
        report.add("sandbox.resume", True)

        result = await sb.commands.run("printf 'exec-ok\\n'")
        report.add("exec.run", result.exit_code == 0 and "exec-ok" in result.stdout, repr(result.stdout))

        chunks = [chunk async for chunk in sb.commands.stream("printf 'stream-ok\\n'")]
        text = "".join(chunk.data for chunk in chunks)
        report.add("exec.stream", "stream-ok" in text and any(chunk.exit_code == 0 for chunk in chunks))

        try:
            procs = await sb.commands.list()
            report.add("process.list", isinstance(procs, list), f"{len(procs)} processes")
        except Exception as exc:
            report.add("process.list", False, f"{type(exc).__name__}: {exc}")

        await sb.files.write("/tmp/abx-engine.txt", "file-ok\n")
        body = await sb.files.read("/tmp/abx-engine.txt")
        report.add("files.read-write", body == "file-ok\n", repr(body))
        info_row = await sb.files.get_info("/tmp/abx-engine.txt")
        report.add("files.stat", info_row.path.endswith("abx-engine.txt") and info_row.size >= 0)
        await sb.files.make_dir("/tmp/abx-engine-dir")
        names = [item.name for item in await sb.files.list("/tmp")]
        report.add("files.list", "abx-engine.txt" in names or "abx-engine-dir" in names, ",".join(names[:8]))
        await sb.files.move("/tmp/abx-engine.txt", "/tmp/abx-engine-moved.txt")
        moved = await sb.files.read("/tmp/abx-engine-moved.txt")
        report.add("files.move", moved == "file-ok\n")
        await sb.files.remove("/tmp/abx-engine-moved.txt")
        report.add("files.remove", not await sb.files.exists("/tmp/abx-engine-moved.txt"))

        try:
            url, _headers = await sb.network.resolve(8080)
            report.add("ports.url", bool(url), url[:80])
        except Exception as exc:
            report.add("ports.url", False, f"{type(exc).__name__}: {exc}")

        try:
            term = await sb.get_terminal(cols=80, rows=24)
            await term.send("echo $((40+2))\n")
            received = b""
            try:
                for _ in range(8):
                    piece = await term.receive(timeout=2)
                    received += piece if isinstance(piece, bytes) else piece.encode()
                    if b"42" in received:
                        break
            except Exception as exc:
                report.add("pty", False, f"{type(exc).__name__}: {exc}; got={received[:80]!r}")
            else:
                report.add("pty", b"42" in received, repr(received[:120]))
            await term.close()
        except Exception as exc:
            report.add("pty", False, f"{type(exc).__name__}: {exc}")

        async def _watch() -> None:
            reader = await sb.files.watch("/tmp")
            async for _event in reader:
                break

        await _expect_unsupported(report, "files.watch", _watch())
        await _expect_unsupported(
            report,
            "process.stdin",
            sb.commands.send_input(1, "x"),
        )

        await sb.kill()
        report.add("lifecycle.kill", True)
        await Sandbox.kill_by_id(sb.id, provider="opensandbox", api_url=BASE, api_key=KEY)
        report.add("lifecycle.kill-idempotent", True)
        sb = None
    except Exception as exc:
        report.add("runner", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        if sb is not None:
            try:
                await sb.kill()
            except Exception:
                pass
    print(f"failed={report.failed}", flush=True)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
