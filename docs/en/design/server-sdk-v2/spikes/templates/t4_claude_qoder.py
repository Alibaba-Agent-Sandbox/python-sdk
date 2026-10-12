"""T4: claude_code + qoder hosted; qoder is flagged experimental; the adapter is chosen by base URL path or header."""
from _t import *
from ebxp.api import presets, SandboxServer, start_http, Principal

ws = workspace()
srv = SandboxServer(presets.agent_host(ws, agents=("claude_code", "qoder")), tokens={"k" * 20: Principal("app", ())})
check("check() warns that qoder is experimental", any("qoder" in m and "experimental" in m for m in srv.check()), srv.check())
httpd = start_http(srv); port = httpd.server_address[1]
st, rt = http(port, "GET", "/agents/runtimes", None, "k" * 20)
check("agents.runtimes.list flags experimental adapters", {r["id"]: r["experimental"] for r in rt["data"]} == {"claude_code": False, "qoder": True}, rt)
st, a = http(port, "POST", "/v1/agents", {"model": "claude-sonnet-4"}, "k" * 20)
body = {"environment": {"type": "self_hosted"}, "agent_id": a["id"]}
st, e = http(port, "POST", "/v1/agents/sessions", body, "k" * 20)
check("two adapters mounted + plain /v1 -> 400 agents.adapter_required (no silent guess)", st == 400 and e["error"]["code"] == "agents.adapter_required", e)
check("path /agents/qoder/v1 selects qoder", http(port, "POST", "/agents/qoder/v1/agents/sessions", body, "k" * 20)[0] == 200)
check("X-EBX-Adapter: claude_code selects claude_code", http(port, "POST", "/v1/agents/sessions", body, "k" * 20, {"X-EBX-Adapter": "claude_code"})[0] == 200)
check("an adapter that is not mounted is 404", http(port, "POST", "/agents/codex/v1/agents/sessions", body, "k" * 20)[0] == 404)
httpd.shutdown()
done("T4")
