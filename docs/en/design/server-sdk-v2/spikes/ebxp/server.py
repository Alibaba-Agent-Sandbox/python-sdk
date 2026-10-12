"""Prototype: builtin ops + dispatcher (design v2.1). The HTTP layer lives in api.py."""
from __future__ import annotations
import base64, collections, os, subprocess, time, types

from .core import Registry, ops
from .guards import (Denied, PathScope, ENV_NEVER, env_never, open_beneath, open_parent_beneath, resolve_path,
                     unlink_beneath)
from .policy import Policy, Principal, selector_matches

REG = Registry()
_RATE_UNITS = {"s": 1, "sec": 1, "min": 60, "m": 60, "h": 3600, "hour": 3600}


@REG.op("files.list", effects="read", http=("GET /files/list",), paths=("path",), group="file_ops", limits=("max_entries",))
def files_list(ctx, path: str, max_entries: int = 1000) -> dict:
    """List a directory."""
    real = ctx.paths["path"]
    cap = min(max_entries, (ctx.limits and ctx.limits.max_entries) or max_entries)
    out = []
    dfd = open_beneath(ctx.scope, real, os.O_RDONLY, want_dir=True)
    try:
        for e in sorted(os.scandir(dfd), key=lambda e: e.name)[:cap]:
            try:
                ctx.recheck(os.path.realpath(os.path.join(real, e.name)))     # denied/escaping entries are omitted
            except Denied:
                continue
            out.append({"name": e.name, "type": "directory" if e.is_dir(follow_symlinks=False) else "file"})
    finally:
        os.close(dfd)
    return {"entries": out}


@REG.op("files.stat", effects="read", http=("GET /files/stat",), paths=("path",), group="file_ops")
def files_stat(ctx, path: str) -> dict:
    real = ctx.paths["path"]
    try:
        st = os.stat(real)
    except FileNotFoundError:
        return {"path": real, "exists": False}
    return {"path": real, "exists": True, "size": st.st_size}


@REG.op("files.download", effects="read", http=("GET /files/download",), paths=("path",), group="file_ops", limits=("max_bytes",))
def files_download(ctx, path: str) -> dict:
    real = ctx.paths["path"]
    fd = open_beneath(ctx.scope, real, os.O_RDONLY)
    with os.fdopen(fd, "rb") as f:
        cap = min([c for c in ((ctx.scope and ctx.scope.max_bytes), (ctx.limits and ctx.limits.max_bytes),
                               100 * 2**20) if c])
        data = f.read(cap + 1)
    if len(data) > cap:
        raise Denied("limit.max_bytes", f"file exceeds {cap} bytes")
    return {"path": real, "content_base64": base64.b64encode(data).decode()}


@REG.op("files.upload", effects="write", http=("POST /files/upload",), paths=("path",), group="file_ops", limits=("max_bytes",))
def files_upload(ctx, path: str, content_base64: str) -> dict:
    real = ctx.paths["path"]
    data = base64.b64decode(content_base64)
    fd = open_beneath(ctx.scope, real, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return {"path": real, "bytes": len(data)}


@REG.op("files.delete", effects="delete", http=("DELETE /files",), paths=("path",), group="file_ops")
def files_delete(ctx, path: str) -> dict:
    unlink_beneath(ctx.scope, ctx.paths["path"])          # *at() on a parent fd opened with O_NOFOLLOW (IS-F2)
    return {"deleted": True}


@REG.op("commands.run", effects="exec", http=("POST /shell",), command="command", group="process", limits=("timeout",))
def commands_run(ctx, command: str = "", argv: list | None = None, cwd: str = "", env: dict | None = None,
                 shell: bool = False, timeout: int = 30) -> dict:
    cap = ctx.scope_commands.timeout_max
    p = subprocess.run(ctx.argv, executable=ctx.executable, env=ctx.env, cwd=ctx.paths.get("cwd") or "/",
                       capture_output=True, text=True, timeout=min(timeout, cap), shell=False)
    lim = ctx.scope_commands.max_output_bytes
    return {"stdout": p.stdout[:lim], "stderr": p.stderr[:lim], "exit_code": p.returncode}


@REG.op("system.env.set", effects=("admin", "write"), http=("POST /env",), group="system")
def system_env_set(ctx, name: str, value: str) -> dict:
    """Writes the server's env OVERLAY only (never os.environ); refuses PATH/LD_*/EBX_*/... (IS-A, IS-C2)."""
    if env_never(name) or name.startswith("EBX_"):
        raise Denied("policy.env_var_denied", f"environment variable {name!r} may not be set")
    ctx.env_overlay[name] = value
    return {"set": name}


class Ctx:
    """What a handler sees. Policy-resolved values only; hooks never get this object."""

    def __init__(self, decision, rule_scope, op, principal=None, args=None, env_overlay=None, server=None, meta=None):
        self.principal, self.args = principal, types.MappingProxyType(dict(args or {}))
        self.paths = decision.resolved
        self.limits = decision.limits
        self.scope = decision.scope
        self.argv, self.executable, self.env = decision.argv, decision.executable, decision.env
        self.scope_commands = rule_scope or decision.commands
        self.agents, self.urls = decision.agents, decision.urls
        self.op = op
        self.server, self.meta = server, meta or {}
        self.env_overlay = env_overlay if env_overlay is not None else {}

    def run(self, argv, timeout=60, cwd=None):
        """Sanctioned subprocess helper for custom ops: no shell, scrubbed env."""
        from .guards import snapshot_env
        env = {k: os.environ[k] for k in ("PATH", "LANG") if k in os.environ}
        p = subprocess.run(list(argv), env=env, cwd=cwd or "/", capture_output=True, text=True, timeout=timeout, shell=False)
        return types.SimpleNamespace(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)

    def recheck(self, full):
        resolve_path(self.scope, full)


_JT = {"integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
       "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
       "boolean": lambda v: isinstance(v, bool), "string": lambda v: isinstance(v, str),
       "array": lambda v: isinstance(v, list), "object": lambda v: isinstance(v, dict)}


class Server:
    def __init__(self, policy: Policy | None = None, registry: Registry = REG, verbose: bool = False):
        self.reg, self.policy = registry, policy or Policy()
        self.verbose = verbose
        self.env_overlay: dict = {}
        self._rate: dict = {}

    def _not_enabled(self, op_id, principal):
        self.policy.record(op_id, principal, False, "op.not_enabled")
        body = {"error": "operation is not enabled", "code": "op.not_enabled", "op": op_id}
        if self.verbose:                                   # suggestions only among ops THIS caller can see
            vis = [i for i, o in self.reg.all().items() if self.policy.mounted(o, principal)]
            import difflib
            sug = difflib.get_close_matches(op_id, vis, n=3, cutoff=0.6)
            if sug:
                body["error"] += f"; did you mean {sug}?"
        return 404, body

    def invoke(self, op_id, args: dict | None = None, principal: Principal = Principal(), meta: dict | None = None):
        op_id = str(op_id)
        op = self.reg.get(op_id)
        if op is None or not self.policy.mounted(op, principal):
            return self._not_enabled(op_id, principal)
        args = dict(args or {})
        unknown = set(args) - {p.name for p in op.params}
        if unknown:
            return 400, {"error": f"unknown argument(s) {sorted(unknown)}", "code": "args.unknown"}
        missing = [p.name for p in op.params if p.required and p.name not in args]
        if missing:
            return 400, {"error": f"missing argument(s) {missing}", "code": "args.missing"}
        for p in op.params:
            v = args.get(p.name)
            if v is None:
                continue
            if p.type in _JT and not _JT[p.type](v) or (p.name in op.limits and p.type == "integer" and v < 1):
                return 400, {"error": f"argument {p.name!r} must be {p.type}" + (" >= 1" if p.name in op.limits else ""),
                             "code": "args.type"}
        dec = self.policy.decide(op, args, principal)
        if not dec.allowed:
            return dec.status, {"error": dec.message, "code": dec.code, "op": op_id}
        if dec.limits and dec.limits.rate:
            n, per = dec.limits.rate.split("/")
            win = _RATE_UNITS[per.strip()]
            q = self._rate.setdefault((principal.id, op_id), collections.deque())
            now = time.time()
            while q and now - q[0] > win:
                q.popleft()
            if len(q) >= int(n):
                return 429, {"error": "rate limit exceeded", "code": "limit.rate", "op": op_id}
            q.append(now)
        ctx = Ctx(dec, dec.commands, op, principal, args, self.env_overlay, self, meta)
        try:
            return 200, op.handler(ctx, **args) if op.wants_ctx else op.handler(**args)
        except Denied as exc:
            status = exc.details.get("status") or (413 if exc.code.startswith("limit.") else 403)
            return status, {"error": exc.message, "code": exc.code, "op": op_id}
        except FileNotFoundError:
            return 404, {"error": "not found", "code": "files.not_found", "op": op_id}

    def check_also(self, op_id: str, principal: Principal, args: dict | None = None):
        """Second policy gate for generic ops that act through a named backend (agents.sessions.create ->
        agents.<adapter>.sessions.create). Raises Denied with the policy's own status and code."""
        op = self.reg.get(op_id)
        if op is None or not self.policy.mounted(op, principal):
            raise Denied("op.not_enabled", "operation is not enabled", status=404)
        dec = self.policy.decide(op, args or {}, principal)
        if not dec.allowed:
            raise Denied(dec.code, dec.message, status=dec.status)
        return dec

    def describe(self, principal=None):
        return {i: {"effects": sorted(o.effects), "http": list(o.http), "mounted": self.policy.mounted(o, principal),
                    "params": [p.name for p in o.params]} for i, o in sorted(self.reg.all().items())}

    def openapi(self):
        paths = {}
        for i, o in self.reg.all().items():
            for h in o.http or (f"POST /ops/{i}",):
                m, p = h.split(" ", 1)
                paths.setdefault(p, {})[m.lower()] = {"operationId": i, "x-effects": sorted(o.effects)}
        return {"openapi": "3.1.0", "info": {"title": "sandbox", "version": "2.1"}, "paths": paths}
