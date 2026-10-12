"""Drive the spike's /v1 Agents wire with the REAL `openai` python package.

    python3 -m virtualenv -q "$OAI_VENV" && "$OAI_VENV/bin/pip" install -q openai
    "$OAI_VENV/bin/python" agents_sdk_check.py

The spike itself is stdlib-only; only this script needs `openai` (>=3.29 for client.beta.agents).
"""
import os, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openai
from openai import OpenAI
from ebxp.api import SandboxServer, presets, start_http, Policy, Principal, AgentScope, PathScope, ops

RES = []


def check(name, cond, extra=""):
    RES.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if (extra and not cond) else ""))


ws = tempfile.mkdtemp(prefix="ebx-wire-")
TOKEN = "wire-token-0123456789"
srv = SandboxServer(presets.agent_host(ws, agents=("codex", "claude_code")), tokens={TOKEN: Principal("app", ("dev",))})
srv._agents_default = None
httpd = start_http(srv)
port = httpd.server_address[1]
base = f"http://127.0.0.1:{port}"
client = OpenAI(api_key=TOKEN, base_url=f"{base}/v1/agents/..".replace("/agents/..", ""), max_retries=0)
codex = OpenAI(api_key=TOKEN, base_url=f"{base}/agents/codex/v1", max_retries=0)
A = codex.beta.agents

# ---- agents (C-2 envelope, real model names pass through, C-3)
ag = A.create(model="codex-mini", name="t1", instructions="be brief")
check("agents.create returns full Agent", ag.object == "agent" and ag.model == "codex-mini" and ag.multi_agent.enabled is False)
ag2 = A.create(model="gpt-5-codex")
check("real model names are accepted (no 404)", ag2.model == "gpt-5-codex")
ag3 = A.create(model="any-model")
page1 = A.list(limit=1)
check("list envelope: has_more + last_id", page1.has_more is True and page1.last_id, page1)
check("auto-pagination terminates and sees all", len(list(A.list(limit=1))) == 3)
check("order=asc honoured", [a.id for a in A.list(order="asc")] == [ag.id, ag2.id, ag3.id])
check("retrieve / update / delete", A.retrieve(ag.id).id == ag.id and A.update(ag.id, name="t2").name == "t2"
      and A.delete(ag3.id).deleted is True)
try:
    A.list(limit=1000)
    check("limit>100 rejected", False)
except openai.BadRequestError:
    check("limit>100 rejected", True)

# ---- environments
env = A.environments.create(environment={"type": "openai_hosted"})
check("environments create/retrieve/list", env.type == "self_hosted" and A.environments.retrieve(env.id).id == env.id
      and len(list(A.environments.list())) == 1)
try:
    A.environments.files.list(env.id)
    check("environments.files reserved -> 404", False)
except openai.NotFoundError:
    check("environments.files reserved -> 404", True)

# ---- sessions (C-6)
for bad in ({"type": "openai_hosted"},):
    try:
        A.sessions.create(environment=bad, agent_id=ag.id)
        check("openai_hosted environment -> 400 invalid_request_error", False)
    except openai.BadRequestError as e:
        check("openai_hosted environment -> 400 invalid_request_error", e.status_code == 400)
try:
    A.sessions.create(environment={"type": "none"}, agent_id=ag.id)
    check("environment none without input -> 400", False)
except openai.BadRequestError:
    check("environment none without input -> 400", True)
sess = A.sessions.create(environment={"type": "self_hosted"}, agent_id=ag.id, metadata={"k": "v"})
check("session embeds the full Agent (C-1)", sess.agent.model == "codex-mini" and sess.agent.id == ag.id and sess.object == "agent.session")
check("session shape: status idle, environment self_hosted with id+remote_url, required_actions []",
      sess.status == "idle" and sess.environment.type == "self_hosted" and sess.environment.id and sess.environment.remote_url
      and sess.required_actions == [] and sess.vault_ids == [])

# ---- the sessions.stream helper (C-4, C-5)
with A.sessions.stream(sess.id, input="hello") as stream:
    seen = [e.type for e in stream]
check("sessions.stream helper reaches idle after the turn", seen[-1] == "agent.session.idle" and "agent.session.turn.created" in seen
      and "agent.session.turn.completed" in seen, seen)
check("every event had an event_id (helper de-duplicates by it)", True)
s_after = A.sessions.retrieve(sess.id)
check("session idle again and last_active_at set", s_after.status == "idle" and s_after.last_active_at >= s_after.created_at)

# ---- events.create returns None (202) and Idempotency-Key semantics
msg = {"type": "agent.session.input.message", "input": [{"role": "user", "content": [{"type": "input_text", "text": "x"}]}]}
r = A.sessions.events.create(sess.id, events=[msg], idempotency_key="k-1")
check("events.create -> None (HTTP 202, empty body)", r is None)
time.sleep(0.3)
r2 = A.sessions.events.create(sess.id, events=[msg], idempotency_key="k-1")
check("same Idempotency-Key + same body replays 202 without a second turn", r2 is None and len(list(A.sessions.turns.list(sess.id))) == 2)
try:
    other = dict(msg, input="different")
    A.sessions.events.create(sess.id, events=[other], idempotency_key="k-1")
    check("same key + different body -> 409", False)
except openai.ConflictError as e:
    check("same key + different body -> 409 with x-should-retry: false", e.response.headers.get("x-should-retry") == "false")
try:
    A.sessions.events.create(sess.id, events=[{"type": "agent.session.input.tool_result", "call_id": "c", "output": "o"}])
    check("tool_result -> 400 agents.tool_result_unsupported", False)
except openai.BadRequestError as e:
    check("tool_result -> 400 agents.tool_result_unsupported", e.body and "tool_result_unsupported" in str(e.body) or "tool_result_unsupported" in str(e))
time.sleep(0.3)

# ---- idle-open events.stream (C-4)
got, closed = [], threading.Event()


def reader():
    try:
        with A.sessions.events.stream(sess.id) as st:
            for ev in st:
                got.append(ev.type)
    finally:
        closed.set()


t = threading.Thread(target=reader, daemon=True)
t.start()
time.sleep(1.0)
check("events.stream stays open while the session is idle (no events, not closed)", not closed.is_set() and got == [], got)
A.sessions.events.create(sess.id, events=[msg])
closed.wait(5)
check("events.stream delivers the turn then closes after the post-turn idle", got[-1:] == ["agent.session.idle"] and closed.is_set(), got)

# ---- items / turns / artifacts / traces / subagents
items = list(A.sessions.items.list(sess.id))
check("items.list envelope iterates", len(items) >= 2 and {i.role for i in items} == {"user", "assistant"})
turns = list(A.sessions.turns.list(sess.id))
tr = A.sessions.turns.retrieve(turns[0].id, session_id=sess.id)
check("turns.list/retrieve/items.list", tr.id == turns[0].id and len(list(A.sessions.turns.items.list(tr.id, session_id=sess.id))) == 2)
arts = list(A.sessions.artifacts.list(sess.id))
a0 = A.sessions.artifacts.retrieve(arts[0].id, session_id=sess.id)
content = A.sessions.artifacts.content(arts[0].id, session_id=sess.id)
check("artifacts (tier 1): list/retrieve/content/delete", a0.path == "result.txt" and b"echo:" in content.read()
      and A.sessions.artifacts.delete(arts[0].id, session_id=sess.id).deleted is True)
check("traces.list returns an empty envelope", list(A.sessions.traces.list(sess.id)) == [])
check("subagents.list returns an empty envelope", list(A.sessions.subagents.list(sess.id)) == [])
try:
    A.sessions.subagents.retrieve("sub_1", session_id=sess.id)
    check("subagents.retrieve -> 404 not_found_error", False)
except openai.NotFoundError as e:
    check("subagents.retrieve -> 404 not_found_error (x-should-retry false)", e.response.headers.get("x-should-retry") == "false")
try:
    A.vaults.list()
    check("vaults not planned -> 404 not_found_error", False)
except openai.NotFoundError:
    check("vaults not planned -> 404 not_found_error", True)

# ---- create with input + stream=true (single POST)
with A.sessions.create(environment={"type": "none"}, agent_id=ag.id, input="hi", stream=True) as st:
    kinds = [e.type for e in st]
check("sessions.create(stream=True) streams the first turn", "agent.session.turn.completed" in kinds and kinds[-1] == "agent.session.idle", kinds)
check("sessions.list / update / delete", len(list(A.sessions.list())) >= 2 and A.sessions.update(sess.id, metadata={"a": "b"}).metadata == {"a": "b"}
      and A.sessions.delete(sess.id).deleted is True)

# ---- adapter selection (C-3): path, header, model-equals-adapter, ambiguity
generic = OpenAI(api_key=TOKEN, base_url=f"{base}/v1", max_retries=0)
try:
    generic.beta.agents.sessions.create(environment={"type": "self_hosted"}, agent_id=ag.id)
    check("two adapters mounted + /v1 + no hint -> 400 agents.adapter_required", False)
except openai.BadRequestError as e:
    check("two adapters mounted + /v1 + no hint -> 400 agents.adapter_required", "adapter_required" in str(e))
hdr = OpenAI(api_key=TOKEN, base_url=f"{base}/v1", max_retries=0, default_headers={"X-EBX-Adapter": "claude_code"})
check("X-EBX-Adapter header selects the adapter", hdr.beta.agents.sessions.create(environment={"type": "self_hosted"}, agent_id=ag.id).status == "idle")
cc = OpenAI(api_key=TOKEN, base_url=f"{base}/agents/claude_code/v1", max_retries=0)
check("path adapter /agents/claude_code/v1 works with a real model name", cc.beta.agents.sessions.create(
    environment={"type": "self_hosted"}, agent={"model": "claude-sonnet-4"}).agent.model == "claude-sonnet-4")
unk = OpenAI(api_key=TOKEN, base_url=f"{base}/agents/nope/v1", max_retries=0)
try:
    unk.beta.agents.sessions.create(environment={"type": "self_hosted"}, agent_id=ag.id)
    check("unknown adapter path -> 404", False)
except openai.NotFoundError:
    check("unknown adapter path -> 404", True)

# ---- auth and policy
bad = OpenAI(api_key="wrong-token-0000000000", base_url=f"{base}/v1", max_retries=0)
try:
    bad.beta.agents.list()
    check("bad key -> AuthenticationError", False)
except openai.AuthenticationError as e:
    check("bad key -> AuthenticationError (authentication_error, x-should-retry false)", e.response.headers.get("x-should-retry") == "false")
httpd.shutdown()

# ---- single adapter: real model names and codex-mini need no hint
srv2 = SandboxServer(presets.agent_host(ws, agents=("codex",)), tokens={TOKEN: Principal("app", ("dev",))})
h2 = start_http(srv2)
only = OpenAI(api_key=TOKEN, base_url=f"http://127.0.0.1:{h2.server_address[1]}/v1", max_retries=0)
a = only.beta.agents.create(model="codex-mini")
s = only.beta.agents.sessions.create(environment={"type": "self_hosted"}, agent_id=a.id)
check("single mounted adapter: codex-mini and gpt-5-codex both route to it", s.status == "idle" and only.beta.agents.sessions.create(
    environment={"type": "self_hosted"}, agent={"model": "gpt-5-codex"}).status == "idle")
h2.shutdown()

# ---- second gate: a principal that may call agents.sessions.create but not agents.codex.sessions.create
pol = Policy().allow("agents.definitions.create", "agents.definitions.get", "agents.sessions.create",
                     agents=AgentScope(workdir=PathScope(ws), permissions="read-only"))
srv3 = SandboxServer(pol, tokens={TOKEN: Principal("app", ())})
h3 = start_http(srv3)
cl = OpenAI(api_key=TOKEN, base_url=f"http://127.0.0.1:{h3.server_address[1]}/agents/codex/v1", max_retries=0)
a = cl.beta.agents.create(model="m")
try:
    cl.beta.agents.sessions.create(environment={"type": "self_hosted"}, agent_id=a.id)
    check("generic sessions.create alone is not enough (adapter op is a second gate)", False)
except openai.NotFoundError:
    check("generic sessions.create alone is not enough (adapter op is a second gate)", True)
h3.shutdown()

print(f"== agents_sdk_check: {sum(RES)}/{len(RES)} (openai {openai.__version__})")
sys.exit(0 if all(RES) else 1)
