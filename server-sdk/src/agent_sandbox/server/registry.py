"""Server-side command registry — stdlib-only, zero external dependencies.

Provides a lightweight command registration mechanism that lives entirely
within the ``server`` package and has **no** imports from the ``declarative``,
``models``, or any other SDK layer.  This removes the previous circular
dependency where ``routes.py`` had to lazy-import
``declarative.decorator.sandbox._registry`` at request time.

Named commands have exactly one mechanism: a function registered here is listed by
``GET /commands`` and run by ``POST /commands/{name}``.  Inside a sandbox template's
``commands.py`` register with the decorator::

    from agent_sandbox.server import command

    @command("greet", description="Say hello")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

Argument types come from ``str``, ``int``, ``float``, ``bool`` and ``list[str]`` annotations.
The client SDK's ``@sandbox.register`` ends in the same registry. A private
:class:`CommandRegistry` can be handed to
:class:`~agent_sandbox.server.SandboxServer` for tests.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import typing
from typing import Any

__all__ = [
    "CommandArg",
    "RegisteredCommand",
    "CommandRegistry",
    "command",
    "default_registry",
]

# ---------------------------------------------------------------------------
# Valid scalar and homogeneous string-array types
# ---------------------------------------------------------------------------

_VALID_ARG_TYPES: frozenset[str] = frozenset(
    {"string", "integer", "float", "boolean", "string_array"}
)


# ---------------------------------------------------------------------------
# Data models (stdlib dataclasses only)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CommandArg:
    """A single argument definition for a registered command.

    Attributes:
        name: Argument name (must match the function parameter name).
        type: Argument type hint — one of ``"string"``, ``"integer"``,
            ``"float"``, ``"boolean"``, or ``"string_array"`` (native JSON list of strings).
        required: Whether the caller *must* supply this argument.
        default: Default value (as a string) when the argument is omitted.
        description: Human-readable description shown in ``GET /commands``.
    """

    name: str
    type: str = "string"
    required: bool = False
    default: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        """Validate the argument type and any string-array default."""
        if self.type not in _VALID_ARG_TYPES:
            raise ValueError(f"Invalid arg type {self.type!r}; allowed: {sorted(_VALID_ARG_TYPES)}")
        if self.type == "string_array" and self.default is not None:
            try:
                value = json.loads(self.default)
            except (ValueError, TypeError) as exc:
                raise ValueError("string_array default must be a JSON array of strings") from exc
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError("string_array default must be a JSON array of strings")


@dataclasses.dataclass
class RegisteredCommand:
    """Metadata for a command registered with :class:`CommandRegistry`.

    Attributes:
        name: Unique command name used in ``POST /commands/{name}``.
        fn: Direct reference to the callable that implements the command.
        args: Ordered list of :class:`CommandArg` definitions.
        description: Human-readable description shown in ``GET /commands``.
        hidden: When ``True`` the command is executable but omitted from the
            ``GET /commands`` listing (see :meth:`CommandRegistry.list_visible`).
        scopes: Extra permission scopes (all-of) a caller needs, on top of
            ``commands:run``, when a server policy is active.
    """

    name: str
    fn: Any  # Callable[..., Any] — kept as Any to avoid typing import
    args: list[CommandArg] = dataclasses.field(default_factory=list)
    description: str = ""
    hidden: bool = False
    scopes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CommandRegistry:
    """Server-side command registry — independent of the declarative layer.

    Maintains a mapping of command names to :class:`RegisteredCommand`
    entries.  The registry can optionally be *frozen* to prevent
    runtime modifications after the server has started.

    Example::

        reg = CommandRegistry()

        @reg.command("greet")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        reg.freeze()
        assert "greet" in reg
    """

    def __init__(self) -> None:
        self._commands: dict[str, RegisteredCommand] = {}
        self._frozen: bool = False

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #

    def register(
        self,
        name: str,
        fn: Any,
        *,
        args: list[CommandArg] | None = None,
        description: str = "",
        hidden: bool = False,
        scopes: tuple[str, ...] | list[str] = (),
    ) -> None:
        """Register a command by *name*.

        Args:
            name: Unique command name.
            fn: The callable that implements the command.
            args: Optional list of :class:`CommandArg` definitions.
                Defaults to an empty list.
            description: Human-readable description.
            hidden: When ``True`` the command is executable but excluded from
                the ``GET /commands`` listing.
            scopes: Extra permission scopes required to run the command when a
                server policy is active (``GET /commands`` lists only commands
                the caller may run).

        Raises:
            RuntimeError: If the registry has been frozen via
                :meth:`freeze`.
        """
        if self._frozen:
            raise RuntimeError("Cannot register command after the registry has been frozen")
        self._commands[name] = RegisteredCommand(
            name=name,
            fn=fn,
            args=args if args is not None else [],
            description=description,
            hidden=hidden,
            scopes=tuple(scopes),
        )

    def command(
        self,
        name: str | None = None,
        *,
        hidden: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Decorator for registering a command.

        Supports both ``@registry.command("my_cmd")`` and
        ``@registry.command()`` (name inferred from the function).

        Args:
            name: Explicit command name.  When ``None``, the decorated
                function's ``__name__`` is used.
            hidden: When ``True`` the command is executable but excluded from
                the ``GET /commands`` listing.
            **kwargs: Forwarded to :meth:`register` (e.g. ``args``,
                ``description``).

        Returns:
            A decorator that registers the function and returns it
            unchanged.

        Example::

            @registry.command("add")
            def add(a: int, b: int) -> int:
                return a + b

            @registry.command()
            def greet(name: str) -> str:
                return f"Hello, {name}!"
        """

        def decorator(fn: Any) -> Any:
            cmd_name = name if name is not None else fn.__name__
            # If no explicit args were provided, infer from function signature.
            if "args" not in kwargs or kwargs["args"] is None:
                sig = inspect.signature(fn)
                # typing.get_type_hints() resolves stringified annotations
                # (PEP 563 / ``from __future__ import annotations``) back to
                # real types so that int/float/bool params are correctly
                # recognised instead of being treated as plain strings.
                try:
                    resolved_hints = typing.get_type_hints(fn)
                except Exception:
                    resolved_hints = {}
                inferred_args: list[CommandArg] = []
                for param_name, param in sig.parameters.items():
                    arg_type = "string"  # default
                    # Prefer resolved hint; fall back to raw annotation
                    annotation = resolved_hints.get(param_name, param.annotation)
                    if annotation != inspect.Parameter.empty:
                        _annotation_map = {
                            int: "integer",
                            float: "float",
                            bool: "boolean",
                        }
                        if typing.get_origin(annotation) is list and typing.get_args(
                            annotation
                        ) == (str,):
                            arg_type = "string_array"
                        else:
                            arg_type = _annotation_map.get(annotation, "string")

                    required = param.default is inspect.Parameter.empty
                    default = None
                    if not required and (param.default is not None or arg_type == "string_array"):
                        default = (
                            json.dumps(param.default)
                            if arg_type == "string_array"
                            else str(param.default)
                        )

                    inferred_args.append(
                        CommandArg(
                            name=param_name,
                            type=arg_type,
                            required=required,
                            default=default,
                        )
                    )
                kwargs["args"] = inferred_args
            self.register(cmd_name, fn, hidden=hidden, **kwargs)
            return fn

        return decorator

    def freeze(self) -> None:
        """Lock the registry to prevent further modifications.

        Once frozen, any call to :meth:`register` (including via
        :meth:`command`) will raise :class:`RuntimeError`.
        """
        self._frozen = True

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def get(self, name: str) -> RegisteredCommand | None:
        """Return the :class:`RegisteredCommand` for *name*, or ``None``.

        Args:
            name: The command name to look up.

        Returns:
            The registered command, or ``None`` if not found.
        """
        return self._commands.get(name)

    def list_all(self) -> dict[str, RegisteredCommand]:
        """Return a shallow copy of all registered commands.

        Returns:
            A new ``dict`` mapping command names to
            :class:`RegisteredCommand` instances.
        """
        return dict(self._commands)

    def list_visible(self) -> dict[str, RegisteredCommand]:
        """Return all registered commands that are not marked ``hidden``.

        Returns:
            A new ``dict`` mapping command names to
            :class:`RegisteredCommand` instances, excluding any registered
            with ``hidden=True``.
        """
        return {name: cmd for name, cmd in self._commands.items() if not cmd.hidden}

    # ------------------------------------------------------------------ #
    # Dunder helpers
    # ------------------------------------------------------------------ #

    def __contains__(self, name: str) -> bool:
        """Return ``True`` if *name* is registered."""
        return name in self._commands

    def __len__(self) -> int:
        """Return the number of registered commands."""
        return len(self._commands)

    def __repr__(self) -> str:
        frozen_tag = " (frozen)" if self._frozen else ""
        return f"<CommandRegistry commands={list(self._commands.keys())}{frozen_tag}>"


# ---------------------------------------------------------------------------
# Module-level default registry
# ---------------------------------------------------------------------------

_default_registry = CommandRegistry()


def default_registry() -> CommandRegistry:
    """Return the module-level default :class:`CommandRegistry` instance.

    Returns:
        The singleton :data:`_default_registry`.
    """
    return _default_registry


def command(name: str | None = None, *, hidden: bool = False, **kwargs: Any) -> Any:
    """Register the decorated function as a named command on the default registry.

    ``name`` defaults to the function name; ``hidden``, ``description``, ``scopes`` and ``args``
    are those of :meth:`CommandRegistry.register`.  Returns the function unchanged.
    """
    return _default_registry.command(name, hidden=hidden, **kwargs)
