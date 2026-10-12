"""Prototype facade = the names promised by the reference card (09): policy builders, presets, SandboxServer, start,
config loader, HTTP transport (design v2.1)."""
from __future__ import annotations
import collections, dataclasses, difflib, hashlib, hmac, inspect, json, os, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote

from . import agents_wire
from .catalog import (ADAPTERS, AGENT_FAMILY, AGENT_GENERIC, CATALOG, EXPERIMENTAL_ADAPTERS, EXPLICIT_IDS,
                      GROUP_OF_NAMESPACE, URL_OPS)
from .core import OpRef, Registry, ops
from .guards import (CommandScope, Denied, PathScope, UrlScope, harden_process, parse_duration, parse_size, protect_dir,
                     snapshot_env)
from .policy import AgentScope, Deny, Limits, Narrow, Policy, Principal, selector_matches
from .server import REG, Server

__all__ = ["Policy", "ops", "op", "presets", "PathScope", "CommandScope", "UrlScope", "AgentScope", "Limits", "Deny",
           "Narrow", "Principal", "SandboxServer", "Registry", "start", "start_http", "from_config", "check_config",
           "configure", "ConfigError", "PolicyError", "legacy_diff"]


class ConfigError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class PolicyError(ConfigError):
    pass


class AuthConflict(Exception):
    pass


# ------------------------------------------------------------------ catalog stubs
def _make_stub(paths=(), command=None, urls=()):
    names = list(paths) + list(urls) + ([command] if command else [])
    names += ["cwd", "argv", "env", "shell", "timeout"] if command else []
    seen = list(dict.fromkeys(names))

    def stub(ctx, **kw):
        return {"stub": True}
    stub.__signature__ = inspect.Signature([inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD)] + [
        inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str) for n in seen])
    stub.__annotations__ = {n: str for n in seen}
    return stub


def _register_catalog(reg: Registry):
    for id_, eff, group, binds, paths, command in CATALOG:
        if reg.get(id_):
            continue
        urls = URL_OPS.get(id_, ())
        reg.op(id_, effects=tuple(eff.split("+")), http=tuple(f"{m} {p}" for m, p, _ in binds), paths=paths,
               command=command, group=group, explicit=id_ in EXPLICIT_IDS, urls=urls)(_make_stub(paths, command, urls))
    agents_wire.register(reg)
    for id_, eff, binds in AGENT_GENERIC:
        if reg.get(id_):
            continue
        reg.op(id_, effects=tuple(eff.split("+")), http=tuple(f"{m} {p}" for m, p, _ in binds), group="agents")(_make_stub())
    for a in ADAPTERS:
        for suffix, eff, scoped, explicit in AGENT_FAMILY:
            reg.op(f"agents.{a}.{suffix}", effects=tuple(eff.split("+")), group="agents", agent_scope=scoped,
                   explicit=explicit)(_make_stub())


_register_catalog(REG)
BUILTIN_IDS = frozenset(REG.all())


def op(op_id, **kw):
    """Module-level @op (registers into the default registry)."""
    return REG.op(op_id, **kw)


# ------------------------------------------------------------------ presets
def _root(root=None, **aliases):
    for k in ("paths", "workspace"):
        if aliases.get(k) is not None:
            root = aliases[k]
    return root


def _need_root(name, root):
    if root is None:
        raise ValueError(f"presets.{name}() needs root=... (aliases: paths=, workspace=); there is no default root")
    return root if isinstance(root, PathScope) else PathScope(root)


_FILES_RO = ("list", "stat", "download", "download_stream")


class presets:
    @staticmethod
    def minimal():
        return Policy().allow(ops.core.health, ops.core.capabilities, ops.core.describe, ops.core.check)

    @staticmethod
    def files_readonly(root=None, *, paths=None, workspace=None, deny=("**/.env", "**/*.pem")):
        sc = _need_root("files_readonly", _root(root, paths=paths, workspace=workspace))
        if deny:
            sc = dataclasses.replace(sc, deny=tuple(sc.deny) + tuple(deny))
        return presets.minimal() + Policy().allow(*[ops.files[x] for x in _FILES_RO],
                                                  paths=dataclasses.replace(sc, readonly=True))

    @staticmethod
    def readonly(root=None, *, paths=None, workspace=None):
        sc = _need_root("readonly", _root(root, paths=paths, workspace=workspace))
        return presets.files_readonly(sc) + Policy().allow(ops.system.info, ops.system.metrics, ops.process.list,
                                                           ops.process.get, ops.process.output)

    @staticmethod
    def download_only(root=None, *, paths=None, workspace=None, deny=("**/.env",), max_bytes="100MB"):
        r = _need_root("download_only", _root(root, paths=paths, workspace=workspace))
        return presets.minimal() + Policy().allow(
            ops.files.download, ops.files.download_stream, ops.files.stat, ops.files.list,
            paths=dataclasses.replace(r, deny=tuple(r.deny) + tuple(deny), readonly=True, max_bytes=parse_size(max_bytes)))

    @staticmethod
    def commands_only(root=None, *, allow=(), paths=None, workspace=None, timeout=60, **_):
        r = _need_root("commands_only", _root(root, paths=paths, workspace=workspace))
        cs = allow if isinstance(allow, CommandScope) else CommandScope(allow=allow, cwd=dataclasses.replace(r, readonly=True),
                                                                        timeout=timeout)
        return presets.minimal() + Policy().allow(ops.commands.run, ops.commands.stream, commands=cs)

    @staticmethod
    def workspace_jail(root=None, *, paths=None, workspace=None, readonly=False, commands=None):
        r = _need_root("workspace_jail", _root(root, paths=paths, workspace=workspace))
        sc = dataclasses.replace(r, readonly=readonly, deny=tuple(r.deny) + ("**/.env", "**/*.pem", "**/.git/config"))
        p = presets.minimal() + Policy().allow("files.*", paths=sc).allow(ops.system.info)
        if commands:
            cs = commands if isinstance(commands, CommandScope) else CommandScope(allow=commands, cwd=sc)
            p.allow(ops.commands.run, ops.commands.stream, commands=cs)
        return p

    @staticmethod
    def ci_runner(root=None, *, workspace=None, paths=None, commands=(), timeout=600, writable=False):
        """Commands + a READ-ONLY workspace by default: command allowlists plus writable files are code execution."""
        r = _need_root("ci_runner", _root(root, paths=paths, workspace=workspace))
        cwd = dataclasses.replace(r, readonly=not writable)
        p = presets.minimal() + Policy().allow("files.list", "files.stat", "files.download", paths=cwd)
        p.allow(ops.commands.run, ops.commands.stream, commands=CommandScope(allow=commands, cwd=cwd, timeout=timeout))
        if writable:
            p.allow("files.upload", "files.mkdir", paths=cwd)
        return p

    @staticmethod
    def agent_host(root=None, *, agents=("codex",), workspace=None, paths=None, permissions="read-only"):
        r = _need_root("agent_host", _root(root, paths=paths, workspace=workspace))
        scope = AgentScope(workdir=dataclasses.replace(r, deny=tuple(r.deny) + ("**/.env",)), permissions=permissions)
        p = presets.minimal() + Policy().allow(
            *[o for o in ("agents.definitions.create", "agents.definitions.get", "agents.definitions.update",
                          "agents.definitions.list", "agents.definitions.delete", "agents.environments.create",
                          "agents.environments.get", "agents.environments.list", "agents.sessions.get",
                          "agents.sessions.update", "agents.sessions.list", "agents.sessions.delete",
                          "agents.sessions.stream_events", "agents.sessions.list_items", "agents.sessions.turns.list",
                          "agents.sessions.turns.get", "agents.sessions.turns.list_items", "agents.sessions.artifacts.list",
                          "agents.sessions.artifacts.get", "agents.sessions.artifacts.content",
                          "agents.sessions.artifacts.delete", "agents.sessions.traces.list",
                          "agents.sessions.subagents.list", "agents.runtimes.list", "agents.models.list")])
        names = ["agents.sessions.create", "agents.sessions.send_event"]
        for a in agents:
            names += [f"agents.{a}.run", f"agents.{a}.sessions.create", f"agents.{a}.sessions.send_event"]
        return p.allow(*names, agents=scope, name="agent_host")

    @staticmethod
    def full_access(root=None, commands=None, *, unsafe=False):
        """Every non-explicit group. Needs a root + a CommandScope, or unsafe=True (lint error)."""
        if (root is None or commands is None) and not unsafe:
            raise ValueError("full_access() needs root=... and commands=CommandScope(...); or pass unsafe=True")
        sc = PathScope.anywhere(unsafe=True) if root is None else PathScope(root)
        cs = commands or CommandScope.unrestricted(unsafe=True)
        return (Policy().allow("group:core", "group:system")
                .allow("group:file_ops", paths=sc).allow("group:process", "group:commands", commands=cs))


LEGACY_IDS = sorted({i for i, _e, _g, binds, _p, _c in CATALOG if any(b[2] for b in binds)})


def _legacy_compat(env_set: bool | None = None):
    """What a v1 server exposed, as an explicit (and loudly unsafe) policy: for migrations only."""
    if env_set is None:
        env_set = os.environ.get("EBX_SERVER_LEGACY_ENV_SET") == "1"
    pol = (Policy().allow("group:core", "group:system").allow("group:file_ops", paths=PathScope.anywhere(unsafe=True))
           .allow("group:process", "group:commands", ops.terminal.create, ops.process.signal,
                  commands=CommandScope.unrestricted(unsafe=True)))
    pol.allow("group:terminal", "group:dev_tools", "group:browser", commands=CommandScope.unrestricted(unsafe=True),
              paths=PathScope.anywhere(unsafe=True), urls=UrlScope(hosts=("*",), schemes=("http", "https"), block_private=False))
    if env_set:
        pol.allow(ops.system.env.set)
    return pol


presets.legacy_compat = staticmethod(_legacy_compat)


def legacy_diff(server: "SandboxServer", principal=None):
    """`check-config` output for migrations: legacy ids that v1 served and this policy does not mount."""
    pr = principal or Principal("anonymous", ("admin",))
    return [i for i in LEGACY_IDS if not server.policy.mounted(server.reg.get(i), pr)]


# ------------------------------------------------------------------ server
def default_state_dir() -> str:
    d = os.environ.get("EBX_SERVER_STATE_DIR")
    if d:
        return d
    return "/var/lib/easy-sandbox" if os.geteuid() == 0 else os.path.join(os.path.expanduser("~"), ".local", "state",
                                                                         "easy-sandbox")


def prepare_state_dir(path: str) -> str:
    """0700 and owned by us (IS-L1): refuse a pre-created directory owned by someone else or group/world writable."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    st = os.stat(path)
    if st.st_uid != os.geteuid() or st.st_mode & 0o022:
        raise ConfigError("config.state_dir_unsafe", f"{path} must be owned by the server user and not group/world writable")
    protect_dir(path)
    return path


class SandboxServer(Server):
    def __init__(self, policy=None, authenticate=None, tokens=None, registry=None, *, verbose=False, state_dir=None,
                 agents_default=None, trusted_proxies=(), strict=True):
        reg = registry or Registry()
        reg._ops = dict(REG._ops)
        super().__init__(policy, reg, verbose)
        reg.frozen = True
        self._auth, self._tokens = authenticate, dict(tokens or {})
        self._anonymous = Principal("anonymous", ("admin",)) if not (authenticate or tokens) else None
        self.max_request_bytes = 100 * 2**20
        self.agents_default = agents_default
        self.trusted_proxies = tuple(trusted_proxies)
        self.state_dir = prepare_state_dir(state_dir) if state_dir else None
        protect_dir(default_state_dir())
        snapshot_env()
        self._fail: dict = collections.defaultdict(list)
        if strict:
            problems = self.policy.validate(self.reg)
            if problems:
                raise PolicyError("config.unknown_selector", "; ".join(problems))

    @property
    def open_mode(self):
        return self._auth is None and not self._tokens

    def authenticate(self, headers) -> Principal | None:
        """`headers`: lower-cased mapping. Authorization wins; X-Access-Token is the legacy alias; both present and
        different -> AuthConflict (401). Returns None for 'no valid credential'."""
        h = {str(k).lower(): v for k, v in dict(headers).items()}
        if self._auth:
            try:
                pr = self._auth(h)
            except Exception:
                return None
            return pr if isinstance(pr, Principal) else None
        auth = h.get("authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        xat = h.get("x-access-token", "").strip()
        if bearer and xat and not hmac.compare_digest(bearer.encode(), xat.encode()):
            raise AuthConflict()
        tok = bearer or xat
        if self.open_mode:
            return self._anonymous
        fp = hashlib.sha256(tok.encode()).hexdigest()[:16]
        now = time.time()
        recent = [t for t in self._fail[fp] if now - t < 60]
        if len(recent) >= 10:
            raise PermissionError("rate")
        for secret, pr in self._tokens.items():
            if tok and hmac.compare_digest(tok.encode(), secret.encode()):
                return pr
        self._fail[fp] = recent + [now]
        return None

    def call(self, op_id, principal=None, **args):
        return self.invoke(op_id, args, principal or self._anonymous or Principal("anonymous", ("admin",)))

    def check(self, policy_problems=True):
        out = (self.policy.validate(self.reg) if policy_problems else []) + self.policy.lint(self.reg) + self.reg.lint()
        for o in self.reg.all().values():
            if not self.policy.mounted(o, None) and not any(
                    r.kind == "allow" and any(selector_matches(x, o, "allow") for x in r.selectors) for r in self.policy.rules):
                if o.id not in BUILTIN_IDS:
                    out.append(f"warn: op {o.id!r} is registered but no rule mounts it")
        for a in ADAPTERS:
            if a in EXPERIMENTAL_ADAPTERS and self.policy.mounted(self.reg.get(f"agents.{a}.sessions.create"), None):
                out.append(f"warn: adapter {a!r} is experimental")
        known = {r for t in self._tokens.values() for r in t.roles} | {f"id:{t.id}" for t in self._tokens.values()}
        if self._tokens:
            for r in self.policy.rules:
                for p in r.principals:
                    if p != "*" and (p.startswith("role:") and p[5:] not in {x for t in self._tokens.values() for x in t.roles}
                                     or p.startswith("id:") and p[3:] not in {t.id for t in self._tokens.values()}):
                        out.append(f"warn: principal selector {p!r} matches no configured token")
        if self.open_mode and self.exec_capable():
            out.append("error config.open_exec: no authentication is configured but this policy mounts exec-capable "
                       "operations; configure auth.tokens or start with allow_open=True")
        return out

    def explain(self, op_id, args=None, principal=None):
        """Dry-run of the policy pipeline: what would happen, which rule decides (serve --explain-denials / `explain`)."""
        pr = principal or self._anonymous or Principal("anonymous", ())
        o = self.reg.get(op_id)
        if o is None:
            return {"op": op_id, "allowed": False, "code": "op.not_enabled", "why": "no such operation"}
        d = self.policy.decide(o, dict(args or {}), pr)
        return {"op": op_id, "allowed": d.allowed, "status": d.status, "code": d.code, "rule": d.rule, "message": d.message,
                "resolved": dict(d.resolved)}

    def exec_capable(self):
        return [o.id for o in self.reg.all().values()
                if ({"exec", "admin"} & o.effects) and self.policy.mounted(o, None) and o.id != "core.health"]

    def assert_startable(self, host: str, allow_open: bool = False):
        if self.open_mode and not allow_open:
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise ConfigError("config.open_non_loopback", "open mode (no auth) refused on a non-loopback bind")
            ex = self.exec_capable()
            if ex:
                raise ConfigError("config.open_exec", f"open mode refused: policy mounts exec-capable ops ({ex[:3]}...); "
                                                      f"configure auth.tokens")


# ------------------------------------------------------------------ transport
_BAD_TARGET = re.compile(r"(//|/\./|/\.\./|/\.$|/\.\.$|%2f|%2e|%5c|\\|\x00|%00)", re.I)
_STATUS_TYPE = {400: "invalid_request_error", 401: "authentication_error", 403: "permission_error",
                404: "not_found_error", 409: "invalid_request_error", 413: "invalid_request_error",
                415: "invalid_request_error", 429: "rate_limit_error"}


def split_target(target: str):
    """Reject request-target tricks before routing (IS-A8). Returns (path, query)."""
    if not target.startswith("/") or _BAD_TARGET.search(target.split("?", 1)[0]) or "\x00" in target:
        raise Denied("request.bad_target", "malformed request target", status=400)
    path, _, query = target.partition("?")
    return (path.rstrip("/") or "/"), query


def _compile_routes(reg):
    rows = []
    for o in reg.all().values():
        for h in o.http:
            m, p = h.split(" ", 1)
            pat = re.sub(r"{(\w+)}", r"(?P<\1>[^/]+)", p)
            rows.append((m, re.compile("^" + pat + "$"), o.id, p.count("{"), p.startswith("/v1/")))
    rows.sort(key=lambda r: (r[3], -len(r[1].pattern)))
    return rows


def _coerce(op, args):
    for p in op.params:
        v = args.get(p.name)
        if isinstance(v, str) and p.type in ("integer", "boolean", "number"):
            try:
                args[p.name] = {"integer": int, "number": float, "boolean": lambda x: x.lower() in ("1", "true")}[p.type](v)
            except ValueError:
                raise Denied("args.type", f"{p.name} must be {p.type}", status=400)
    return args


def start_http(server: SandboxServer, port=0, host="127.0.0.1", *, allow_open=False, allowed_hosts=(), allowed_origins=(),
               header_timeout=3.0, max_pre_auth=64, allow_lint_errors=False):
    server.assert_startable(host, allow_open)
    bad = [m for m in server.check() if m.startswith("error") and "open_exec" not in m]
    if bad and not allow_lint_errors:
        raise ConfigError("config.lint_errors", "; ".join(bad[:3]))
    harden_process()
    routes = _compile_routes(server.reg)
    pre_auth = threading.BoundedSemaphore(max_pre_auth)
    hosts_ok = set(allowed_hosts)

    class H(BaseHTTPRequestHandler):
        timeout = header_timeout                         # socket timeout: slow headers/bodies are dropped (IS-A3)
        protocol_version = "HTTP/1.0"

        def log_message(self, *a):
            pass

        def _wire(self, path):
            return path.startswith("/v1/") or re.match(r"^/agents/[a-z_]+/v1/", path) is not None

        def _err(self, code, obj, wire=False, retry=None):
            if wire:
                err = {"message": obj.get("error", ""), "type": _STATUS_TYPE.get(code, "api_error"),
                       "param": None, "code": obj.get("code")}
                obj = {"error": err}
                retry = (code in (429,) or code >= 500) if retry is None else retry
                self._send(code, obj, {"x-should-retry": "true" if retry else "false"})
            else:
                self._send(code, obj)

        def _go(self):
            self._slot = pre_auth.acquire(blocking=False)
            try:
                if not self._slot:
                    return self._send(503, {"error": "too many unauthenticated connections", "code": "request.busy"})
                self._go_inner()
            except (ConnectionError, TimeoutError):
                self.close_connection = True
            finally:
                self._release()

        def _release(self):
            if getattr(self, "_slot", False):
                self._slot = False
                pre_auth.release()

        def _go_inner(self):
            hdr = {k.lower(): v for k, v in self.headers.items()}
            try:
                path, query = split_target(self.requestline.split(" ")[1] if self.requestline.count(" ") >= 2 else self.path)
            except Denied as exc:
                return self._send(400, {"error": exc.message, "code": exc.code})
            hh = hdr.get("host", "")
            okh = {f"127.0.0.1:{self.server.server_address[1]}", f"localhost:{self.server.server_address[1]}",
                   f"[::1]:{self.server.server_address[1]}"} | hosts_ok
            if hh not in okh:
                return self._send(403, {"error": "host not allowed", "code": "request.host_denied"})
            if hdr.get("origin") and hdr["origin"] not in allowed_origins:
                return self._send(403, {"error": "cross-origin requests are not accepted", "code": "request.origin_denied"})
            wire = self._wire(path)
            try:
                pr = server.authenticate(hdr)
            except AuthConflict:
                return self._err(401, {"error": "conflicting credentials", "code": "auth.conflicting_credentials"}, wire)
            except PermissionError:
                return self._err(429, {"error": "too many failed attempts", "code": "auth.rate_limited"}, wire)
            if pr is None:
                return self._err(401, {"error": "authentication required", "code": "auth.required"}, wire)
            self._release()                                  # the pre-auth pool only bounds unauthenticated work
            n = int(hdr.get("content-length") or 0)
            if n > server.max_request_bytes:
                return self._err(413, {"error": "request too large", "code": "limit.request_too_large"}, wire)
            body = {}
            if n:
                ctype = hdr.get("content-type", "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    return self._err(415, {"error": "Content-Type must be application/json", "code": "request.bad_content_type"}, wire)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except (ValueError, UnicodeDecodeError):
                    return self._err(400, {"error": "invalid JSON", "code": "request.bad_json"}, wire)
                if not isinstance(body, dict):
                    return self._err(400, {"error": "JSON body must be an object", "code": "request.bad_json"}, wire)
            meta = {}
            m = re.match(r"^/agents/([a-z_]+)(/v1/.*)$", path)
            if m:
                meta["adapter_path"], path = m.group(1), m.group(2)
            if hdr.get("x-ebx-adapter"):
                meta["adapter_header"] = hdr["x-ebx-adapter"]
            if hdr.get("idempotency-key"):
                meta["idempotency_key"] = hdr["idempotency-key"]
            if path.startswith("/ops/") and self.command == "POST":
                return self._run(path[5:], body, pr, meta, wire)
            if path == "/ops" and self.command == "GET":
                vis = {i: v for i, v in server.describe(pr).items() if v["mounted"]}
                return self._send(200, vis)
            q = dict(parse_qsl(query))
            for method, rx, op_id, _n, is_wire in routes:
                mm = rx.match(path)
                if mm and method == self.command:
                    o = server.reg.get(op_id)
                    args = {**(q if self.command in ("GET", "DELETE") else {}), **body,
                            **{k: unquote(v) for k, v in mm.groupdict().items()}}
                    if is_wire:
                        args = {k: v for k, v in args.items() if k in {p.name for p in o.params}}
                    try:
                        args = _coerce(o, args)
                    except Denied as exc:
                        return self._err(400, {"error": exc.message, "code": exc.code}, wire)
                    return self._run(op_id, args, pr, meta, wire)
            return self._err(404, {"error": "operation is not enabled", "code": "op.not_enabled"}, wire)

        def _run(self, op_id, args, pr, meta, wire):
            code, out = server.invoke(op_id, args, pr, meta)
            if code != 200:
                return self._err(code, out, wire)
            if isinstance(out, agents_wire.Raw):
                body = out.body if isinstance(out.body, bytes) else (json.dumps(out.body).encode() if out.body is not None else b"")
                self.send_response(out.status)
                self.send_header("Content-Type", out.content_type)
                self.send_header("Content-Length", str(len(body)))
                for k, v in out.headers.items():
                    self.send_header(k, v)
                self.end_headers()
                return self.wfile.write(body)
            if isinstance(out, agents_wire.SSE):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.flush()
                try:
                    for ev in out.events:
                        chunk = b": keep-alive\n\n" if ev is None else \
                            f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode()
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self._send(200, out)

        def _send(self, code, obj, extra=None):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)
        do_GET = do_POST = do_DELETE = _go

    class _S(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):          # timeouts/resets are routine; no tracebacks
            pass

    httpd = _S((host, port), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def start(policy=None, *, config=None, port=0, host="127.0.0.1", **kw):
    """Programmatic entry point (card section 3). `config` is a dict, a path to JSON/YAML, or a ServerConfig-like mapping."""
    if config is not None:
        if isinstance(config, (str, os.PathLike)):
            text = open(config).read()
            config = json.loads(text) if str(config).endswith(".json") else __import__("yaml").safe_load(text)
        srv = from_config(config)
        if policy is not None:
            srv.policy = srv.policy + policy
    else:
        srv = SandboxServer(policy)
    return srv, start_http(srv, port, host, **kw)


def configure(**kw):
    """Process-wide knobs (state dir). Kept deliberately tiny."""
    if "state_dir" in kw:
        os.environ["EBX_SERVER_STATE_DIR"] = str(kw["state_dir"])


# ------------------------------------------------------------------ config loader (JSON/YAML dict)
KNOWN_KEYS = {"version", "preset", "root", "paths", "workspace", "enable", "disable", "rules", "custom", "auth", "agents",
              "install", "audit", "load", "limits", "llm", "commands"}


def _rule_kwargs(r):
    kw = {}
    allowed = {"allow", "deny", "principals", "paths", "commands", "urls", "agents", "limits", "reason", "name"}
    bad = set(r) - allowed
    if bad:
        raise ConfigError("config.unknown_key", f"unknown key(s) {sorted(bad)} in a rule; allowed: {sorted(allowed)}")
    if "principals" in r:
        kw["principals"] = r["principals"]
    if "paths" in r:
        p = r["paths"]
        kw["paths"] = PathScope(**p) if isinstance(p, dict) else p
    if "commands" in r:
        c = dict(r["commands"])
        if "cwd" in c and isinstance(c["cwd"], dict):
            c["cwd"] = PathScope(**c["cwd"])
        kw["commands"] = CommandScope(**c)
    if "urls" in r:
        kw["urls"] = UrlScope(**r["urls"])
    if "agents" in r:
        a = dict(r["agents"])
        if isinstance(a.get("workdir"), dict):
            a["workdir"] = PathScope(**a["workdir"])
        kw["agents"] = AgentScope(**a)
    if "limits" in r:
        kw["limits"] = Limits(**r["limits"])
    return kw


def from_config(cfg: dict, server_kwargs=None) -> SandboxServer:
    """server.json / template.yaml `server:` block -> SandboxServer. Strict: unknown keys are errors."""
    cfg = dict(cfg)
    bad = set(cfg) - KNOWN_KEYS
    if bad:
        raise ConfigError("config.unknown_key", "; ".join(
            f"unknown key {k!r} in server config" + (f"; did you mean {difflib.get_close_matches(k, sorted(KNOWN_KEYS), 1)[0]!r}?"
                                                     if difflib.get_close_matches(k, sorted(KNOWN_KEYS), 1) else "")
            for k in sorted(bad)))
    pol = Policy()
    names = cfg.get("preset") or []
    names = [names] if isinstance(names, str) else names
    root = cfg.get("root") or cfg.get("paths") or cfg.get("workspace")
    for nm in names:
        key = nm.replace("-", "_")
        fn = getattr(presets, key, None)
        if fn is None or key.startswith("_"):
            raise ConfigError("config.unknown_preset", f"unknown preset {nm!r}; available: minimal, files_readonly, readonly, "
                                                       f"download_only, commands_only, workspace_jail, ci_runner, agent_host")
        kw = {}
        sig = inspect.signature(fn).parameters
        if "root" in sig and root is not None:
            kw["root"] = root
        if key == "agent_host" and cfg.get("agents"):
            kw["agents"] = tuple(a if isinstance(a, str) else a["name"] for a in cfg["agents"])
        if key in ("ci_runner", "commands_only") and cfg.get("commands"):
            kw["commands" if key == "ci_runner" else "allow"] = cfg["commands"]
        pol = pol + fn(**kw)
    for sel in cfg.get("enable", []):
        pol.allow(sel)
    for r in cfg.get("rules", []):
        kw = _rule_kwargs(r)
        kind = "allow" if "allow" in r else "deny"
        sels = r[kind]
        sels = [sels] if isinstance(sels, str) else sels
        if kind == "allow":
            pol.allow(*sels, **kw)
        else:
            pol.deny(*sels, reason=r.get("reason", ""), principals=r.get("principals", ()))
    if cfg.get("disable"):
        pol.deny(*cfg["disable"], reason="disabled by template")
    tokens = {}
    for t in (cfg.get("auth") or {}).get("tokens", []):
        env = t.get("token_env")
        if "token" in t:
            raise ConfigError("config.secret_inline", f"auth token {t.get('id')!r}: secrets must be environment references; "
                                                      f"use token_env: NAME")
        if t.get("id") == "anonymous":
            raise ConfigError("config.reserved_id", "the principal id 'anonymous' is reserved")
        secret = os.environ.get(env or "")
        if not secret:                                   # IS-A1: fail closed
            raise ConfigError("config.auth_secret_missing",
                              f"auth token {t.get('id')!r}: environment variable {env!r} is unset or empty; refusing to start")
        if len(secret) < 16:
            raise ConfigError("config.auth_secret_weak", f"{env} is shorter than 16 characters")
        tokens[secret] = Principal(t["id"], tuple(t.get("roles", ())))
    if not (cfg.get("auth") or {}).get("tokens") and os.environ.get("EBX_SERVER_TOKEN"):
        tokens[os.environ["EBX_SERVER_TOKEN"]] = Principal("default", ("admin",))
    kw = dict(server_kwargs or {})
    if cfg.get("agents"):
        d = [a for a in cfg["agents"] if isinstance(a, dict) and a.get("default")]
        if d:
            kw.setdefault("agents_default", d[0]["name"])
    strict = kw.pop("strict", True)
    srv = SandboxServer(pol, tokens=tokens, strict=False, **kw)
    srv.reg.frozen = False
    for name, c in (cfg.get("custom") or {}).items():
        _declarative_op(srv.reg, name, c)
    srv.reg.frozen = True
    problems = srv.policy.validate(srv.reg)
    if problems and strict:
        raise PolicyError("config.unknown_selector", "; ".join(problems))
    return srv


def _declarative_op(reg, name, c):
    allowed = {"argv", "params", "cwd", "timeout", "effects", "summary"}
    bad = set(c) - allowed
    if bad:
        raise ConfigError("config.unknown_key", f"custom.{name}: unknown key(s) {sorted(bad)}; allowed {sorted(allowed)}")
    argv_t, params, cwd = c["argv"], c.get("params", {}), c.get("cwd")
    path_params = tuple(k for k, v in params.items() if v.get("type") == "path")
    for k in path_params:
        if "root" not in params[k]:
            raise ConfigError("config.invalid", f"custom.{name} param {k!r} type path has no root")
    timeout = parse_duration(c.get("timeout", 60))

    def handler(ctx, **kw):
        argv = []
        for tok in argv_t:
            if tok.startswith("{") and tok.endswith("}") and tok[1:-1] in params:
                k = tok[1:-1]
                argv.append(ctx.paths[k] if k in path_params else str(kw[k]))
            else:
                argv.append(tok)
        r = ctx.run(argv, timeout=timeout, cwd=cwd)
        return {"exit_code": r.exit_code, "stdout": r.stdout[-4000:], "stderr": r.stderr[-2000:]}

    sig = [inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD)] + [
        inspect.Parameter(k, inspect.Parameter.KEYWORD_ONLY, annotation={"int": int}.get(v.get("type"), str))
        for k, v in params.items()]
    handler.__signature__ = inspect.Signature(sig)
    handler.__annotations__ = {k: {"int": int}.get(v.get("type"), str) for k, v in params.items()}
    roots = {k: params[k]["root"] for k in path_params}
    reg.op(f"custom.{name}", effects=tuple(c.get("effects", ["exec"])), paths=roots)(handler)
    return roots


def check_config(cfg: dict):
    try:
        srv = from_config(cfg)
    except ValueError as exc:
        return [f"ERROR {exc}"]
    return [f"WARN {m}" for m in srv.check()]
