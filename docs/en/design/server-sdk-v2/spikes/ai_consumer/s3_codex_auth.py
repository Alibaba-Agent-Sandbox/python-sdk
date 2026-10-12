# S3: expose Codex through the OpenAI-compatible agents API with my own bearer token; nothing else but workspace files.
from h import *
os.environ["APP_API_KEY"] = "app-secret-0123456789"
os.makedirs("/tmp/s3ws", exist_ok=True)
from ebxp.api import from_config, start_http
import json, urllib.request, urllib.error
cfg = {"preset": "agent-host", "agents": ["codex"], "root": "/tmp/s3ws",
       "auth": {"tokens": [{"id": "app", "roles": ["dev"], "token_env": "APP_API_KEY"}]},
       "agent": {"codex": {"llm": {"base_url_env": "LLM_BASE_URL", "api_key_env": "LLM_API_KEY", "model": "gpt-5-codex"},
                           "permissions": "workspace-write"}} if False else None,
       "install": {"mode": "lazy"}}
cfg = {k: v for k, v in cfg.items() if v is not None}
srv = from_config(cfg)
httpd = start_http(srv); port = httpd.server_address[1]
def http(path, body=None, token=None, hdr="Authorization"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body or {}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token: req.add_header(hdr, ("Bearer " if hdr == "Authorization" else "") + token)
    try:
        r = urllib.request.urlopen(req); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
check("no token -> 401", http("/ops/agents.codex.run")[0] == 401)
check("wrong token -> 401", http("/ops/agents.codex.run", token="nope")[0] == 401)
check("Bearer token -> codex.run ok", http("/ops/agents.codex.run", token="app-secret-0123456789")[0] == 200)
check("X-Access-Token also works", http("/ops/agents.codex.run", token="app-secret-0123456789", hdr="X-Access-Token")[0] == 200)
check("claude_code not mounted -> 404", http("/ops/agents.claude_code.run", token="app-secret-0123456789")[1].get("code") == "op.not_enabled")
check("commands.run not mounted -> 404", http("/ops/commands.run", token="app-secret-0123456789")[0] == 404)
check("terminal not mounted", http("/ops/terminal.create", token="app-secret-0123456789")[0] == 404)
check("install is not granted by agents.codex.** (explicit-only)", http("/ops/agents.codex.install", token="app-secret-0123456789")[0] == 404)
try:
    from_config({"auth": {"tokens": [{"id": "a", "token": "plaintext"}]}}); ok = False
except ValueError as e:
    ok = "token_env" in str(e)
check("literal secret rejected with fix hint", ok)
try:
    from_config({"preset": "agent-hots"}); ok = False
except ValueError as e:
    ok = "unknown preset" in str(e)
check("typo'd preset rejected", ok)
def conflict():
    req = urllib.request.Request(f"http://127.0.0.1:{port}/ops/core.health", data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer app-secret-0123456789"); req.add_header("X-Access-Token", "something-else-entirely")
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code
check("Authorization + different X-Access-Token -> 401 (no silent precedence)", conflict() == 401)
check("core.health is mounted without being named", http("/ops/core.health", token="app-secret-0123456789")[0] == 200)
httpd.shutdown(); done("S3")

