"""T3: Codex hosted behind the OpenAI-compatible Agents API (Python flavour with tokens + install mode)."""
from _t import *
from ebxp.api import SandboxServer, presets, start_http, Principal, from_config

ws = workspace()
os.environ["T3_KEY"] = "t3-secret-0123456789"
srv = from_config({"preset": "agent_host", "root": str(ws), "agents": ["codex"], "install": {"mode": "lazy"},
                   "auth": {"tokens": [{"id": "app", "roles": ["dev"], "token_env": "T3_KEY"}]}})
httpd = start_http(srv); port = httpd.server_address[1]
tok = os.environ["T3_KEY"]
st, a = http(port, "POST", "/v1/agents", {"model": "codex-mini", "name": "t3"}, tok)
check("POST /v1/agents works with the agent_host preset (B-10: the first SDK call)", st == 200 and a["object"] == "agent" and a["model"] == "codex-mini", a)
st, s = http(port, "POST", "/v1/agents/sessions", {"environment": {"type": "self_hosted"}, "agent_id": a["id"]}, tok)
check("session create routes to the only mounted adapter; model need not be an adapter name", st == 200 and s["agent"]["id"] == a["id"], s)
st, lst = http(port, "GET", "/v1/agents?limit=1", None, tok)
check("list envelope has has_more/first_id/last_id", set(lst) >= {"object", "data", "first_id", "last_id", "has_more"}, lst)
st, e = http(port, "POST", "/ops/agents.codex.install", {}, tok)
check("install is NOT granted by the preset (explicit-only)", st == 404 and e["code"] == "op.not_enabled")
st, e = http(port, "POST", "/v1/agents/sessions", {"environment": {"type": "self_hosted"}, "agent_id": a["id"]}, None)
check("no token -> 401 with the OpenAI error shape", st == 401 and e["error"]["type"] == "authentication_error", e)
httpd.shutdown()
done("T3")
