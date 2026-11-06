"""Independent cross-process PostgreSQL/SSE deletion and slow-reader checks.

No cloud/model calls. Barriers only suspend real event fetch or socket writes;
all ownership, authorization, transactions and session gates are product code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import socket
import subprocess  # nosec B404 - owns fixture Gateway child processes
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pgserver

import agent_sandbox.managed_agents.service as managed_service
from agent_sandbox.managed_agents import ManagedConfig, ManagedService, ManagedStore
from agent_sandbox.managed_agents.http import TokenAuthenticator, make_server

SOURCE = Path(managed_service.__file__).parent


def hashes():
    return {
        name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
        for name in ("store.py", "service.py", "http.py")
    }


def record(path, kind, **extra):
    with Path(path).open("a") as stream:
        stream.write(json.dumps({"kind": kind, "ns": time.monotonic_ns(), **extra}) + "\n")


def wait_file(path, timeout=4):
    end = time.monotonic() + timeout
    while not Path(path).exists():
        if time.monotonic() > end:
            raise RuntimeError("barrier_deadline")
        time.sleep(0.01)


def child(file):
    doc = json.loads(Path(file).read_text())
    service = ManagedService(
        ManagedStore(doc["database"], doc["application"]), ManagedConfig.from_dict(doc["config"])
    )
    barrier = doc.get("barrier")
    original_events = service.events
    first_fetch = True

    def events(*args, **kwargs):
        nonlocal first_fetch
        rows = original_events(*args, **kwargs)
        record(
            doc["log"],
            "event_fetch",
            count=len(rows),
            text_bytes=sum(len(r.get("delta", "")) for r in rows),
        )
        if barrier == "fetch" and first_fetch:
            first_fetch = False
            Path(doc["ready"]).touch()
            wait_file(doc["release"], 8)
        return rows

    service.events = events
    original_handle = service.handle

    def handle(owner, method, path, *args, **kwargs):
        result = original_handle(owner, method, path, *args, **kwargs)
        if method == "DELETE" and path.startswith("/v1/agents/sessions/"):
            record(doc["log"], "delete_committed", status=result[0])
        return result

    service.handle = handle
    auth = TokenAuthenticator(lambda: json.loads(Path(doc["auth"]).read_text()))
    server = make_server(service, auth, port=0, write_timeout=0.5, max_frame_bytes=1048576)
    handler = server.RequestHandlerClass
    first_write = True

    class Writer:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def write(self, data):
            nonlocal first_write
            prefix, separator, body = data.partition(b"\r\n")
            frame = bool(
                separator
                and prefix
                and all(byte in b"0123456789abcdefABCDEF" for byte in prefix)
                and body.endswith(b"\r\n")
                and int(prefix, 16) == len(body) - 2
                and body.startswith(b"id: ")
            )
            if frame and barrier == "write" and first_write:
                first_write = False
                Path(doc["ready"]).touch()
                wait_file(doc["release"], 8)
            if frame:
                record(doc["log"], "frame_write_start", bytes=len(data))
            try:
                result = self.wrapped.write(data)
            except OSError:
                if frame:
                    record(doc["log"], "frame_write_failed", bytes=len(data))
                raise
            if frame:
                record(doc["log"], "frame_enqueued", bytes=len(data))
            return result

    original_setup = handler.setup

    def setup(self):
        original_setup(self)
        self.wfile = Writer(self.wfile)

    handler.setup = setup
    print(json.dumps({"port": server.server_port}), flush=True)
    server.serve_forever()


def rows(path):
    return (
        [json.loads(line) for line in Path(path).read_text().splitlines()]
        if Path(path).exists()
        else []
    )


def main(output=None):
    result = {
        "scope": "independent_real_postgresql_two_gateway_processes",
        "cloud": False,
        "model": False,
        "tests": [],
        "source_before": hashes(),
    }
    processes = []
    pg = None
    with tempfile.TemporaryDirectory(prefix="managed-sse-pg-review-") as raw:
        root = Path(raw)
        try:
            pg = pgserver.get_server(root / "pgdata", cleanup_mode="delete")
            database = pg.get_uri()
            application = "independent-sse-review"
            config = {
                "revision": "review",
                "applicationId": application,
                "template": "unused",
                "models": {"review-model": "qwen-code"},
            }
            service = ManagedService(
                ManagedStore(database, application), ManagedConfig.from_dict(config)
            )
            token = os.urandom(32).hex()
            auth = root / "auth.json"
            auth.write_text(
                json.dumps(
                    {
                        "tokens": [
                            {
                                "sha256": hashlib.sha256(token.encode()).hexdigest(),
                                "owner": "review-owner",
                                "scopes": ["agents:read", "agents:write"],
                            }
                        ]
                    }
                )
            )
            auth.chmod(0o600)
            headers = {"Authorization": "Bearer " + token}

            def session():
                return service.handle(
                    "review-owner",
                    "POST",
                    "/v1/agents/sessions",
                    {"agent": {"model": "review-model"}},
                )[1]["id"]

            def spawn(label, barrier=None):
                document = {
                    "database": database,
                    "application": application,
                    "config": config,
                    "auth": str(auth),
                    "log": str(root / (label + ".log")),
                    "barrier": barrier,
                    "ready": str(root / (label + ".ready")),
                    "release": str(root / (label + ".release")),
                }
                file = root / (label + ".json")
                file.write_text(json.dumps(document))
                file.chmod(0o600)
                errors = (root / (label + ".stderr")).open("w")
                proc = subprocess.Popen(  # nosec B603 - this script, Python argv, no shell
                    [sys.executable, __file__, "--child", str(file)],
                    stdout=subprocess.PIPE,
                    stderr=errors,
                    text=True,
                )
                processes.append(proc)
                if not select.select([proc.stdout], [], [], 10)[0]:
                    raise RuntimeError("gateway_start_deadline")
                port = json.loads(proc.stdout.readline())["port"]
                return "http://127.0.0.1:" + str(port), document

            controller, control_doc = spawn("controller")

            def delete(sid):
                with httpx.Client(timeout=5, trust_env=False) as client:
                    return client.delete(controller + "/v1/agents/sessions/" + sid, headers=headers)

            def consume(base, sid, out):
                try:
                    with (
                        httpx.Client(timeout=4, trust_env=False) as client,
                        client.stream(
                            "GET",
                            base + "/v1/agents/sessions/" + sid + "/events?after=0",
                            headers=headers,
                        ) as response,
                    ):
                        out["status"] = response.status_code
                        for line in response.iter_lines():
                            if line.startswith("data:"):
                                out.setdefault("events", []).append(json.loads(line[5:])["type"])
                except Exception as error:
                    out["closed_as"] = type(error).__name__

            # Real fetch precedes DELETE, but frame admission occurs after deletion.
            sid = session()
            base, doc = spawn("prefetch", "fetch")
            out = {}
            stream = threading.Thread(target=consume, args=(base, sid, out), daemon=True)
            stream.start()
            wait_file(doc["ready"])
            response = delete(sid)
            Path(doc["release"]).touch()
            stream.join(3)
            writes = rows(doc["log"])
            ok = response.status_code == 200 and not any(
                r["kind"] == "frame_enqueued" for r in writes
            )
            result["tests"].append(
                {
                    "name": "prefetched_batch_deleted_in_other_process",
                    "passed": ok,
                    "delete_status": response.status_code,
                    "enqueued_frames": sum(r["kind"] == "frame_enqueued" for r in writes),
                    "stream_status": out.get("status"),
                }
            )
            # Pause an admitted frame while holding only its Session gate.
            sid = session()
            other = session()
            base, doc = spawn("admitted", "write")
            out = {}
            stream = threading.Thread(target=consume, args=(base, sid, out), daemon=True)
            stream.start()
            wait_file(doc["ready"])
            deleted = {}

            def deleting():
                start = time.monotonic()
                response = delete(sid)
                deleted.update(status=response.status_code, seconds=time.monotonic() - start)

            deletion = threading.Thread(target=deleting)
            deletion.start()
            time.sleep(0.15)
            pending = deletion.is_alive()
            start = time.monotonic()
            with httpx.Client(timeout=2, trust_env=False) as client:
                other_status = client.get(
                    controller + "/v1/agents/sessions/" + other, headers=headers
                ).status_code
            other_seconds = time.monotonic() - start
            Path(doc["release"]).touch()
            deletion.join(4)
            stream.join(3)
            committed = [
                r["ns"] for r in rows(control_doc["log"]) if r["kind"] == "delete_committed"
            ][-1]
            enqueued = [r["ns"] for r in rows(doc["log"]) if r["kind"] == "frame_enqueued"]
            ok = (
                pending
                and deleted.get("status") == 200
                and other_status == 200
                and other_seconds < 1
                and bool(enqueued)
                and max(enqueued) < committed
            )
            result["tests"].append(
                {
                    "name": "inflight_frame_orders_with_cross_process_delete",
                    "passed": ok,
                    "delete_waited_for_session_gate": pending,
                    "delete_status": deleted.get("status"),
                    "unrelated_session_status": other_status,
                    "unrelated_session_seconds": round(other_seconds, 3),
                    "all_enqueues_before_delete_commit": bool(enqueued)
                    and max(enqueued) < committed,
                }
            )
            # A real TCP peer accepts headers and then stops consuming large frames.
            sid = session()
            other = session()
            with service.store.transaction() as tx:
                current = tx.get(sid)
                for index in range(12):
                    tx.event(
                        current,
                        "agent.session.output_text.delta",
                        {"delta": "x" * 900000, "test_index": index},
                    )
            base, doc = spawn("slow")
            port = int(base.rsplit(":", 1)[1])
            peer = socket.socket()
            peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
            peer.settimeout(3)
            peer.connect(("127.0.0.1", port))
            peer.sendall(
                (
                    "GET /v1/agents/sessions/"
                    + sid
                    + "/events?after=0 HTTP/1.1\r\nHost: 127.0.0.1:"
                    + str(port)
                    + "\r\nAuthorization: Bearer "
                    + token
                    + "\r\nUser-Agent: independent-sse-review\r\n\r\n"
                ).encode()
            )
            header = b""
            while not header.endswith(b"\r\n\r\n"):
                header += peer.recv(1)
            # Wait for a genuinely blocked large socket write, rather than racing
            # deletion against the initial multi-megabyte database read.
            blocked = False
            until = time.monotonic() + 4
            while time.monotonic() < until:
                records = rows(doc["log"])
                started = sum(
                    r["kind"] == "frame_write_start" and r["bytes"] > 800000 for r in records
                )
                ended = sum(
                    r["kind"] in {"frame_enqueued", "frame_write_failed"} and r["bytes"] > 800000
                    for r in records
                )
                if started > ended:
                    time.sleep(0.08)
                    records = rows(doc["log"])
                    now_ended = sum(
                        r["kind"] in {"frame_enqueued", "frame_write_failed"}
                        and r["bytes"] > 800000
                        for r in records
                    )
                    if started > now_ended:
                        blocked = True
                        break
                time.sleep(0.01)
            start = time.monotonic()
            with httpx.Client(timeout=2, trust_env=False) as client:
                other_status = client.get(
                    controller + "/v1/agents/sessions/" + other, headers=headers
                ).status_code
            other_seconds = time.monotonic() - start
            start = time.monotonic()
            response = delete(sid)
            delete_seconds = time.monotonic() - start
            time.sleep(0.6)
            peer.close()
            records = rows(doc["log"])
            failed = sum(r["kind"] == "frame_write_failed" for r in records)
            committed = [
                r["ns"] for r in rows(control_doc["log"]) if r["kind"] == "delete_committed"
            ][-1]
            after = sum(r["kind"] == "frame_enqueued" and r["ns"] > committed for r in records)
            ok = (
                blocked
                and response.status_code == 200
                and delete_seconds < 3
                and other_status == 200
                and other_seconds < 1
                and failed > 0
                and after == 0
            )
            result["tests"].append(
                {
                    "name": "saturated_reader_is_bounded_and_other_session_progresses",
                    "passed": ok,
                    "blocked_large_write_observed": blocked,
                    "stream_status_line": header.split(b"\r\n", 1)[0].decode(),
                    "delete_status": response.status_code,
                    "delete_seconds": round(delete_seconds, 3),
                    "unrelated_session_seconds": round(other_seconds, 3),
                    "failed_bounded_writes": failed,
                    "enqueues_after_delete_commit": after,
                    "trace": records,
                }
            )
        except BaseException as error:
            result["failure"] = {
                "exception": type(error).__name__,
                "label": str(error) if isinstance(error, RuntimeError) else None,
            }
        finally:
            for proc in processes:
                proc.terminate()
                try:
                    proc.wait(3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if pg:
                pg.cleanup()
            result["source_after"] = hashes()
            result["same_source_snapshot"] = result["source_before"] == result["source_after"]
            result["passed"] = len(result["tests"]) == 3 and all(
                t["passed"] for t in result["tests"]
            )
            if output:
                Path(output).write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.child:
        child(args.child)
    else:
        raise SystemExit(main(args.output))
