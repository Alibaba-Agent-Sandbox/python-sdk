"""Command guard: normalised argv, deny pass, allow-list, no shell unless granted.

Patterns (design 03 section 7.1):

* a single token without ``...``/``{...}`` constrains the **executable** only (v1 behaviour:
  matched against ``argv[0]`` and its basename, ``fnmatch`` globs);
* several tokens (a string is ``shlex``-split) constrain the **whole argv**, one token per element:
  literal, glob (never matches an element containing ``/`` or ``..`` or starting with ``-`` unless
  the pattern token itself does), ``...`` (zero or more elements), ``{int}``, ``{word}`` and
  ``{path}`` (canonicalised through the guard's path scope; never matches without one).

Deny rules are evaluated first and match against the same argv with short flags expanded
(``-lR`` -> ``-l -R``).  Deny patterns are defence in depth; pin arguments in the allow pattern.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from typing import TYPE_CHECKING

from ..policy import PolicyDenied

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..runtime import EndpointContext
    from .paths import PathGuard

__all__ = [
    "CommandGuard",
    "check_command",
    "command_guard",
    "command_guard_from_context",
    "expand_short_flags",
]

MAX_ARGV = 256
MAX_ARG_LENGTH = 4096
MAX_ELLIPSES = 3

_SHORT_FLAGS = re.compile(r"^-[A-Za-z]{2,}$")
_INT = re.compile(r"^[0-9]{1,9}$")
_WORD = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.@:+=,-]*$")
_GLOB_CHARS = "*?["

_LEGACY_CODE = "command_not_allowed"


def expand_short_flags(argv: Sequence[str]) -> list[str]:
    """Expand grouped short flags for matching only: ``["ls", "-lR"]`` -> ``["ls", "-l", "-R"]``."""
    out: list[str] = list(argv[:1])
    for arg in argv[1:]:
        if _SHORT_FLAGS.match(arg):
            out.extend(f"-{ch}" for ch in arg[1:])
        else:
            out.append(arg)
    return out


def _is_executable_only(tokens: Sequence[str]) -> bool:
    return len(tokens) == 1 and tokens[0] != "..." and not tokens[0].startswith("{")


def _tokens(pattern: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(pattern, str):
        try:
            tokens = tuple(shlex.split(pattern))
        except ValueError as exc:
            raise ValueError(f"invalid command pattern {pattern!r}: {exc}") from exc
    else:
        tokens = tuple(pattern)
    if not tokens:
        raise ValueError("empty command pattern")
    if tokens.count("...") > MAX_ELLIPSES:
        raise ValueError(f"at most {MAX_ELLIPSES} '...' per command pattern")
    return tokens


def _exe_matches(argv0: str, token: str) -> bool:
    return any(fnmatch.fnmatchcase(name, token) for name in (argv0, os.path.basename(argv0)))


def _arg_matches(arg: str, token: str) -> bool:
    if not any(ch in token for ch in _GLOB_CHARS):
        return arg == token
    if "/" in arg and "/" not in token:
        return False
    if ".." in arg and ".." not in token:
        return False
    if arg.startswith("-") and not token.startswith("-"):
        return False
    return fnmatch.fnmatchcase(arg, token)


class CommandGuard:
    """Admit or reject an argv against deny and allow patterns.

    Args:
        allow: Allow patterns.  Empty means "no allow-list" (v1 semantics) unless
            *require_allow* is set, in which case nothing is allowed.
        deny: Deny patterns; evaluated first and absolute.
        shell: Whether callers may ask for a shell.
        path_guard: Scope used to canonicalise ``{path}`` tokens.
        require_allow: Fail closed when *allow* is empty.
        legacy_codes: Report deny matches as ``command_not_allowed`` (the v1 engine code)
            instead of ``command_denied``.
    """

    def __init__(
        self,
        allow: Sequence[str | Sequence[str]] = (),
        deny: Sequence[str | Sequence[str]] = (),
        *,
        shell: bool = False,
        path_guard: PathGuard | None = None,
        require_allow: bool = False,
        legacy_codes: bool = False,
    ) -> None:
        self.allow = tuple(_tokens(p) for p in allow)
        self.deny = tuple(_tokens(p) for p in deny)
        self.shell = shell
        self.path_guard = path_guard
        self.require_allow = require_allow
        self.legacy_codes = legacy_codes

    # -- normalisation ------------------------------------------------- #

    @staticmethod
    def normalise(command: object = None, argv: object = None) -> list[str]:
        """One argv from ``command`` (string, ``shlex``-split) xor ``argv`` (list of strings)."""
        if (command is None) == (argv is None):
            raise PolicyDenied(
                "command_invalid",
                "Provide exactly one of 'command' and 'argv'",
                status=400,
                error_type="ValueError",
            )
        if command is not None:
            if not isinstance(command, str):
                raise PolicyDenied(
                    "command_invalid",
                    "'command' must be a string",
                    status=400,
                    error_type="ValueError",
                )
            try:
                items: object = shlex.split(command)
            except ValueError as exc:
                raise PolicyDenied(
                    "command_invalid",
                    f"Unparsable command: {exc}",
                    status=400,
                    error_type="ValueError",
                ) from exc
        else:
            items = argv
        if (
            not isinstance(items, (list, tuple))
            or not items
            or not all(isinstance(a, str) for a in items)
        ):
            raise PolicyDenied(
                "command_invalid",
                "argv must be a non-empty list of strings",
                status=400,
                error_type="ValueError",
            )
        out = list(items)
        if len(out) > MAX_ARGV or any(len(a) > MAX_ARG_LENGTH or "\x00" in a for a in out):
            raise PolicyDenied(
                "command_invalid",
                "argv is too long or contains a NUL byte",
                status=400,
                error_type="ValueError",
            )
        if not out[0]:
            raise PolicyDenied(
                "command_invalid", "Empty executable", status=400, error_type="ValueError"
            )
        return out

    # -- matching ------------------------------------------------------ #

    def _match(self, tokens: tuple[str, ...], argv: list[str]) -> list[int] | None:
        """Return the argv indexes bound to ``{path}`` tokens, or ``None`` if no match."""
        if _is_executable_only(tokens):
            return [] if _exe_matches(argv[0], tokens[0]) else None
        memo: dict[tuple[int, int], list[int] | None] = {}

        def go(i: int, j: int) -> list[int] | None:
            key = (i, j)
            if key in memo:
                return memo[key]
            result: list[int] | None = None
            if i == len(tokens):
                result = [] if j == len(argv) else None
            elif tokens[i] == "...":
                for k in range(j, len(argv) + 1):
                    result = go(i + 1, k)
                    if result is not None:
                        break
            elif j < len(argv) and self._token(tokens[i], argv[j], first=(j == 0)):
                rest = go(i + 1, j + 1)
                if rest is not None:
                    result = [j, *rest] if tokens[i] == "{path}" else rest
            memo[key] = result
            return result

        return go(0, 0)

    def _token(self, token: str, arg: str, *, first: bool) -> bool:
        if first:
            return _exe_matches(arg, token)
        if token == "{path}":
            return bool(arg) and not arg.startswith("-") and self.path_guard is not None
        if token == "{int}":
            return bool(_INT.match(arg))
        if token == "{word}":
            return bool(_WORD.match(arg))
        return _arg_matches(arg, token)

    # -- decision ------------------------------------------------------ #

    def check(self, argv: Sequence[str], *, shell: bool = False) -> list[str]:
        """Return the admitted argv (``{path}`` tokens canonicalised) or raise.

        Raises:
            PolicyDenied: ``shell_not_allowed``, ``command_invalid`` (400), ``command_denied``
                (or ``command_not_allowed`` with ``legacy_codes``), ``command_not_allowed``,
                or a ``path_*`` code from a ``{path}`` token.
        """
        admitted = self.normalise(argv=list(argv))
        if shell and not self.shell:
            raise PolicyDenied("shell_not_allowed", "A shell is not permitted here")
        expanded = expand_short_flags(admitted)
        deny_code = _LEGACY_CODE if self.legacy_codes else "command_denied"
        for tokens in self.deny:
            if self._match(tokens, expanded) is not None:
                raise PolicyDenied(deny_code, f"Command {admitted[0]!r} is denied by policy")
        if not self.allow:
            if self.require_allow:
                raise PolicyDenied(
                    "scope_required", f"Command {admitted[0]!r} has no allow-list to match"
                )
            return admitted
        for tokens in self.allow:
            paths = self._match(tokens, expanded)
            if paths is None:
                continue
            if paths:
                return self._canonicalise(admitted, expanded, paths)
            return admitted
        raise PolicyDenied(_LEGACY_CODE, f"Command {admitted[0]!r} is not in the allow-list")

    def _canonicalise(
        self, admitted: list[str], expanded: list[str], paths: list[int]
    ) -> list[str]:
        guard = self.path_guard
        if guard is None:
            raise PolicyDenied(_LEGACY_CODE, "Command pattern needs a path scope")
        if expanded != admitted:
            raise PolicyDenied(_LEGACY_CODE, "Grouped short flags cannot be combined with {path}")
        out = list(admitted)
        for index in paths:
            out[index] = guard.resolve(admitted[index], "exec", field="argv")
        return out

    def permits(self, argv: Sequence[str]) -> bool:
        """Return whether *argv* is admitted; never raises."""
        try:
            self.check(argv)
        except PolicyDenied:
            return False
        return True


def command_guard(
    allow: Sequence[str | Sequence[str]] = (),
    deny: Sequence[str | Sequence[str]] = (),
    *,
    shell: bool = False,
    path_guard: PathGuard | None = None,
) -> CommandGuard:
    """Fail-closed constructor: an empty *allow* admits nothing."""
    return CommandGuard(allow, deny, shell=shell, path_guard=path_guard, require_allow=True)


def command_guard_from_context(ctx: EndpointContext) -> CommandGuard:
    """The endpoint's ``allow_commands`` / ``deny_commands`` params as a guard (v1 codes)."""
    from .paths import path_guard_from_context

    return CommandGuard(
        ctx.param("allow_commands", []) or (),
        ctx.param("deny_commands", []) or (),
        path_guard=path_guard_from_context(ctx),
        legacy_codes=True,
    )


def check_command(ctx: EndpointContext, argv: Sequence[str], *, shell: bool = False) -> list[str]:
    """Policy-engine entry point: admit *argv* under the endpoint's command params."""
    return command_guard_from_context(ctx).check(argv, shell=shell)
