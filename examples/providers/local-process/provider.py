#!/usr/bin/env python3
"""Reference EPP/1 provider: sandboxes are plain directories, commands run as local processes.

Stdlib only. NOT isolated - for demos and as a template for plugin authors.
Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout, free-form logs on stderr.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL = "epp/1"
FEATURES = ["sandbox.lifecycle", "sandbox.timeout", "exec.run", "exec.stream", "files.rw"]

NOT_AUTH, NOT_FOUND, NO_FEATURE, QUOTA, TIMEOUT, BAD_PARAMS, FAIL = (
    -32001,
    -32002,
    -32003,
    -32004,
    -32005,
    -32006,
    -32000,
)

_out_lock = threading.Lock()
state: dict = {"root": None, "config": {}, "debug": False}


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data or {}


def send(obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    with _out_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def notify(method: str, params: dict) -> None:
    send({"jsonrpc": "2.0", "method": method, "params": params})


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- state


def sandboxes_dir() -> Path:
    return state["root"] / "sandboxes"


def sandbox_path(sandbox_id: str) -> Path:
    if not sandbox_id or "/" in sandbox_id or ".." in sandbox_id:
        raise RpcError(NOT_FOUND, f"sandbox '{sandbox_id}' not found", {"sdk_code": "E2000"})
    path = sandboxes_dir() / sandbox_id
    if not (path / "meta.json").exists():
        raise RpcError(NOT_FOUND, f"sandbox '{sandbox_id}' not found", {"sdk_code": "E2000"})
    return path


def record(path: Path) -> dict:
    meta = json.loads((path / "meta.json").read_text())
    return {
        "sandbox_id": meta["sandbox_id"],
        "template": meta["template"],
        "status": "running",
        "created_at": meta["created_at"],
        "metadata": meta.get("metadata", {}),
    }


def inside(sandbox_id: str, raw_path: str) -> Path:
    root = (sandbox_path(sandbox_id) / "root").resolve()
    rel = raw_path.lstrip("/")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise RpcError(BAD_PARAMS, f"path '{raw_path}' escapes the sandbox")
    return target


# ---------------------------------------------------------------- methods


def m_initialize(p: dict) -> dict:
    if p.get("protocol") != PROTOCOL:
        raise RpcError(BAD_PARAMS, f"unsupported protocol {p.get('protocol')}")
    state["root"] = Path(p["data_dir"])
    state["config"] = p.get("config", {})
    state["debug"] = bool(state["config"].get("debug"))
    sandboxes_dir().mkdir(parents=True, exist_ok=True)
    return {
        "protocol": PROTOCOL,
        "plugin": {"name": "local-process", "version": "0.1.0"},
        "features": FEATURES,
        "operation_contract_version": 1,
        "operations": {'cli': ['sandbox.create', 'sandbox.get', 'sandbox.list', 'sandbox.delete', 'sandbox.timeout', 'exec.run', 'exec.stream', 'files.read', 'files.write', 'files.list', 'files.stat', 'files.remove', 'files.move'], 'python': ['sandbox.create', 'sandbox.get', 'sandbox.list', 'sandbox.delete', 'sandbox.timeout', 'exec.run', 'exec.stream', 'files.read', 'files.write', 'files.list', 'files.stat', 'files.remove', 'files.move']},
        "workflow_inputs": ["managed"],
        "startup_modes": ["exec", "none"],
    }


def m_shutdown(_p: dict) -> dict:
    return {}


def m_create(p: dict) -> dict:
    sandbox_id = "lp-" + uuid.uuid4().hex[:10]
    path = sandboxes_dir() / sandbox_id
    (path / "root").mkdir(parents=True)
    meta = {
        "sandbox_id": sandbox_id,
        "template": p.get("template") or "base",
        "created_at": now(),
        "metadata": p.get("metadata") or {},
        "envs": p.get("envs") or {},
        "expires_at": time.time() + float(p.get("timeout") or 300),
    }
    (path / "meta.json").write_text(json.dumps(meta))
    return record(path)


def m_get(p: dict) -> dict:
    return record(sandbox_path(p["sandbox_id"]))


def m_list(_p: dict) -> dict:
    items = []
    if sandboxes_dir().exists():
        for child in sorted(sandboxes_dir().iterdir()):
            if (child / "meta.json").exists():
                items.append(record(child))
    return {"sandboxes": items}


def m_kill(p: dict) -> dict:
    try:
        path = sandbox_path(p["sandbox_id"])
    except RpcError:
        return {}  # kill is idempotent
    shutil.rmtree(path, ignore_errors=True)
    return {}


def m_set_timeout(p: dict) -> dict:
    path = sandbox_path(p["sandbox_id"])
    meta = json.loads((path / "meta.json").read_text())
    meta["expires_at"] = time.time() + float(p["timeout"])
    (path / "meta.json").write_text(json.dumps(meta))
    return {}


def _argv(p: dict) -> list[str]:
    return [p["cmd"], *p.get("args", [])]


def _env(sandbox_id: str, p: dict) -> dict:
    meta = json.loads((sandbox_path(sandbox_id) / "meta.json").read_text())
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(sandbox_path(sandbox_id) / "root"),
    }
    env.update(meta.get("envs", {}))
    env.update(p.get("env") or {})
    return env


def m_exec_run(p: dict) -> dict:
    cwd = inside(p["sandbox_id"], p.get("cwd") or "/")
    try:
        proc = subprocess.run(
            _argv(p),
            cwd=cwd,
            env=_env(p["sandbox_id"], p),
            capture_output=True,
            timeout=float(p.get("timeout") or 60),
            input=(p.get("stdin") or "").encode() or None,
            check=False,
        )
    except FileNotFoundError:
        return {"exit_code": 127, "stdout": "", "stderr": f"{p['cmd']}: command not found\n"}
    except subprocess.TimeoutExpired:
        raise RpcError(TIMEOUT, "command timed out") from None
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", "replace"),
        "stderr": proc.stderr.decode("utf-8", "replace"),
    }


def m_exec_start(p: dict) -> dict:
    cwd = inside(p["sandbox_id"], p.get("cwd") or "/")
    process_id = uuid.uuid4().hex[:8]
    try:
        proc = subprocess.Popen(
            _argv(p),
            cwd=cwd,
            env=_env(p["sandbox_id"], p),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except FileNotFoundError:

        def fail() -> None:
            notify(
                "exec.output",
                {
                    "process_id": process_id,
                    "stream": "stderr",
                    "data": f"{p['cmd']}: command not found\n",
                },
            )
            notify("exec.exit", {"process_id": process_id, "exit_code": 127})

        threading.Thread(target=fail, daemon=True).start()
        return {"process_id": process_id}

    def pump(stream, name: str) -> None:
        for chunk in iter(lambda: stream.read(4096), b""):
            notify(
                "exec.output",
                {
                    "process_id": process_id,
                    "stream": name,
                    "data": chunk.decode("utf-8", "replace"),
                },
            )

    def supervise() -> None:
        threads = [
            threading.Thread(target=pump, args=(proc.stdout, "stdout")),
            threading.Thread(target=pump, args=(proc.stderr, "stderr")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        notify("exec.exit", {"process_id": process_id, "exit_code": proc.wait()})

    threading.Thread(target=supervise, daemon=True).start()
    return {"process_id": process_id}


def _entry(path: Path, root: Path) -> dict:
    st = path.stat()
    return {
        "name": path.name,
        "path": "/" + str(path.relative_to(root)) if path != root else "/",
        "type": "dir" if path.is_dir() else "file",
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _root(sandbox_id: str) -> Path:
    return (sandbox_path(sandbox_id) / "root").resolve()


def _existing(sandbox_id: str, raw: str) -> Path:
    path = inside(sandbox_id, raw)
    if not path.exists():
        raise RpcError(NOT_FOUND, f"no such file or directory: {raw}", {"sdk_code": "E4001"})
    return path


def m_files_read(p: dict) -> dict:
    path = _existing(p["sandbox_id"], p["path"])
    data = path.read_bytes()
    return {"content_b64": base64.b64encode(data).decode("ascii"), "size": len(data)}


def m_files_write(p: dict) -> dict:
    path = inside(p["sandbox_id"], p["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(p.get("content_b64", "")))
    return {}


def m_files_list(p: dict) -> dict:
    path = _existing(p["sandbox_id"], p["path"])
    root = _root(p["sandbox_id"])
    return {"entries": [_entry(c, root) for c in sorted(path.iterdir())]}


def m_files_stat(p: dict) -> dict:
    return _entry(_existing(p["sandbox_id"], p["path"]), _root(p["sandbox_id"]))


def m_files_mkdir(p: dict) -> dict:
    inside(p["sandbox_id"], p["path"]).mkdir(parents=True, exist_ok=True)
    return {}


def m_files_remove(p: dict) -> dict:
    path = _existing(p["sandbox_id"], p["path"])
    shutil.rmtree(path) if path.is_dir() else path.unlink()
    return {}


def m_files_move(p: dict) -> dict:
    src = _existing(p["sandbox_id"], p["source"])
    dst = inside(p["sandbox_id"], p["destination"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {}


def m_debug_env(_p: dict) -> dict:
    return {"env": dict(os.environ), "config_keys": sorted(state["config"])}


def m_debug_leak(_p: dict) -> dict:
    sys.stderr.write("leaking token: %s\n" % state["config"].get("token", ""))
    sys.stderr.flush()
    return {}


def m_debug_crash(_p: dict) -> dict:
    sys.stderr.write("fatal: simulated crash\n")
    sys.stderr.flush()
    os._exit(3)


def m_debug_garbage(_p: dict) -> dict:
    sys.stdout.write("this is not json\n")
    sys.stdout.flush()
    return {}


def m_debug_sleep(p: dict) -> dict:
    time.sleep(float(p.get("seconds", 5)))
    return {}


METHODS = {
    "initialize": m_initialize,
    "shutdown": m_shutdown,
    "sandbox.create": m_create,
    "sandbox.connect": m_get,
    "sandbox.get": m_get,
    "sandbox.list": m_list,
    "sandbox.kill": m_kill,
    "sandbox.set_timeout": m_set_timeout,
    "exec.run": m_exec_run,
    "exec.start": m_exec_start,
    "files.read": m_files_read,
    "files.write": m_files_write,
    "files.list": m_files_list,
    "files.stat": m_files_stat,
    "files.mkdir": m_files_mkdir,
    "files.remove": m_files_remove,
    "files.move": m_files_move,
}
DEBUG_METHODS = {
    "debug.env": m_debug_env,
    "debug.leak": m_debug_leak,
    "debug.crash": m_debug_crash,
    "debug.garbage": m_debug_garbage,
    "debug.sleep": m_debug_sleep,
}


def handle(msg: dict) -> None:
    rid = msg.get("id")
    method = msg.get("method")
    if rid is None:  # notification ($/cancel is accepted and ignored)
        return
    handler = METHODS.get(method) or (DEBUG_METHODS.get(method) if state["debug"] else None)
    try:
        if handler is None:
            raise RpcError(-32601, f"unknown method {method}")
        result = handler(msg.get("params") or {})
        send({"jsonrpc": "2.0", "id": rid, "result": result})
        if method == "shutdown":
            sys.stdout.flush()
    except RpcError as exc:
        send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": exc.code, "message": exc.message, "data": exc.data},
            }
        )
    except KeyError as exc:
        send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": BAD_PARAMS, "message": f"missing parameter {exc}"},
            }
        )
    except Exception as exc:  # noqa: BLE001
        send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": FAIL, "message": f"{type(exc).__name__}: {exc}"},
            }
        )


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        threading.Thread(target=handle, args=(msg,), daemon=True).start() if msg.get(
            "method"
        ) == "exec.start" else handle(msg)


if __name__ == "__main__":
    main()
