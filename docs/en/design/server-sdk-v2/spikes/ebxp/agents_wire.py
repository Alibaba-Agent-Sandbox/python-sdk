"""Spike: the official OpenAI Agents wire (/v1/agents...) served from policy-gated ops with an echo adapter.

Verified against the real `openai` 3.29.0 SDK by `agents_sdk_check.py` (run with a venv that has `openai`).
"""
from __future__ import annotations
import dataclasses, hashlib, json, re, secrets, threading, time
from typing import Any

from .catalog import ADAPTERS, EXPERIMENTAL_ADAPTERS
from .guards import Denied


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(16)}"            # IS-J1: unguessable ids


class WireError(Denied):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(code, message, status=status)


@dataclasses.dataclass
class Raw:
    status: int = 200
    body: Any = None
    content_type: str = "application/json"
    headers: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class SSE:
    events: Any                       # iterator of dicts (or None for a keep-alive comment)


# ------------------------------------------------------------------ state
class AgentsState:
    def __init__(self):
        self.cv = threading.Condition()
        self.agents, self.envs, self.sessions = {}, {}, {}
        self.log: dict[str, list] = {}        # session_id -> events
        self.items: dict[str, list] = {}
        self.turns: dict[str, list] = {}
        self.artifacts: dict[str, dict] = {}
        self.idem: dict[tuple, str] = {}
        self.idle_timeout = 300.0

    def emit(self, sid: str, ev: dict):
        with self.cv:
            ev = {"event_id": _id("evt"), **ev}
            self.log[sid].append(ev)
            self.cv.notify_all()
        return ev


def state_of(server) -> AgentsState:
    if not hasattr(server, "_agents"):
        server._agents = AgentsState()
    return server._agents


# ------------------------------------------------------------------ envelope helpers (C-2)
def page(objs: list, after, limit, order) -> dict:
    limit = 20 if limit is None else limit
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise WireError(400, "args.type", "limit must be an integer between 1 and 100")
    if order not in (None, "asc", "desc"):
        raise WireError(400, "args.type", "order must be 'asc' or 'desc'")
    seq = list(reversed(objs)) if (order or "desc") == "desc" else list(objs)
    if after:
        ids = [o["id"] for o in seq]
        if after not in ids:
            raise WireError(404, "agents.cursor_not_found", "after cursor not found")
        seq = seq[ids.index(after) + 1:]
    data = seq[:limit]
    return {"object": "list", "data": data, "first_id": data[0]["id"] if data else None,
            "last_id": data[-1]["id"] if data else None, "has_more": len(seq) > limit}


# ------------------------------------------------------------------ adapter selection (C-3)
def select_adapter(server, principal, meta: dict, model: str | None) -> str:
    """path > X-EBX-Adapter header > model string equal to an adapter name > agents.default > the only mounted adapter."""
    def ok(a):
        op = server.reg.get(f"agents.{a}.sessions.create")
        return op is not None and server.policy.mounted(op, principal)
    for cand in (meta.get("adapter_path"), meta.get("adapter_header")):
        if cand:
            if cand not in ADAPTERS:
                raise WireError(404, "op.not_enabled", "operation is not enabled")
            return cand
    if model in ADAPTERS:
        return model
    default = getattr(server, "agents_default", None)
    if default:
        return default
    mounted = [a for a in ADAPTERS if ok(a)]
    if len(mounted) == 1:
        return mounted[0]
    if not mounted:
        raise WireError(404, "op.not_enabled", "operation is not enabled")
    raise WireError(400, "agents.adapter_required",
                    f"several adapters are mounted ({', '.join(mounted)}): pick one with the /agents/<adapter>/v1 base URL, "
                    f"the X-EBX-Adapter header or `agents.default`")


# ------------------------------------------------------------------ object builders
def agent_obj(model, instructions=None, name=None, metadata=None, tools=None, **extra) -> dict:
    now = int(time.time())
    return {"id": _id("agent"), "object": "agent", "created_at": now, "updated_at": now, "model": model,
            "instructions": instructions, "name": name, "metadata": metadata or {}, "tools": tools or [],
            "multi_agent": {"enabled": False, "max_concurrent_subagents": None},
            "reasoning": {"effort": None, "summary": None},
            "service_tier": "auto", "text": {"format": {"type": "text"}, "verbosity": "medium"}}


def session_obj(st: AgentsState, s: dict) -> dict:
    out = {k: v for k, v in s.items() if not k.startswith("_")}
    out["agent"] = st.agents[s["_agent_id"]]
    return out


def _text_of(inp) -> str:
    if isinstance(inp, str):
        return inp
    parts = []
    for m in inp or []:
        if isinstance(m, str):
            parts.append(m)
        elif isinstance(m, dict):
            c = m.get("content", m.get("text", ""))
            parts.append(_text_of(c) if not isinstance(c, str) else c)
    return "\n".join(p for p in parts if p)


def _turn(st, sid, agent_id, status, **kw):
    now = int(time.time())
    return {"id": kw.pop("id", None) or _id("turn"), "object": "agent.session.turn", "session_id": sid, "agent_id": agent_id,
            "status": status, "created_at": now, "started_at": now, "completed_at": None, "error": None,
            "subagent_id": None, "usage": None, **kw}


def run_turn(st: AgentsState, sid: str, text: str):
    """Echo adapter. Sync-callable; the HTTP layer runs it on a thread."""
    s = st.sessions[sid]
    s["status"] = "in_progress"
    s["last_active_at"] = int(time.time())
    sess = lambda: session_obj(st, s)
    st.emit(sid, {"type": "agent.session.in_progress", "session": sess()})
    t = _turn(st, sid, s["_agent_id"], "in_progress")
    st.turns[sid].append(t)
    st.emit(sid, {"type": "agent.session.turn.created", "session_id": sid, "turn_id": t["id"], "turn": dict(t)})
    user = {"id": _id("item"), "type": "message", "role": "user", "status": "completed", "turn_id": t["id"],
            "content": [{"type": "input_text", "text": text}]}
    st.items[sid].append(user)
    reply = f"echo: {text}"
    msg = {"id": _id("item"), "type": "message", "role": "assistant", "status": "completed", "turn_id": t["id"],
           "phase": "final_answer", "content": [{"type": "output_text", "text": reply, "annotations": []}]}
    st.emit(sid, {"type": "agent.session.turn.output_text.delta", "session_id": sid, "turn_id": t["id"],
                  "item_id": msg["id"], "output_index": 0, "content_index": 0, "delta": reply})
    st.items[sid].append(msg)
    st.emit(sid, {"type": "agent.session.turn.item.done", "session_id": sid, "turn_id": t["id"], "item": msg})
    aid = _id("art")
    st.artifacts[aid] = {"id": aid, "object": "agent.session.artifact", "session_id": sid, "turn_id": t["id"],
                         "environment_id": s["environment"].get("id", ""), "path": "result.txt",
                         "size_bytes": len(reply), "created_at": int(time.time()), "_data": reply.encode()}
    t.update(status="completed", completed_at=int(time.time()), usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    st.emit(sid, {"type": "agent.session.turn.completed", "session_id": sid, "turn_id": t["id"], "turn": dict(t),
                  "usage": t["usage"]})
    s["status"] = "idle"
    s["last_active_at"] = int(time.time())
    st.emit(sid, {"type": "agent.session.idle", "session": sess()})


def _subscribe(st: AgentsState, sid: str, after: str | None = None):
    """Idle-open stream (C-4): starts at 'now'; closes after the post-turn idle it observed, or on failed/delete."""
    with st.cv:
        log = st.log[sid]
        pos = len(log)
        if after:                                           # extension: replay after an event id (not in the official API)
            ids = [e["event_id"] for e in log]
            if after in ids:
                pos = ids.index(after) + 1

    def gen():
        nonlocal pos
        seen_turn, last = False, time.time()
        while True:
            with st.cv:
                if sid not in st.log:
                    return
                while pos >= len(st.log[sid]):
                    st.cv.wait(timeout=0.5)
                    if sid not in st.log:
                        return
                    if time.time() - last > st.idle_timeout:
                        return
                    if pos >= len(st.log[sid]):
                        yield None                       # keep-alive comment
                ev = st.log[sid][pos]
                pos += 1
            last = time.time()
            yield ev
            if ev["type"] == "agent.session.turn.created":
                seen_turn = True
            if ev["type"] == "agent.session.failed" or (ev["type"] == "agent.session.idle" and seen_turn):
                return
    return gen()


# ------------------------------------------------------------------ ops
def register(reg):
    from .server import REG  # noqa: F401  (ensures base registry loaded)

    def need(st, sid):
        if sid not in st.sessions:
            raise WireError(404, "agents.not_found", "session not found")
        return st.sessions[sid]

    @reg.op("agents.runtimes.list", effects="read", group="agents", http=("GET /agents/runtimes",))
    def runtimes_list(ctx) -> dict:
        data = []
        for a in ADAPTERS:
            o = ctx.server.reg.get(f"agents.{a}.sessions.create")
            if o is not None and ctx.server.policy.mounted(o, ctx.principal):
                data.append({"id": a, "object": "agent.runtime", "experimental": a in EXPERIMENTAL_ADAPTERS, "installed": False})
        return {"object": "list", "data": data, "first_id": data[0]["id"] if data else None,
                "last_id": data[-1]["id"] if data else None, "has_more": False}

    @reg.op("agents.definitions.create", effects="write", group="agents", http=("POST /v1/agents",))
    def agents_create(ctx, model: str, instructions: str | None = None, name: str | None = None,
                      metadata: dict | None = None, tools: list | None = None) -> dict:
        st = state_of(ctx.server)
        a = agent_obj(model, instructions, name, metadata, tools)
        st.agents[a["id"]] = a
        return a

    @reg.op("agents.definitions.get", effects="read", group="agents", http=("GET /v1/agents/{agent_id}",))
    def agents_get(ctx, agent_id: str) -> dict:
        a = state_of(ctx.server).agents.get(agent_id)
        if not a:
            raise WireError(404, "agents.not_found", "agent not found")
        return a

    @reg.op("agents.definitions.update", effects="write", group="agents", http=("POST /v1/agents/{agent_id}",))
    def agents_update(ctx, agent_id: str, model: str | None = None, instructions: str | None = None,
                      name: str | None = None, metadata: dict | None = None) -> dict:
        a = agents_get(ctx, agent_id)
        for k, v in (("model", model), ("instructions", instructions), ("name", name), ("metadata", metadata)):
            if v is not None:
                a[k] = v
        a["updated_at"] = int(time.time())
        return a

    @reg.op("agents.definitions.list", effects="read", group="agents", http=("GET /v1/agents",))
    def agents_list(ctx, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        return page(list(state_of(ctx.server).agents.values()), after, limit, order)

    @reg.op("agents.definitions.delete", effects="delete", group="agents", http=("DELETE /v1/agents/{agent_id}",))
    def agents_delete(ctx, agent_id: str) -> dict:
        agents_get(ctx, agent_id)
        del state_of(ctx.server).agents[agent_id]
        return {"id": agent_id, "deleted": True, "object": "agent.deleted"}

    @reg.op("agents.environments.create", effects="write", group="agents", http=("POST /v1/agents/environments",))
    def env_create(ctx, environment: dict, vault_ids: list | None = None) -> dict:
        if environment.get("type") not in ("openai_hosted", "self_hosted"):
            raise WireError(400, "args.invalid", "environment.type must be self_hosted (openai_hosted is accepted as an alias)")
        st = state_of(ctx.server)
        e = {"id": _id("env"), "object": "agent.environment", "type": "self_hosted", "status": "ready", "files": [],
             "plugins": [], "skills": []}
        st.envs[e["id"]] = e
        return e

    @reg.op("agents.environments.get", effects="read", group="agents", http=("GET /v1/agents/environments/{environment_id}",))
    def env_get(ctx, environment_id: str) -> dict:
        e = state_of(ctx.server).envs.get(environment_id)
        if not e:
            raise WireError(404, "agents.not_found", "environment not found")
        return e

    @reg.op("agents.environments.list", effects="read", group="agents", http=("GET /v1/agents/environments",))
    def env_list(ctx, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        return page(list(state_of(ctx.server).envs.values()), after, limit, order)

    @reg.op("agents.environments.files.create", effects="write", group="agents",
            http=("POST /v1/agents/environments/{environment_id}/files",))
    def env_files_create(ctx, environment_id: str) -> dict:
        raise WireError(404, "agents.not_supported", "environment files are reserved for a later release")

    @reg.op("agents.environments.files.list", effects="read", group="agents",
            http=("GET /v1/agents/environments/{environment_id}/files",))
    def env_files_list(ctx, environment_id: str) -> dict:
        raise WireError(404, "agents.not_supported", "environment files are reserved for a later release")

    @reg.op("agents.sessions.create", effects=("exec", "net"), group="agents", agent_scope=True,
            http=("POST /v1/agents/sessions",), stream="sse")
    def sessions_create(ctx, environment: dict, agent_id: str | None = None, agent: dict | None = None,
                        input: Any = None, metadata: dict | None = None, stream: bool = False,
                        vault_ids: list | None = None, spend_control: dict | None = None):
        st = state_of(ctx.server)
        etype = (environment or {}).get("type")
        if etype == "openai_hosted":
            raise WireError(400, "agents.environment_unsupported", "openai_hosted environments are not available here; "
                                                                    "use self_hosted or none")
        if etype not in ("none", "self_hosted"):
            raise WireError(400, "args.invalid", "environment.type must be none or self_hosted")
        if etype == "none" and input is None:
            raise WireError(400, "args.missing", "environment none requires input")
        if agent_id:
            if agent_id not in st.agents:
                raise WireError(404, "agents.not_found", "agent not found")
            a = st.agents[agent_id]
        elif agent:
            a = agent_obj(**{k: v for k, v in agent.items() if k in ("model", "instructions", "name", "metadata", "tools")})
            st.agents[a["id"]] = a
        else:
            raise WireError(400, "args.missing", "agent_id or agent is required")
        adapter = select_adapter(ctx.server, ctx.principal, ctx.meta, a["model"])
        ctx.server.check_also(f"agents.{adapter}.sessions.create", ctx.principal)       # second policy gate
        sid, now = _id("sess"), int(time.time())
        env = {"type": "none"} if etype == "none" else {
            "type": "self_hosted", "id": environment.get("id") or _id("env"), "capability_directories": [],
            "remote_url": "local://sandbox", "workspace_directory": ctx.paths.get("cwd", "/")}
        s = {"id": sid, "object": "agent.session", "created_at": now, "last_active_at": now, "status": "idle",
             "metadata": metadata or {}, "environment": env, "error": None, "required_actions": [], "usage": None,
             "vault_ids": vault_ids or [], "_agent_id": a["id"], "_adapter": adapter}
        if spend_control is not None:
            s["spend_control"] = spend_control
        with st.cv:
            st.sessions[sid] = s
            st.log[sid], st.items[sid], st.turns[sid] = [], [], []
        st.emit(sid, {"type": "agent.session.created", "session": session_obj(st, s)})
        sub = _subscribe(st, sid) if stream else None
        if input is not None:
            threading.Thread(target=run_turn, args=(st, sid, _text_of(input)), daemon=True).start()
        return SSE(sub) if stream else session_obj(st, s)

    @reg.op("agents.sessions.get", effects="read", group="agents", http=("GET /v1/agents/sessions/{session_id}",))
    def sessions_get(ctx, session_id: str) -> dict:
        st = state_of(ctx.server)
        return session_obj(st, need(st, session_id))

    @reg.op("agents.sessions.update", effects="write", group="agents", http=("POST /v1/agents/sessions/{session_id}",))
    def sessions_update(ctx, session_id: str, metadata: dict | None = None) -> dict:
        st = state_of(ctx.server)
        s = need(st, session_id)
        if metadata is not None:
            s["metadata"] = metadata
        return session_obj(st, s)

    @reg.op("agents.sessions.list", effects="read", group="agents", http=("GET /v1/agents/sessions",))
    def sessions_list(ctx, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        st = state_of(ctx.server)
        return page([session_obj(st, s) for s in st.sessions.values()], after, limit, order)

    @reg.op("agents.sessions.delete", effects="delete", group="agents", http=("DELETE /v1/agents/sessions/{session_id}",))
    def sessions_delete(ctx, session_id: str) -> dict:
        st = state_of(ctx.server)
        need(st, session_id)
        with st.cv:
            for d in (st.sessions, st.log, st.items, st.turns):
                d.pop(session_id, None)
            st.artifacts = {k: v for k, v in st.artifacts.items() if v["session_id"] != session_id}
            st.cv.notify_all()
        return {"id": session_id, "deleted": True, "object": "agent.session.deleted"}

    @reg.op("agents.sessions.send_event", effects=("exec", "net"), group="agents", agent_scope=True,
            http=("POST /v1/agents/sessions/{session_id}/events",))
    def send_event(ctx, session_id: str, events: list):
        st = state_of(ctx.server)
        s = need(st, session_id)
        if not isinstance(events, list) or not events:
            raise WireError(400, "args.invalid", "events must be a non-empty list")
        key = ctx.meta.get("idempotency_key")
        digest = hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest()
        if key:                                                      # IS-I1: same key + different body = 409
            prev = st.idem.get((session_id, key))
            if prev is not None:
                if prev != digest:
                    raise WireError(409, "idempotency.mismatch", "Idempotency-Key reused with a different request")
                return Raw(202)
        adapter = s["_adapter"]
        ctx.server.check_also(f"agents.{adapter}.sessions.send_event", ctx.principal)
        texts = []
        for ev in events:
            t = ev.get("type") if isinstance(ev, dict) else None
            if t == "agent.session.input.message":
                texts.append(_text_of(ev.get("input")))
            elif t == "agent.session.input.cancel":
                continue                                              # cancel is an input event, not an op
            elif t in ("agent.session.input.tool_result", "agent.session.input.computer_use_approval_request_result"):
                raise WireError(400, "agents.tool_result_unsupported", "tool results are not supported by this server")
            else:
                raise WireError(400, "args.invalid", f"unsupported event type {t!r}")
        if texts:
            if s["status"] != "idle":
                raise WireError(409, "agents.session_busy", "session is not idle")
            s["status"] = "in_progress"                               # claim before the thread starts
            threading.Thread(target=run_turn, args=(st, session_id, "\n".join(texts)), daemon=True).start()
        if key:
            st.idem[(session_id, key)] = digest
        return Raw(202)

    @reg.op("agents.sessions.stream_events", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/events",), stream="sse")
    def stream_events(ctx, session_id: str, after: str | None = None):
        st = state_of(ctx.server)
        need(st, session_id)
        return SSE(_subscribe(st, session_id, after))

    @reg.op("agents.sessions.list_items", effects="read", group="agents", http=("GET /v1/agents/sessions/{session_id}/items",))
    def list_items(ctx, session_id: str, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        st = state_of(ctx.server)
        need(st, session_id)
        return page(st.items[session_id], after, limit, order)

    @reg.op("agents.sessions.turns.list", effects="read", group="agents", http=("GET /v1/agents/sessions/{session_id}/turns",))
    def turns_list(ctx, session_id: str, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        st = state_of(ctx.server)
        need(st, session_id)
        return page(st.turns[session_id], after, limit, order)

    @reg.op("agents.sessions.turns.get", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/turns/{turn_id}",))
    def turns_get(ctx, session_id: str, turn_id: str) -> dict:
        st = state_of(ctx.server)
        need(st, session_id)
        for t in st.turns[session_id]:
            if t["id"] == turn_id:
                return t
        raise WireError(404, "agents.not_found", "turn not found")

    @reg.op("agents.sessions.turns.list_items", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/turns/{turn_id}/items",))
    def turn_items(ctx, session_id: str, turn_id: str, after: str | None = None, limit: int | None = None,
                   order: str | None = None) -> dict:
        st = state_of(ctx.server)
        need(st, session_id)
        return page([i for i in st.items[session_id] if i["turn_id"] == turn_id], after, limit, order)

    def _art(st, session_id, artifact_id):
        need(st, session_id)
        a = st.artifacts.get(artifact_id)
        if not a or a["session_id"] != session_id:
            raise WireError(404, "agents.not_found", "artifact not found")
        return a

    pub = lambda a: {k: v for k, v in a.items() if not k.startswith("_")}

    @reg.op("agents.sessions.artifacts.list", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/artifacts",))
    def art_list(ctx, session_id: str, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        st = state_of(ctx.server)
        need(st, session_id)
        return page([pub(a) for a in st.artifacts.values() if a["session_id"] == session_id], after, limit, order)

    @reg.op("agents.sessions.artifacts.get", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id}",))
    def art_get(ctx, session_id: str, artifact_id: str) -> dict:
        return pub(_art(state_of(ctx.server), session_id, artifact_id))

    @reg.op("agents.sessions.artifacts.content", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/artifacts/{artifact_id}/content",))
    def art_content(ctx, session_id: str, artifact_id: str):
        return Raw(200, _art(state_of(ctx.server), session_id, artifact_id)["_data"], "application/octet-stream")

    @reg.op("agents.sessions.artifacts.delete", effects="delete", group="agents",
            http=("DELETE /v1/agents/sessions/{session_id}/artifacts/{artifact_id}",))
    def art_delete(ctx, session_id: str, artifact_id: str) -> dict:
        st = state_of(ctx.server)
        _art(st, session_id, artifact_id)
        del st.artifacts[artifact_id]
        return {"id": artifact_id, "deleted": True, "object": "agent.session.artifact.deleted"}

    @reg.op("agents.sessions.traces.list", effects="read", group="agents", http=("GET /v1/agents/sessions/{session_id}/traces",))
    def traces_list(ctx, session_id: str, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        need(state_of(ctx.server), session_id)
        return page([], after, limit, order)

    @reg.op("agents.sessions.subagents.list", effects="read", group="agents",
            http=("GET /v1/agents/sessions/{session_id}/subagents",))
    def subagents_list(ctx, session_id: str, after: str | None = None, limit: int | None = None, order: str | None = None) -> dict:
        need(state_of(ctx.server), session_id)
        return page([], after, limit, order)

    for opid, route, eff in (
            ("agents.sessions.subagents.get", "GET /v1/agents/sessions/{session_id}/subagents/{subagent_id}", "read"),
            ("agents.sessions.subagents.list_items", "GET /v1/agents/sessions/{session_id}/subagents/{subagent_id}/items", "read"),
            ("agents.sessions.subagents.turns.list", "GET /v1/agents/sessions/{session_id}/subagents/{subagent_id}/turns", "read"),
            ("agents.sessions.subagents.turns.get", "GET /v1/agents/sessions/{session_id}/subagents/{subagent_id}/turns/{turn_id}", "read"),
            ("agents.sessions.subagents.turns.list_items",
             "GET /v1/agents/sessions/{session_id}/subagents/{subagent_id}/turns/{turn_id}/items", "read")):
        names = re.findall(r"{(\w+)}", route)

        def mk(names):
            import inspect
            def h(ctx, **kw):
                raise WireError(404, "agents.not_supported", "subagents are not supported by this server")
            h.__signature__ = inspect.Signature([inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD)] + [
                inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY, annotation=str) for n in names] + [
                inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str | None)
                for n in ("after", "limit", "order")])
            h.__annotations__ = {n: str for n in names}
            return h
        reg.op(opid, effects=eff, group="agents", http=(route,))(mk(names))


# ------------------------------------------------------------------ routing
def route_table(reg):
    """(method, regex, op_id, path-param names) for every op bound under /v1."""
    rows = []
    for op in reg.all().values():
        for h in op.http:
            m, p = h.split(" ", 1)
            if p.startswith("/v1/agents") or p == "/v1/agents":
                pat = re.sub(r"{(\w+)}", r"(?P<\1>[^/]+)", p)
                rows.append((m, re.compile("^" + pat + "$"), op.id, p.count("{")))
    rows.sort(key=lambda r: (r[3], -len(r[1].pattern)))      # literal routes before parameterised ones
    return rows
