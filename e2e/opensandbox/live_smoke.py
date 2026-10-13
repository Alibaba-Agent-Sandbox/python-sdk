#!/usr/bin/env python3
"""Stdlib-only live smoke test of every OpenSandbox call the Agent Sandbox provider needs.

Run after `local-up.sh up` (eval "$(./local-up.sh env)"):  python3 live_smoke.py
Exits non-zero on the first failed assertion. Uses no third-party packages (same constraint
as an `abx provider install`ed exec plugin).
"""

from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("OPENSANDBOX_BASE_URL", "http://127.0.0.1:8080/v1")
KEY = os.environ.get("OPENSANDBOX_API_KEY", "local-dev-key")
IMAGE = os.environ.get("OPENSANDBOX_TEST_IMAGE", "python:3.12-slim")


def req(method, url, *, headers=None, body=None, timeout=60):
    data = None
    h = dict(headers or {})
    if body is not None and not isinstance(body, (bytes, bytearray)):
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    elif body is not None:
        data = bytes(body)
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        return urllib.request.urlopen(r, timeout=timeout)
    except urllib.error.HTTPError as e:  # keep the response object (status + body)
        return e


def jreq(method, url, **kw):
    resp = req(method, url, **kw)
    raw = resp.read()
    status = getattr(resp, "status", None) or resp.code
    return status, (json.loads(raw) if raw else None), resp


def lifecycle(method, path, body=None):
    return jreq(method, BASE + path, headers={"OPEN-SANDBOX-API-KEY": KEY}, body=body)


def sse_events(resp):
    """execd streams bare JSON objects separated by blank lines (Content-Type: text/event-stream).
    Standard `data: ` framing is also accepted."""
    buf = b""
    while True:
        chunk = resp.read(4096) if hasattr(resp, "read") else b""
        if not chunk:
            break
        buf += chunk
        while b"\n\n" in buf:
            frame, buf = buf.split(b"\n\n", 1)
            frame = frame.strip()
            if frame.startswith(b"data:"):
                frame = frame[5:].strip()
            if frame:
                yield json.loads(frame)
    if buf.strip():
        frame = buf.strip()
        yield json.loads(frame[5:].strip() if frame.startswith(b"data:") else frame)


def multipart(parts):
    boundary = uuid.uuid4().hex
    out = b""
    for name, filename, ctype, content in parts:
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return boundary, out


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def main():
    # --- auth + create -------------------------------------------------------------------
    st, _, _ = jreq("GET", BASE + "/sandboxes")  # no key
    check(st == 401, f"missing key -> 401 (got {st})")
    st, body, _ = lifecycle(
        "POST",
        "/sandboxes",
        {
            "image": {"uri": IMAGE},
            "timeout": 300,
            "entrypoint": ["tail", "-f", "/dev/null"],
            "resourceLimits": {"cpu": "500m", "memory": "512Mi"},
            "env": {"FOO": "bar"},
            "metadata": {"name": "abx-smoke", "owner": "abx"},
        },
    )
    check(st == 202 and body["status"]["state"] == "Running", f"create -> 202 Running ({st})")
    sid = body["id"]
    try:
        st, info, _ = lifecycle("GET", f"/sandboxes/{sid}")
        check(
            st == 200 and info["image"]["uri"] == IMAGE and info["metadata"]["owner"] == "abx",
            "get",
        )
        st, lst, _ = lifecycle(
            "GET",
            "/sandboxes?pageSize=50&state=Running&metadata=" + urllib.parse.quote("owner=abx"),
        )
        check(
            st == 200 and any(i["id"] == sid for i in lst["items"]),
            "list filtered by state+metadata",
        )
        st, ep, _ = lifecycle("GET", f"/sandboxes/{sid}/endpoints/44772")
        check(st == 200 and "endpoint" in ep, f"execd endpoint {ep}")
        execd = "http://" + ep["endpoint"].rstrip("/")
        eh = ep.get("headers") or {}
        st, ep8, _ = lifecycle("GET", f"/sandboxes/{sid}/endpoints/8000")
        check(st == 200, f"port endpoint {ep8['endpoint']}")
        st, ep8p, _ = lifecycle("GET", f"/sandboxes/{sid}/endpoints/8000?use_server_proxy=true")
        check("/proxy/8000" in ep8p["endpoint"], f"server-proxied endpoint {ep8p['endpoint']}")

        # --- exec (stream) ---------------------------------------------------------------
        r = req(
            "POST",
            execd + "/command",
            headers=eh,
            body={"command": "echo out; echo err >&2; echo $FOO; exit 3"},
        )
        evs = list(sse_events(r))
        types = [e["type"] for e in evs]
        cid = evs[0]["text"]
        check(
            types[0] == "init" and "stdout" in types and "stderr" in types,
            f"command stream types {types}",
        )
        err = [e for e in evs if e["type"] == "error"][0]["error"]
        check(
            err["ename"] == "CommandExecError" and err["evalue"] == "3",
            "non-zero exit surfaces as error event (evalue=exit code)",
        )
        st, status, _ = jreq("GET", f"{execd}/command/status/{cid}", headers=eh)
        check(
            status["exit_code"] == 3 and status["running"] is False,
            f"command status {status['exit_code']}",
        )
        out = "".join(e["text"] for e in evs if e["type"] == "stdout")
        check("bar" in out, "create-time env visible")

        # --- background process + logs + kill -------------------------------------------
        r = req(
            "POST",
            execd + "/command",
            headers=eh,
            body={
                "command": "for i in 1 2 3 4 5 6; do echo l$i; sleep 1; done",
                "background": True,
            },
        )
        bg = list(sse_events(r))[0]["text"]
        import time

        time.sleep(2.5)
        st, status, _ = jreq("GET", f"{execd}/command/status/{bg}", headers=eh)
        check(status["running"] is True, "background running")
        resp = req("GET", f"{execd}/command/{bg}/logs", headers=eh)
        text = resp.read().decode()
        check(
            "l1" in text and resp.headers.get("EXECD-COMMANDS-TAIL-CURSOR") is not None,
            "background logs + tail cursor header",
        )
        st, _, _ = jreq("DELETE", f"{execd}/command?id={bg}", headers=eh)
        check(st == 200, "interrupt background command")

        # --- timeout ---------------------------------------------------------------------
        r = req("POST", execd + "/command", headers=eh, body={"command": "sleep 5", "timeout": 500})
        err = [e for e in sse_events(r) if e["type"] == "error"][0]["error"]
        check(
            err["evalue"] == "-1" and "killed" in " ".join(err["traceback"]),
            "timeout -> evalue -1 / signal: killed",
        )

        # --- files -----------------------------------------------------------------------
        st, _, _ = jreq(
            "POST", execd + "/directories", headers=eh, body={"/tmp/abx/a/b": {"mode": 755}}
        )
        check(st == 200, "mkdir -p")
        b, payload = multipart(
            [
                (
                    "metadata",
                    "metadata",
                    "application/json",
                    json.dumps({"path": "/tmp/abx/a/hello.txt", "mode": 644}).encode(),
                ),
                ("file", "hello.txt", "application/octet-stream", b"hello\nworld\n\x00\xff"),
            ]
        )
        st, _, _ = jreq(
            "POST",
            execd + "/files/upload",
            headers={**eh, "Content-Type": f"multipart/form-data; boundary={b}"},
            body=payload,
        )
        check(st == 200, "upload (metadata part must be a *file* part)")
        resp = req("GET", f"{execd}/files/download?path=/tmp/abx/a/hello.txt", headers=eh)
        check(resp.read() == b"hello\nworld\n\x00\xff", "download is byte exact")
        st, finfo, _ = jreq("GET", f"{execd}/files/info?path=/tmp/abx/a/hello.txt", headers=eh)
        fi = finfo["/tmp/abx/a/hello.txt"]
        check(fi["type"] == "file" and fi["size"] == 14 and fi["mode"] == 644, f"stat {fi['mode']}")
        st, lst, _ = jreq("GET", f"{execd}/directories/list?path=/tmp/abx&depth=2", headers=eh)
        check(
            {e["path"] for e in lst} >= {"/tmp/abx/a", "/tmp/abx/a/b", "/tmp/abx/a/hello.txt"},
            "list depth=2",
        )
        st, found, _ = jreq("GET", f"{execd}/files/search?path=/tmp/abx&pattern=*.txt", headers=eh)
        check([f["path"] for f in found] == ["/tmp/abx/a/hello.txt"], "search glob")
        st, _, _ = jreq(
            "POST",
            execd + "/files/mv",
            headers=eh,
            body=[{"src": "/tmp/abx/a/hello.txt", "dest": "/tmp/abx/a/b/h2.txt"}],
        )
        check(st == 200, "mv")
        st, miss, _ = jreq("GET", f"{execd}/files/info?path=/tmp/abx/a/hello.txt", headers=eh)
        check(st == 404 and miss["code"] == "FILE_NOT_FOUND", "stat missing -> 404 FILE_NOT_FOUND")
        st, _, _ = jreq("DELETE", f"{execd}/files?path=/tmp/abx/a/b/h2.txt", headers=eh)
        check(st == 200, "rm file")
        st, _, _ = jreq("DELETE", f"{execd}/files?path=/tmp/abx/a/b/h2.txt", headers=eh)
        check(st == 200, "rm missing file is idempotent (200)")
        st, bad, _ = jreq("DELETE", f"{execd}/files?path=/tmp/abx/a", headers=eh)
        check(
            st == 500 and bad["code"] == "RUNTIME_ERROR",
            "rm on a directory -> 500 RUNTIME_ERROR (needs /directories)",
        )
        st, _, _ = jreq("DELETE", f"{execd}/directories?path=/tmp/abx", headers=eh)
        check(st == 200, "rmdir -rf")

        # --- ttl / pause / resume / metadata ---------------------------------------------
        st, exp, _ = lifecycle(
            "POST", f"/sandboxes/{sid}/renew-expiration", {"expiresAt": "2099-01-01T00:00:00Z"}
        )
        check(st == 200 and exp["expiresAt"].startswith("2099"), "renew-expiration (absolute time)")
        st, _, _ = lifecycle("POST", f"/sandboxes/{sid}/pause")
        check(st == 202, "pause")
        st, info, _ = lifecycle("GET", f"/sandboxes/{sid}")
        check(info["status"]["state"] == "Paused", "state Paused")
        st, _, _ = lifecycle("POST", f"/sandboxes/{sid}/resume")
        check(st == 202, "resume")
    finally:
        st, _, _ = lifecycle("DELETE", f"/sandboxes/{sid}")
        check(st == 204, "kill -> 204")
    st, nf, _ = lifecycle("GET", f"/sandboxes/{sid}")
    check(st == 404 and "NOT_FOUND" in nf["code"], f"killed sandbox disappears (404 {nf['code']})")
    st, _, _ = lifecycle("DELETE", f"/sandboxes/{sid}")
    check(st == 404, "kill is NOT idempotent server-side (404) -> plugin must swallow it")
    print("ALL OK")


if __name__ == "__main__":
    main()
