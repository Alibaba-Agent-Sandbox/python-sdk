#!/usr/bin/env python3
"""Real SDK repository/preview/MCP acceptance; creates and deletes one owned sandbox.

Install the source-compatible agent-sandbox-client in this Python environment.
Credentials are read only from the environment. No account keys enter the sandbox.
"""

import argparse
import hashlib
import json
import logging
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from agent_sandbox import Sandbox

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--output", type=Path, required=True, help="New sanitized JSON evidence file (must not exist)"
)
args = parser.parse_args()
if args.output.exists():
    parser.error("Evidence already exists; choose a new output file")
args.output.parent.mkdir(parents=True, exist_ok=True)
logging.disable(logging.CRITICAL)


def sanitize(text):
    for key, value in os.environ.items():
        if value and any(
            word in key.upper() for word in ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL")
        ):
            text = text.replace(value, "[REDACTED]")
    return text


report = {
    "checks": [],
    "resources": [],
    "scope": (
        "Real SDK-controlled sandbox; actual public repository, MCP npm packages "
        "and application-level expiring preview"
    ),
}


def save():
    args.output.write_text(sanitize(json.dumps(report, indent=2)))


def record(name, ok, **detail):
    row = {"name": name, "passed": bool(ok), **detail}
    report["checks"].append(row)
    save()
    print(sanitize(json.dumps(row)), flush=True)


sb = None
try:
    sb = Sandbox.create(
        template=os.environ.get("ABX_SKILL_RUNTIME_TEMPLATE", "code-interpreter-v1"),
        timeout=1200,
        secure=False,
        metadata={
            "purpose": os.environ.get("ABX_SKILL_RUN_PREFIX", "skills-tools-live")[:64],
            "run": secrets.token_hex(8),
        },
        request_timeout=45,
    )
    report["resources"].append({"id": sb.sandbox_id, "kind": "sandbox"})
    save()

    def run(name, cmd, timeout=120, expect=None):
        r = sb.commands.run(cmd, timeout=timeout)
        ok = r.exit_code == 0 and (expect is None or expect in r.stdout)
        record(
            name,
            ok,
            exit_code=r.exit_code,
            stdout=sanitize(r.stdout[-4000:]),
            stderr=sanitize(r.stderr[-2000:]),
        )
        if not ok:
            raise RuntimeError(name + " failed")
        return r.stdout

    remote = "/home/user/skills-tools-live"
    run("prepare-owned-workdir", f"mkdir -p {remote}")
    run(
        "public-repository-checkout-pinned",
        f"git init -q {remote}/repo && "
        f"git -C {remote}/repo remote add origin "
        "https://github.com/alibaba-agent-sandbox/awesome-templates.git && "
        "fetched=0; for attempt in 1 2; do "
        f"if timeout 90s git -C {remote}/repo -c http.version=HTTP/1.1 "
        "-c http.lowSpeedLimit=1 -c http.lowSpeedTime=30 fetch --depth 1 origin "
        "1a8c81f59d22fe10b987ffe5f9b59d15b5ed0ded; then fetched=1; break; fi; done; "
        'test "$fetched" = 1 && '
        f"git -C {remote}/repo checkout --detach FETCH_HEAD && "
        f"git -C {remote}/repo rev-parse HEAD",
        220,
        expect="1a8c81f59d22fe10b987ffe5f9b59d15b5ed0ded",
    )
    run("repository-app-syntax-test", f"node --check {remote}/repo/node-web/index.js")
    run(
        "repository-app-start",
        f"PORT=3000 nohup node {remote}/repo/node-web/index.js >{remote}/app.log 2>&1 "
        f"</dev/null & echo $! >{remote}/app.pid",
    )
    run(
        "repository-app-business-response",
        'python3 -c "import urllib.request;assert '
        "urllib.request.urlopen('http://127.0.0.1:3000').read()==b'node-web ready\\n';"
        " print('HTTP200 exact node-web response')\"",
        expect="HTTP200",
    )
    proxy = r"""import http.server, urllib.parse, urllib.request, secrets, time
import hmac, hashlib, json, os

secret = secrets.token_bytes(32)


def signature(t):
    return hmac.new(secret, str(t).encode(), hashlib.sha256).hexdigest()


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        try:
            t = int(q.get("expires", ["0"])[0])
            sig = q.get("signature", [""])[0]
            if t <= time.time() or not hmac.compare_digest(sig, signature(t)):
                raise ValueError()
            data = urllib.request.urlopen("http://127.0.0.1:3000").read()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)
        except ValueError:
            self.send_response(403)
            self.end_headers()

    def log_message(self, *a):
        pass


server = http.server.HTTPServer(("0.0.0.0", 3080), H)
t = int(time.time()) + 20
with open("/home/user/skills-tools-live/preview.json", "w") as f:
    json.dump({"path": "/?expires=" + str(t) + "&signature=" + signature(t), "expires": t}, f)
os.chmod("/home/user/skills-tools-live/preview.json", 0o600)
server.serve_forever()
"""
    sb.files.write(remote + "/preview.py", proxy)
    run(
        "preview-start",
        f"nohup python3 {remote}/preview.py >{remote}/preview.log 2>&1 </dev/null & "
        f"echo $! >{remote}/preview.pid",
    )
    time.sleep(1)
    descriptor = json.loads(sb.files.read(remote + "/preview.json"))
    host = sb.get_host(3080)
    url = "https://" + host + descriptor["path"]

    def status(target):
        try:
            with urllib.request.urlopen(target, timeout=15) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    unsigned = status("https://" + host + "/")
    valid = status(url)
    tampered = status(url + "x")
    record(
        "external-application-signed-preview-valid",
        valid == (200, b"node-web ready\n"),
        status=valid[0],
        body_sha256=hashlib.sha256(valid[1]).hexdigest(),
        expiry_seconds=20,
        contract="application HMAC; provider gateway-native signing is not asserted",
    )
    record(
        "external-preview-unsigned-and-tampered-rejected",
        unsigned[0] == 403 and tampered[0] == 403,
        unsigned_status=unsigned[0],
        tampered_status=tampered[0],
    )
    while time.time() <= descriptor["expires"] + 1:
        time.sleep(1)
    expired = status(url)
    record("external-preview-expired-rejected", expired[0] == 403, status=expired[0])
    readback = sb.files.read(remote + "/repo/node-web/index.js")
    record(
        "repository-source-hash-readback",
        True,
        sha256=hashlib.sha256(readback.encode()).hexdigest(),
        commit="1a8c81f59d22fe10b987ffe5f9b59d15b5ed0ded",
    )
    mcp_client = r"""import subprocess, json, sys, pathlib

root = pathlib.Path(sys.argv[1])
version = sys.argv[2]
log = open(root / ("mcp-" + version + ".log"), "w")
p = subprocess.Popen(
    [
        "node",
        str(root / "tools/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js"),
        str(root / "data"),
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=log,
    text=True,
)


def req(id, method, params):
    p.stdin.write(
        json.dumps({"jsonrpc": "2.0", "id": id, "method": method, "params": params}) + "\n"
    )
    p.stdin.flush()
    while True:
        line = p.stdout.readline()
        if not line:
            raise RuntimeError("MCP server exited")
        msg = json.loads(line)
        if msg.get("id") == id:
            if "error" in msg:
                raise RuntimeError(str(msg["error"]))
            return msg["result"]


try:
    init = req(
        1,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "skills-acceptance", "version": "1.0"},
        },
    )
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    p.stdin.flush()
    tools = req(2, "tools/list", {})
    assert any(t["name"] == "read_file" for t in tools["tools"])
    result = req(
        3,
        "tools/call",
        {"name": "read_file", "arguments": {"path": str(root / "data/business.json")}},
    )
    text = "\n".join(x.get("text", "") for x in result["content"])
    assert "385" in text and not result.get("isError")
    print(
        json.dumps(
            {
                "version": version,
                "tool_count": len(tools["tools"]),
                "business_output": json.loads(text),
                "protocol": init["protocolVersion"],
            }
        )
    )
finally:
    p.terminate()
    p.wait(timeout=10)
    log.close()
"""
    sb.files.write(remote + "/mcp_client.py", mcp_client)
    run(
        "mcp-fixture-data",
        f"mkdir -p {remote}/data && printf '%s' '{{\"sum_of_squares\":385}}' "
        f">{remote}/data/business.json",
    )
    for version in ["2026.7.10", "2026.8.31"]:
        run(
            "third-party-mcp-install-" + version,
            f"timeout 240s npm install --prefix {remote}/tools --ignore-scripts --no-audit"
            f" --no-fund @modelcontextprotocol/server-filesystem@{version}",
            240,
        )
        run(
            "third-party-mcp-initialize-discover-business-tool-" + version,
            f"python3 {remote}/mcp_client.py {remote} {version}",
            90,
            expect="385",
        )
        run(
            "third-party-mcp-log-readback-" + version,
            f"test -s {remote}/mcp-{version}.log && tail -5 {remote}/mcp-{version}.log",
        )
    run(
        "cleanup-owned-app-and-preview-processes",
        f'kill "$(cat {remote}/app.pid)" "$(cat {remote}/preview.pid)" && '
        f"rm -rf {remote}/tools {remote}/data && "
        f"test ! -e {remote}/tools && test ! -e {remote}/data",
    )
    run(
        "third-party-tools-process-cleanup-check",
        "python3 -c \"import pathlib; bad=[]; own=str(__import__('os').getpid()); "
        "[(bad.append(p.name)) for p in pathlib.Path('/proc').iterdir() if "
        "p.name.isdigit() and p.name != own and b'server-filesystem/dist/index.js' in"
        " (p/'cmdline').read_bytes()]; assert not bad,bad;print('no MCP server "
        "remains')\"",
        expect="no MCP",
    )
    report["workload_passed"] = all(x["passed"] for x in report["checks"])
except Exception as e:
    report["failure"] = sanitize(str(e))
    record("workload-exception", False, error=report["failure"])
finally:
    if sb:
        try:
            sb.kill(request_timeout=30)
            try:
                sb.get_info(request_timeout=15)
            except Exception as e:
                report["sandbox_absent"] = type(e).__name__ in (
                    "NotFoundException",
                    "SandboxNotFoundException",
                )
            record(
                "owned-sandbox-cleanup-independent-readback", report.get("sandbox_absent", False)
            )
        except Exception as e:
            record("owned-sandbox-cleanup", False, error=sanitize(str(e)))
    save()
sys.exit(0 if report.get("workload_passed") and report.get("sandbox_absent") else 1)
