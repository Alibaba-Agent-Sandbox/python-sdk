"""Prototype: operation registry (feasibility spike, not production code)."""
from __future__ import annotations
import dataclasses, inspect, re, typing
from typing import Any, Callable

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
EFFECTS = {"read", "write", "delete", "exec", "net", "admin"}


class OpRef:
    """Attribute-path node: ops.files.list -> 'files.list'.  NOT a str subclass: a str subclass would
    shadow verbs that are str methods (ops.custom.format, ops.custom.split ...)."""
    __slots__ = ("_p",)

    def __init__(self, path):
        object.__setattr__(self, "_p", path)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return OpRef(f"{self._p}.{name}")

    __getitem__ = lambda self, name: OpRef(f"{self._p}.{name}")
    __str__ = lambda self: self._p
    __repr__ = lambda self: f"ops.{self._p}"
    __hash__ = lambda self: hash(self._p)
    __eq__ = lambda self, o: str(o) == self._p
    __fspath__ = None


class _Ops:
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return OpRef(name)

    __getitem__ = lambda self, name: OpRef(name)


ops = _Ops()
OpId = OpRef


@dataclasses.dataclass
class Param:
    name: str
    type: str
    required: bool
    default: Any = None
    doc: str = ""


@dataclasses.dataclass(eq=False)
class Operation:
    id: str
    handler: Callable
    effects: frozenset
    summary: str = ""
    http: tuple = ()
    params: tuple = ()
    path_params: tuple = ()        # names of args that are filesystem paths
    command_param: str | None = None
    limits: tuple = ()
    wants_ctx: bool = False
    group: str | None = None       # legacy CapabilityGroup value
    explicit: bool = False         # never matched by wildcard/group/effect selectors; must be named
    install: tuple = ()
    stream: str = "none"

    path_scopes: dict = dataclasses.field(default_factory=dict)   # intrinsic per-parameter jails
    effects_declared: bool = True
    agent_scope: bool = False      # needs AgentScope in every admitting statement (exec-effect agent ops)
    url_params: tuple = ()         # names of arguments that are URLs (UrlScope required)

    def __eq__(self, other):          # ctx.op == "files.upload" works in hooks
        return str(other) == self.id

    __hash__ = lambda self: hash(self.id)
    __str__ = lambda self: self.id

    @property
    def namespace(self):
        return self.id.rsplit(".", 1)[0]


_PYTYPES = {int: "integer", float: "number", bool: "boolean", str: "string", list: "array", dict: "object"}


def _jtype(tp):
    origin = typing.get_origin(tp)
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return _jtype(args[0]) if args else "null"
    if origin in (list, typing.List):
        return "array"
    if origin in (dict, typing.Dict):
        return "object"
    return _PYTYPES.get(tp, "string")


class Registry:
    def __init__(self):
        self._ops: dict[str, Operation] = {}
        self.frozen = False

    def op(self, op_id: str, *, effects: str | tuple | None = None, summary: str = "", http=(), paths=(),
           command: str | None = None, limits=(), group=None, install=(), stream="none", explicit=False,
           agent_scope=False, urls=()):
        op_id = str(op_id)
        http = (http,) if isinstance(http, str) else tuple(http)
        intrinsic = {}
        if isinstance(paths, dict):
            intrinsic, paths = dict(paths), tuple(paths)
        paths = (paths,) if isinstance(paths, str) else tuple(paths)
        limits = (limits,) if isinstance(limits, str) else tuple(limits)
        install = (install,) if isinstance(install, str) else tuple(install)
        if not _ID_RE.match(op_id):
            raise ValueError(f"invalid operation id {op_id!r}: use dotted lowercase, e.g. 'files.list'")
        declared = effects is not None
        if effects is None:
            effects = "admin"                      # fail closed: an op that forgot `effects=` is explicit-only
        eff = frozenset([effects] if isinstance(effects, str) else effects)
        urls = (urls,) if isinstance(urls, str) else tuple(urls)
        bad = eff - EFFECTS
        if bad:
            raise ValueError(f"unknown effects {sorted(bad)}; allowed {sorted(EFFECTS)}")

        def deco(fn):
            if self.frozen:
                raise RuntimeError("registry frozen: register ops before constructing the server")
            if op_id in self._ops:
                raise ValueError(f"duplicate operation id {op_id!r}")
            sig = inspect.signature(fn)
            try:
                hints = typing.get_type_hints(fn)
            except Exception:
                hints = {}
            params, wants_ctx = [], False
            for i, (n, p) in enumerate(sig.parameters.items()):
                if i == 0 and n == "ctx":
                    wants_ctx = True
                    continue
                req = p.default is inspect._empty
                params.append(Param(n, _jtype(hints.get(n, str)), req, None if req else p.default))
            for pn in list(paths) + list(urls) + ([command] if command else []):
                if pn not in {q.name for q in params}:
                    raise ValueError(f"{op_id}: paths/command refers to unknown parameter {pn!r}")
            self._ops[op_id] = Operation(op_id, fn, eff, summary or (fn.__doc__ or "").strip().split("\n")[0],
                                         tuple(http), tuple(params), tuple(paths), command, tuple(limits),
                                         wants_ctx, group, explicit=explicit or "admin" in eff, install=tuple(install),
                                         stream=stream, effects_declared=declared, agent_scope=agent_scope,
                                         url_params=urls)
            from .guards import PathScope
            self._ops[op_id].path_scopes = {k: (v if isinstance(v, PathScope) else PathScope(v))
                                            for k, v in intrinsic.items()}
            return fn
        return deco

    _PATHY = {"path", "file", "dir", "directory", "cwd", "root", "target", "dest", "src", "filename", "folder"}

    def lint(self):
        out = []
        for i, o in sorted(self._ops.items()):
            undeclared = [p.name for p in o.params if p.name in self._PATHY and p.name not in o.path_params
                          and not (p.name == "cwd" and o.command_param)]
            for n in undeclared:
                out.append(f"{i}: parameter {n!r} looks like a path but is not declared in paths=; path scopes will not protect it")
            if not o.effects_declared:
                out.append(f"{i}: effects= not declared; defaulting to 'admin' (explicit-only). Declare effects=...")
            if o.effects == frozenset({"read"}) and o.command_param:
                out.append(f"{i}: declares a command parameter but only the 'read' effect")
        return out

    def get(self, op_id):
        return self._ops.get(op_id)

    def all(self):
        return dict(self._ops)

    def suggest(self, op_id):
        import difflib
        return difflib.get_close_matches(op_id, list(self._ops), n=3, cutoff=0.6)
