"""Prototype: policy engine v2.1 (allow = OR of statements, deny >= allow in reach, scope-required, veto-only hooks)."""
from __future__ import annotations
import dataclasses, difflib, os, time, types
from typing import Any, Callable

from .core import Operation
from .guards import (CommandScope, Denied, PathScope, UrlScope, argv_denied, check_command, check_url, filter_env,
                     normalise_argv, parse_duration, parse_size, path_denied, resolve_path)

PERMISSIONS = ("read-only", "workspace-write", "full")


@dataclasses.dataclass(frozen=True)
class Principal:
    id: str = "anonymous"
    roles: tuple = ()
    claims: Any = dataclasses.field(default_factory=lambda: types.MappingProxyType({}))
    authenticated: bool = True

    def __post_init__(self):
        if self.id == "anonymous":                     # the id is reserved for unauthenticated callers
            object.__setattr__(self, "authenticated", False)
        object.__setattr__(self, "claims", types.MappingProxyType(dict(self.claims)))
        object.__setattr__(self, "roles", tuple(self.roles))

    def __hash__(self):
        return hash((self.id, self.roles))


@dataclasses.dataclass
class Deny:
    reason: str = ""
    code: str = "policy.denied_by_hook"


@dataclasses.dataclass
class Limits:
    max_bytes: int | None = None
    timeout: float | None = None
    max_entries: int | None = None
    max_output_bytes: int | None = None
    rate: str | None = None            # "10/min"
    concurrency: int | None = None
    cpu_seconds: int | None = None
    memory: int | None = None
    processes: int | None = None

    def __post_init__(self):
        self.max_bytes = parse_size(self.max_bytes)
        self.max_output_bytes = parse_size(self.max_output_bytes)
        self.memory = parse_size(self.memory)
        self.timeout = parse_duration(self.timeout)

    def narrowed(self, other: "Limits | None") -> "Limits":
        if other is None:
            return self
        out = dataclasses.replace(self)
        for f in dataclasses.fields(self):
            a, b = getattr(self, f.name), getattr(other, f.name)
            if f.name == "rate":
                out.rate = b if a is None else a if b is None else min((a, b), key=_rate_per_sec)
            elif a is None or b is None:
                setattr(out, f.name, b if a is None else a)
            else:
                setattr(out, f.name, min(a, b))
        return out


def _rate_per_sec(r: str) -> float:
    n, per = r.split("/")
    return int(n) / {"s": 1, "sec": 1, "min": 60, "m": 60, "h": 3600, "hour": 3600}[per.strip()]


@dataclasses.dataclass
class Narrow:
    limits: Limits | None = None


@dataclasses.dataclass(frozen=True)
class AgentScope:
    """Required by every allow statement that admits an agent exec op (run, sessions.create, send_event)."""
    workdir: PathScope | None = None
    permissions: str | None = None          # read-only | workspace-write | full ; None = not decided = refused
    commands: CommandScope | None = None
    models: tuple = ()
    max_turns: int | None = None
    unconfined_ok: bool = False

    def __post_init__(self):
        if self.permissions is not None and self.permissions not in PERMISSIONS:
            raise ValueError(f"permissions must be one of {PERMISSIONS}, got {self.permissions!r}")
        if isinstance(self.workdir, str):
            object.__setattr__(self, "workdir", PathScope(self.workdir))

    def lint(self):
        out = []
        if self.permissions == "full" and not self.unconfined_ok:
            out.append("error: AgentScope(permissions='full') without unconfined_ok=True")
        if self.permissions == "workspace-write" and self.workdir is not None and self.workdir.readonly:
            out.append("error: AgentScope permissions workspace-write contradicts a readonly workdir")
        return out


@dataclasses.dataclass
class Rule:
    kind: str                           # allow | deny
    selectors: tuple
    principals: tuple = ()              # () == everyone;  "id:grader" / "role:admin" / "*" (authenticated)
    paths: PathScope | None = None
    commands: CommandScope | None = None
    limits: Limits | None = None
    hook: Callable | None = None
    reason: str = ""
    name: str = ""
    urls: UrlScope | None = None
    agents: AgentScope | None = None

    def specificity(self, op: Operation) -> int:
        best = 0
        for s in self.selectors:
            if s == op.id: best = max(best, 4)
            elif s.endswith(".*") or s.endswith(".**"): best = max(best, 3)
            elif s.startswith("effect:") or s.startswith("group:"): best = max(best, 2)
            elif s in ("*", "**"): best = max(best, 1)
        return best


def selector_matches(sel: str, op: Operation, side: str = "allow") -> bool:
    """side='allow': explicit-only ops (admin effect, install, env.set, reload ...) match ONLY their exact id.
    side='deny': every selector reaches every op, explicit-only included (IS-P4)."""
    sel = str(sel)
    if side == "allow" and op.explicit and sel != op.id:
        return False
    if sel in ("*", "**"):
        return True
    if sel.startswith("effect:"):
        want = sel[7:]
        return (want in op.effects) if side == "deny" else (op.effects <= {want})
    if sel.startswith("group:"):
        return op.group == sel[6:]
    if sel.endswith(".**"):
        return op.id.startswith(sel[:-2])
    if sel.endswith(".*"):
        pre = sel[:-1]
        return op.id.startswith(pre) and "." not in op.id[len(pre):]
    return sel == op.id


def _pmatch(rule: Rule, pr: Principal) -> bool:
    if not rule.principals:
        return True
    keys = {f"id:{pr.id}"} | {f"role:{r}" for r in pr.roles}
    if pr.authenticated:
        keys.add("*")
    return bool(keys & set(rule.principals))


@dataclasses.dataclass
class Decision:
    allowed: bool
    status: int = 200
    code: str = ""
    message: str = ""
    rule: str = ""
    resolved: dict = dataclasses.field(default_factory=dict)
    limits: Limits | None = None
    argv: list | None = None
    executable: str | None = None
    env: dict | None = None
    scope: PathScope | None = None
    commands: CommandScope | None = None
    agents: AgentScope | None = None
    urls: UrlScope | None = None


@dataclasses.dataclass(frozen=True)
class AuthContext:
    """Frozen view handed to hooks: nothing here can be mutated to change what the handler later does (IS-P5)."""
    op: Operation
    args: Any
    principal: Principal
    paths: Any
    argv: tuple | None
    scope: Any = None

    @property
    def resolved(self):
        return self.paths


class Policy:
    def __init__(self, rules=(), hooks=()):
        self.rules: list[Rule] = list(rules)
        self.hooks: list[Callable] = list(hooks)
        self.audit_sinks: list[Callable] = []

    # builder API -------------------------------------------------------
    def allow(self, *selectors, principals=(), paths=None, commands=None, urls=None, agents=None, limits=None,
              authorize=None, name=""):
        if not selectors:
            raise ValueError("allow() needs at least one selector, e.g. allow(ops.files.download, paths=...)")
        if isinstance(limits, dict):
            limits = Limits(**limits)
        if isinstance(paths, (str, list, tuple)):
            paths = PathScope(paths) if isinstance(paths, str) else PathScope(*paths)
        if isinstance(commands, (list, tuple, str)):
            commands = CommandScope(allow=commands)
        principals = (principals,) if isinstance(principals, str) else tuple(principals)
        self.rules.append(Rule("allow", tuple(map(str, selectors)), principals, paths, commands, limits,
                               authorize, name=name, urls=urls, agents=agents))
        return self

    def deny(self, *selectors, principals=(), paths=None, commands=None, reason="", name=""):
        if not selectors:
            raise ValueError("deny() needs at least one selector")
        if isinstance(paths, (str, list, tuple)):
            paths = PathScope(deny=paths, _anywhere=True)         # deny rules: paths are glob patterns only
        if isinstance(commands, (list, tuple, str)):
            commands = CommandScope(deny=commands)
        principals = (principals,) if isinstance(principals, str) else tuple(principals)
        self.rules.append(Rule("deny", tuple(map(str, selectors)), principals, paths, commands, None,
                               None, reason, name))
        return self

    def without(self, *selectors, reason="removed from this policy"):
        return self.deny(*selectors, reason=reason)

    def authorize(self, fn):
        self.hooks.append(fn)
        return fn

    def audit(self, sink):
        self.audit_sinks.append(sink)
        return sink

    def __add__(self, other):
        return Policy(self.rules + other.rules, self.hooks + other.hooks)

    # static checks -----------------------------------------------------
    def validate(self, registry):
        problems = []
        ids = list(registry.all())
        for n, r in enumerate(self.rules, 1):
            for sel in r.selectors:
                if sel in ("*", "**"):
                    continue
                if not any(selector_matches(sel, o, r.kind) for o in registry.all().values()):
                    near = difflib.get_close_matches(sel, ids, n=1, cutoff=0.6)
                    problems.append(f"rule {n}: selector {sel!r} matches no operation"
                                    + (f"; did you mean {near[0]!r}?" if near else
                                       "; explicit-only operations must be named exactly" if r.kind == "allow" else ""))
        return problems

    def lint(self, registry=None):
        if registry is None:
            from .server import REG as registry
        out = []
        write_roots = []
        for r in self.rules:
            if r.kind == "allow" and r.paths is not None and not r.paths.readonly:
                write_roots += [os.path.realpath(x) for x in r.paths.roots]
        seen = set()
        for r in self.rules:
            if r.kind != "allow":
                continue
            for op in registry.all().values():
                if not any(selector_matches(s, op, "allow") for s in r.selectors):
                    continue
                for what, need, have in self._scope_needs(op, r):
                    if need and not have and (op.id, what) not in seen:
                        seen.add((op.id, what))
                        out.append(f"error config.scope_required: allow({', '.join(r.selectors)}) admits {op.id} which takes "
                                   f"a {what} parameter, but the statement has no {what} scope")
            if r.commands is not None:
                out += r.commands.lint(write_roots)
            if r.paths is not None and r.paths.anywhere_unsafe:
                out.append("error: PathScope.anywhere(unsafe=True) in an allow statement")
            if r.agents is not None:
                out += r.agents.lint()
        return out

    @staticmethod
    def _scope_needs(op, r):
        need = [p for p in op.path_params if not (p == "cwd" and op.command_param)]
        yield "path", bool(need) and not all(p in op.path_scopes for p in need), r.paths is not None
        yield "command", bool(op.command_param), r.commands is not None
        yield "url", bool(op.url_params), r.urls is not None
        yield "agent", op.agent_scope, r.agents is not None and r.agents.permissions is not None

    # evaluation --------------------------------------------------------
    def mounted(self, op: Operation, pr: Principal | None = None) -> bool:
        if op.id == "core.health":
            return True
        return any(r.kind == "allow" and any(selector_matches(s, op, "allow") for s in r.selectors)
                   and (pr is None or _pmatch(r, pr)) for r in self.rules)

    def record(self, op_id, pr, allowed, code="", rule="", paths=()):
        for sink in self.audit_sinks:
            try:
                sink({"ts": time.time(), "op": op_id, "principal": pr.id, "allowed": allowed, "code": code,
                      "rule": rule, "paths": list(paths)})
            except Exception:
                pass

    def decide(self, op: Operation, args: dict, pr: Principal) -> Decision:
        d = self._decide(op, args, pr)
        self.record(op.id, pr, d.allowed, d.code, d.rule, d.resolved.values())
        return d

    def _anchors(self, op, pr):
        out = []
        for r in self.rules:
            if r.kind == "allow" and r.paths is not None and _pmatch(r, pr) and \
                    any(selector_matches(s, op, "allow") for s in r.selectors):
                try:
                    out += [os.path.realpath(x) for x in r.paths.bind(pr).roots]
                except Denied:
                    pass
        for sc in op.path_scopes.values():
            out += [os.path.realpath(x) for x in sc.roots]
        return list(dict.fromkeys(out))

    def _decide(self, op, args, pr) -> Decision:
        if not self.mounted(op, pr) and op.id != "core.health":
            return Decision(False, 404, "op.not_enabled", "operation is not enabled")
        sel = [r for r in self.rules if any(selector_matches(s, op, r.kind) for s in r.selectors) and _pmatch(r, pr)]
        # 1. deny: same reach as allow (relative paths, descendants, argv+command, explicit-only ops)
        for r in sel:
            if r.kind != "deny":
                continue
            if r.paths is None and r.commands is None:
                return Decision(False, 403, "policy.denied_by_rule", r.reason or "denied by policy", r.name)
            if r.paths is not None:
                anchors = self._anchors(op, pr)
                for pn in dict.fromkeys(list(op.path_params) + (["cwd"] if op.command_param else [])):
                    raw = args.get(pn)
                    for v in (raw if isinstance(raw, list) else [raw]):
                        if v is None:
                            continue
                        if not isinstance(v, str) or "\x00" in v:
                            return Decision(False, 403, "policy.path_invalid", "invalid path", r.name)
                        cands = [os.path.normpath(v)] if os.path.isabs(v) else \
                            [os.path.normpath(os.path.join(a, v)) for a in anchors] or [os.path.normpath("/" + v)]
                        for c in cands:
                            if path_denied(r.paths.deny, c) or path_denied(r.paths.deny, os.path.realpath(c)):
                                return Decision(False, 403, "policy.path_denied", "path matches a deny rule", r.name)
            if r.commands is not None and op.command_param:
                try:
                    argv = normalise_argv(args.get(op.command_param), args.get("argv"), bool(args.get("shell")))
                except Denied as exc:
                    return Decision(False, 403, exc.code, exc.message, r.name)
                if argv_denied(r.commands.deny, argv):
                    return Decision(False, 403, "policy.command_denied", "command matches a deny rule", r.name)
        # 2. allow statements, most specific first; first admitting statement wins
        allows = sorted((r for r in sel if r.kind == "allow"), key=lambda r: -r.specificity(op))
        if not allows:
            if op.id == "core.health":
                return Decision(True, rule="core.health")
            return Decision(False, 404, "op.not_enabled", "operation is not enabled")
        last: Denied | None = None
        for r in allows:
            try:
                dec = self._admit(r, op, args, pr)
            except Denied as exc:
                last = last or exc
                continue
            ctx = AuthContext(op, types.MappingProxyType(dict(args)), pr, types.MappingProxyType(dict(dec.resolved)),
                              tuple(dec.argv) if dec.argv else None, dec.scope)
            for hook in ([r.hook] if r.hook else []) + self.hooks:
                try:
                    out = hook(ctx)
                except Exception as exc:                      # fail closed
                    return Decision(False, 403, "policy.hook_error", f"authorize hook failed: {type(exc).__name__}")
                if out is None or out is True:
                    continue
                if isinstance(out, Narrow):
                    dec.limits = (dec.limits or Limits()).narrowed(out.limits)
                    continue
                if out is False or isinstance(out, Deny):     # exact types only; anything else denies
                    return Decision(False, 403, getattr(out, "code", "policy.denied_by_hook"),
                                    getattr(out, "reason", "") or "denied by authorize hook", r.name)
                return Decision(False, 403, "policy.hook_bad_return", "authorize hook returned an unsupported value")
            dec.rule = r.name or "+".join(r.selectors)
            return dec
        return Decision(False, last.details.get("status", 403) if last else 403,
                        last.code if last else "policy.not_permitted", last.message if last else "")

    def _admit(self, r: Rule, op: Operation, args: dict, pr: Principal) -> Decision:
        scope = r.paths.bind(pr) if r.paths is not None else None
        dec = Decision(True, limits=r.limits, scope=scope, commands=r.commands, agents=r.agents, urls=r.urls)
        effect = "write" if ({"write", "delete"} & op.effects) else "read"
        for pn in op.path_params:
            if args.get(pn) is None or (pn == "cwd" and op.command_param):
                continue
            if scope is None and pn not in op.path_scopes:
                raise Denied("policy.scope_required", f"{op.id} takes a path but the statement has no PathScope")
            raw = args[pn]
            if scope is not None:
                dec.resolved[pn] = [resolve_path(scope, x, effect) for x in raw] if isinstance(raw, list) \
                    else resolve_path(scope, raw, effect)
        for pn, sc in op.path_scopes.items():            # the op's own jail: always applied
            if args.get(pn) is not None:
                cur = dec.resolved.get(pn, args[pn])
                dec.resolved[pn] = resolve_path(sc.bind(pr), cur, effect)
                if dec.scope is None:
                    dec.scope = sc.bind(pr)
        if op.command_param:
            if r.commands is None:
                raise Denied("policy.scope_required", f"{op.id} runs commands but the statement has no CommandScope")
            cs = r.commands
            if args.get("cwd"):
                if cs.cwd is None:
                    raise Denied("policy.scope_required", "a cwd argument needs a cwd scope on the statement")
                dec.resolved["cwd"] = resolve_path(cs.cwd.bind(pr), args["cwd"], "read")
            elif cs.cwd is not None:
                dec.resolved["cwd"] = os.path.realpath(cs.cwd.bind(pr).roots[0])       # never the server cwd (IS-P1b)
            else:
                dec.resolved["cwd"] = "/"
            argv, exe, _eff = check_command(
                dataclasses.replace(cs, cwd=cs.cwd.bind(pr)) if cs.cwd is not None else cs,
                args.get(op.command_param), args.get("argv"), bool(args.get("shell")))
            dec.argv, dec.executable = argv, exe
            dec.env = filter_env(cs, args.get("env"))
        for pn in op.url_params:
            if args.get(pn) is not None:
                if r.urls is None:
                    raise Denied("policy.scope_required", f"{op.id} takes a URL but the statement has no UrlScope")
                dec.resolved[pn] = check_url(r.urls, args[pn])
        if op.agent_scope:
            if r.agents is None or r.agents.permissions is None:
                raise Denied("policy.scope_required", f"{op.id} starts an agent: the statement needs "
                                                      f"AgentScope(permissions=...) (read-only | workspace-write | full)")
        return dec
