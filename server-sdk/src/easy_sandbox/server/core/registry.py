"""The operation registry: one place that knows every capability (design 02, sections 3-4)."""

from __future__ import annotations

import dataclasses
import inspect
import types
import typing
from typing import TYPE_CHECKING, Any

from .errors import RegistryFrozen
from .ids import validate_id

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

__all__ = [
    "CATALOG_VERSION",
    "EFFECTS",
    "EXPLICIT_ONLY_IDS",
    "HttpBinding",
    "Operation",
    "Param",
    "Registry",
]

CATALOG_VERSION = 1
EFFECTS = frozenset({"read", "write", "delete", "exec", "net", "admin"})

#: IDs that are explicit-only in addition to every op carrying the ``admin`` effect (03, section 2).
EXPLICIT_ONLY_IDS = frozenset(
    {"core.reload", "system.env.set", "terminal.create", "process.signal"}
)

#: Namespaces below ``agents`` that are not adapter names (adapter ``install`` is explicit-only).
_AGENT_GENERIC_NAMESPACES = frozenset(
    {"runtimes", "models", "definitions", "environments", "sessions", "vaults"}
)

_JSON_TYPES: dict[Any, str] = {
    int: "integer",
    float: "number",
    bool: "boolean",
    str: "string",
    list: "array",
    dict: "object",
}


@dataclasses.dataclass(frozen=True)
class Param:
    """One declared parameter of an operation."""

    name: str
    type: str = "string"
    required: bool = False
    default: Any = None


@dataclasses.dataclass(frozen=True)
class HttpBinding:
    """A REST binding of an operation (the RPC binding ``POST /ops/{id}`` always exists)."""

    method: str
    path: str
    legacy: bool = False


@dataclasses.dataclass(eq=False)
class Operation:
    """Metadata plus the callable behind one operation ID.

    ``legacy_route`` names the v1 route whose handler this operation calls; such operations are
    *wrappers*: the handler is looked up in the serving route table at call time.
    """

    id: str
    handler: Callable[..., Any] | None = None
    effects: frozenset[str] = frozenset({"admin"})
    summary: str = ""
    http: tuple[HttpBinding, ...] = ()
    params: tuple[Param, ...] = ()
    group: str | None = None
    stream: str = "none"
    since: str = "1.0"
    aliases: tuple[str, ...] = ()
    install: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    command: str | None = None
    urls: tuple[str, ...] = ()
    agent_scope: bool = False
    auth_required: bool = True
    wants_ctx: bool = False
    effects_declared: bool = True
    hidden: bool = False
    deprecated: str | None = None
    legacy_route: str | None = None
    fixed_path_params: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (Operation, str)):
            return str(other) == self.id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        return self.id

    @property
    def namespace(self) -> str:
        """Everything before the verb (``files`` for ``files.list``)."""
        return self.id.rsplit(".", 1)[0]

    @property
    def explicit(self) -> bool:
        """Explicit-only ops are never matched by wildcard, group or effect selectors (D26)."""
        if "admin" in self.effects or self.id in EXPLICIT_ONLY_IDS:
            return True
        parts = self.id.split(".")
        if parts[0] != "agents" or len(parts) < 3 or parts[1] in _AGENT_GENERIC_NAMESPACES:
            return False
        return parts[-1] == "install" or parts[-2:] == ["sessions", "create"]

    def entry(self) -> dict[str, Any]:
        """The catalog entry of this operation (design 02, section 7.1)."""
        return {
            "id": self.id,
            "summary": self.summary,
            "effects": sorted(self.effects),
            "explicit": self.explicit,
            "group": self.group,
            "http": [
                {"method": b.method, "path": b.path, **({"legacy": True} if b.legacy else {})}
                for b in self.http
            ],
            "rpc": f"/ops/{self.id}",
            "params": [
                {"name": p.name, "type": p.type, "required": p.required}
                | ({} if p.required else {"default": p.default})
                for p in self.params
            ],
            "limits": list(self.limits),
            "stream": self.stream,
            "install": list(self.install),
            "since": self.since,
            "aliases": list(self.aliases),
            "deprecated": self.deprecated,
        }


def _json_type(tp: Any) -> str:
    origin = typing.get_origin(tp)
    if origin is typing.Union or origin is getattr(types, "UnionType", None):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return _json_type(args[0]) if args else "null"
    if origin in (list, tuple):
        return "array"
    if origin is dict:
        return "object"
    return _JSON_TYPES.get(tp, "string")


def selector_matches(selector: str, op_id: str) -> bool:
    """Match an ID selector: exact, ``ns.*`` (one level), ``ns.**`` (any depth) or ``*``."""
    if selector == "*":
        return True
    if selector.endswith(".**"):
        return op_id.startswith(selector[:-2])
    if selector.endswith(".*"):
        prefix = selector[:-1]
        return op_id.startswith(prefix) and "." not in op_id[len(prefix) :]
    return selector == op_id


class Registry:
    """Operations by ID, with aliases and the prefix rule enforced at registration."""

    def __init__(self) -> None:
        self._ops: dict[str, Operation] = {}
        self._aliases: dict[str, str] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        """Whether registration is closed."""
        return self._frozen

    def freeze(self) -> None:
        """Close registration; later registrations raise :class:`RegistryFrozen`."""
        self._frozen = True

    def child(self) -> Registry:
        """Return an independent, unfrozen copy (per-server registries never share ops)."""
        clone = Registry()
        clone._ops = dict(self._ops)
        clone._aliases = dict(self._aliases)
        return clone

    # -- registration ---------------------------------------------------- #

    def register(self, operation: Operation) -> Operation:
        """Add *operation*; enforces grammar, uniqueness, the prefix rule and alias uniqueness."""
        if self._frozen:
            raise RegistryFrozen
        op_id = validate_id(operation.id)
        if op_id in self._ops:
            raise ValueError(f"duplicate operation id {op_id!r}")
        for existing in self._ops:
            if existing.startswith(op_id + ".") or op_id.startswith(existing + "."):
                raise ValueError(
                    f"operation id {op_id!r} conflicts with {existing!r}: "
                    "an ID may not be a prefix of another ID"
                )
        for alias in operation.aliases:
            if alias in self._aliases or alias in self._ops:
                raise ValueError(f"alias {alias!r} of {op_id!r} is already taken")
        self._ops[op_id] = operation
        for alias in operation.aliases:
            self._aliases[alias] = op_id
        return operation

    def op(
        self,
        op_id: Any,
        *,
        effects: str | Iterable[str] | None = None,
        summary: str = "",
        http: str | Iterable[str] = (),
        paths: str | Iterable[str] = (),
        command: str | None = None,
        limits: str | Iterable[str] = (),
        group: str | None = None,
        install: str | Iterable[str] = (),
        stream: str = "none",
        since: str = "2.0",
        aliases: str | Iterable[str] = (),
        agent_scope: bool = False,
        urls: str | Iterable[str] = (),
        auth_required: bool = True,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form of :meth:`register` for native handlers ``(ctx, **params)``.

        An omitted ``effects`` means ``admin`` (explicit-only), as the design requires.
        """
        identifier = validate_id(str(op_id))

        def tup(value: str | Iterable[str]) -> tuple[str, ...]:
            return (value,) if isinstance(value, str) else tuple(value)

        declared = effects is not None
        effect_set = (
            frozenset(tup(effects)) if declared and effects is not None else frozenset({"admin"})
        )
        unknown = effect_set - EFFECTS
        if unknown:
            raise ValueError(f"unknown effects {sorted(unknown)}; allowed {sorted(EFFECTS)}")

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            signature = inspect.signature(fn)
            try:
                hints = typing.get_type_hints(fn)
            except Exception:
                hints = {}
            params: list[Param] = []
            wants_ctx = False
            for index, (name, parameter) in enumerate(signature.parameters.items()):
                if index == 0 and name == "ctx":
                    wants_ctx = True
                    continue
                required = parameter.default is inspect.Parameter.empty
                params.append(
                    Param(
                        name,
                        _json_type(hints.get(name, str)),
                        required,
                        None if required else parameter.default,
                    )
                )
            names = {p.name for p in params}
            for declared_name in (*tup(paths), *tup(urls), *([command] if command else [])):
                if declared_name not in names:
                    raise ValueError(
                        f"{identifier}: paths/urls/command refers to unknown parameter "
                        f"{declared_name!r}"
                    )
            bindings = []
            for spec in tup(http):
                method, _, path = spec.partition(" ")
                bindings.append(HttpBinding(method.upper(), path.strip()))
            self.register(
                Operation(
                    id=identifier,
                    handler=fn,
                    effects=effect_set,
                    summary=summary or (fn.__doc__ or "").strip().split("\n")[0],
                    http=tuple(bindings),
                    params=tuple(params),
                    group=group,
                    stream=stream,
                    since=since,
                    aliases=tup(aliases),
                    install=tup(install),
                    limits=tup(limits),
                    paths=tup(paths),
                    command=command,
                    urls=tup(urls),
                    agent_scope=agent_scope,
                    auth_required=auth_required,
                    wants_ctx=wants_ctx,
                    effects_declared=declared,
                )
            )
            return fn

        return decorate

    # -- lookup ---------------------------------------------------------- #

    def get(self, op_id: Any) -> Operation | None:
        """The operation with exactly this ID (aliases are not followed)."""
        return self._ops.get(str(op_id))

    def resolve(self, name: Any) -> Operation | None:
        """The operation for an ID or an alias."""
        key = str(name)
        found = self._ops.get(key)
        if found is not None:
            return found
        target = self._aliases.get(key)
        return self._ops.get(target) if target is not None else None

    def all(self) -> dict[str, Operation]:
        """A copy of the ID -> operation mapping."""
        return dict(self._ops)

    def __contains__(self, name: object) -> bool:
        return self.resolve(name) is not None

    def __len__(self) -> int:
        return len(self._ops)

    def namespaces(self) -> dict[str, list[str]]:
        """Namespace -> sorted op IDs below it (the namespace is the ID minus its verb)."""
        out: dict[str, list[str]] = {}
        for op_id, operation in self._ops.items():
            out.setdefault(operation.namespace, []).append(op_id)
        return {ns: sorted(ids) for ns, ids in sorted(out.items())}

    def lint(self) -> list[str]:
        """Warnings that do not stop registration."""
        return [
            f"{op_id}: effects= not declared; defaulting to 'admin' (explicit-only)"
            for op_id, operation in sorted(self._ops.items())
            if not operation.effects_declared
        ]

    # -- documents ------------------------------------------------------- #

    def describe(
        self,
        *selectors: Any,
        visible: Callable[[Operation], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Catalog entries filtered by *selectors* and by the caller's *visible* predicate.

        Hidden operations (executable but unlisted, like ``hidden`` legacy commands) are omitted.
        """
        chosen = [str(s) for s in selectors]
        entries = []
        for op_id in sorted(self._ops):
            operation = self._ops[op_id]
            if operation.hidden:
                continue
            if chosen and not any(selector_matches(s, op_id) for s in chosen):
                continue
            if visible is not None and not visible(operation):
                continue
            entries.append(operation.entry())
        return entries

    def catalog(self) -> dict[str, Any]:
        """The ``operations.json`` document (every non-hidden op, no principal filtering)."""
        return {
            "catalog_version": CATALOG_VERSION,
            "api": "easy-sandbox/2",
            "ops": self.describe(),
        }
